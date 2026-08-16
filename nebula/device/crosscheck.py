"""
device/crosscheck.py — the CLAUDEwa.md §6 gate, in Python, where it can fail.

WHY THIS FILE EXISTS
--------------------
§6 says: *"at least one full extraction must be checked against these. If A_dc
from the wrapper disagrees with gm*RL/k, something upstream is broken and every
downstream number is fiction. Do not proceed past that discrepancy."*

That check used to live in a `.control` block inside
`spice/g1_handdesign.cir`, and **it never executed**. Two independent reasons,
both confirmed by running the netlist and reading the output:

1. `@m1[gm]` belongs to the `op1` plot. After `.ac` the current plot is `ac1`,
   so every `let` referencing it failed.
2. `.param` names such as `{RS_OHM}` are not visible as `.control` vectors at
   all, so even `let k = 1 + gm * {RS_OHM} / 2` had nothing to multiply.

ngspice reports both as **warnings**, continues, and **exits 0**. The gate was
reported as passing for a week while computing nothing — and the equation it
was supposed to be checking was 2.33 dB wrong.

Hence CLAUDEwa.md §8 rule 9: *a check that reports failure as a warning and
exits zero is not a gate.* This module is the correction. Everything here

  * parses primitives out of ngspice's stdout,
  * does the arithmetic in Python,
  * **raises** on disagreement, and
  * scans the output for ngspice's silent-failure warnings first, so a run that
    printed "not available" can never be read as a clean result.

`nebula/tests/test_crosscheck.py` includes a test that corrupts A_dc and
asserts the gate goes red. A gate without such a test is an untested gate.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional, Sequence

from nebula.common.design_equations import cross_check_extraction

# ─────────────────────────────────────────────────────────────────────────────
# Step 0 — never trust an ngspice run you have not grepped.
# ─────────────────────────────────────────────────────────────────────────────

#: Patterns that mean "ngspice could not compute something but did not tell the
#: shell". Exit code 0 alongside any of these is the G26 failure mode.
_SILENT_FAILURE_PATTERNS: tuple[str, ...] = (
    r"is not available or has zero length",
    r"(?i)^\s*Error[:,]",
    r"could not find a valid modelname",
    # A `.param` name a model card references but nothing defines. ngspice
    # prints `Undefined parameter [x]` followed by `ERROR: fatal error in
    # ngspice, exit(1)`, and NEITHER line matched this list before session 19 —
    # the second because it is upper-case and `^\s*Error[:,]` was anchored
    # case-sensitively. Found while trimming the R/C parameter decks
    # (`device/pdk_trim.py`): the equivalence probe was reading a run that had
    # aborted and comparing the empty result set. G26 inside the G26 guard.
    #
    # The asymmetry is worth knowing on its own: a `.model` card whose
    # parameters are undefined is accepted in SILENCE as long as nothing
    # instantiates it, and is FATAL the moment something does.
    r"Undefined parameter",
    r"fatal error in ngspice",
    r"doAnalyses: iteration limit reached",
    r"singular matrix",
    r"Simulation interrupted due to error",
    # A PRINTED VALUE THAT IS NOT A NUMBER. ngspice's `.noise` can return
    # `inoise_total = -nan(ind)` and exit 0 — measured on a current-mirror tail
    # at ss/0.95/125 C, where the mirror reference device's noise is rejected
    # to machine zero and the log-slope integration of the integrated noise
    # hits log(0). See G54.
    #
    # This is anchored to `= value` rather than the bare word so it cannot fire
    # on a model parameter or a comment that happens to contain "nan" or "inf"
    # (`nfactor`, `Infinity` in a banner). Without it the NaN is caught only by
    # accident, because the numeric regexes in this module do not match "nan" —
    # and a laxer parser would carry NaN into a spec check, where `nan < tau`
    # is False and reads as a genuine FAILURE rather than as a broken run.
    r"=\s*[-+]?(?:nan|inf)\b",
)

#: Warnings that are normal for these netlists and carry no numeric meaning.
#: Keep this list SHORT and justified — every entry is a thing we have decided
#: not to look at again.
_BENIGN_PATTERNS: tuple[str, ...] = (
    # sky130 prints these for every device when rdsw/rsw are model-defaulted.
    r"conductance reset to",
    # emitted when a subckt line carries m=; we set mult explicitly on purpose.
    r"m=xx on \.subckt line will override multiplier",
)


class SilentFailure(RuntimeError):
    """ngspice reported a computation failure as a warning and exited 0."""


class CrossCheckFailure(AssertionError):
    """The §6 gate did not pass. Every downstream number is fiction."""


def scan_for_silent_failures(text: str) -> list[str]:
    """Return the offending lines from an ngspice run. Empty list means clean.

    This is the grep HANDOFF G26 demands, as a function so it is applied
    everywhere rather than remembered sometimes.
    """
    offenders: list[str] = []
    for line in text.splitlines():
        if any(re.search(p, line) for p in _BENIGN_PATTERNS):
            continue
        if any(re.search(p, line, re.I if p.startswith("^") is False else 0)
               for p in _SILENT_FAILURE_PATTERNS):
            offenders.append(line.strip())
    return offenders


def assert_no_silent_failures(text: str) -> None:
    """Raise `SilentFailure` if the run printed a warning-shaped failure."""
    offenders = scan_for_silent_failures(text)
    if offenders:
        shown = "\n  ".join(offenders[:10])
        more = f"\n  ... and {len(offenders) - 10} more" if len(offenders) > 10 else ""
        raise SilentFailure(
            f"ngspice printed {len(offenders)} failure(s) as warnings and "
            f"likely still exited 0. Exit code is not a success signal "
            f"(CLAUDEwa.md §8 rule 9):\n  {shown}{more}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — parse primitives. Primitives only; no derived quantities.
# ─────────────────────────────────────────────────────────────────────────────

_NUM = r"[-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?"


def parse_scalar(text: str, name: str) -> Optional[float]:
    """`print x` emits `x = <value>`. Returns None if absent.

    `name` is matched literally, so both plain (`@m1[gm]`) and subckt-qualified
    (`@m.xm1.msky130_fd_pr__nfet_01v8[gm]`) device references work.
    """
    m = re.search(rf"^\s*{re.escape(name)}\s*=\s*({_NUM})\s*$", text, re.M)
    return float(m.group(1)) if m else None


def parse_meas(text: str, name: str) -> tuple[Optional[float], Optional[float]]:
    """`meas` emits `name = value` and, for MAX/MIN, `at= x` on the same line.

    Returns `(value, at)`; `at` is None for FIND-style measurements.
    """
    m = re.search(rf"^\s*{re.escape(name)}\s*=\s*({_NUM})(?:\s+at=\s*({_NUM}))?",
                  text, re.M)
    if not m:
        return None, None
    return float(m.group(1)), (float(m.group(2)) if m.group(2) else None)


def find_device_scalar(text: str, prop: str) -> Optional[float]:
    """Find `@<anything>[prop]` without knowing the device's expanded name.

    sky130 devices land inside a subckt, so the printed name is
    `@m.xm1.msky130_fd_pr__nfet_01v8[gm]` rather than `@m1[gm]`. The callers
    should not have to care which model family produced the output.
    """
    m = re.search(rf"^\s*@[^\s\[]*\[{re.escape(prop)}\]\s*=\s*({_NUM})\s*$",
                  text, re.M)
    return float(m.group(1)) if m else None


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — the gate itself.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CrossCheckResult:
    """Outcome of one §6 extraction check. `passed=False` means STOP."""

    passed: bool
    disagreement_db: float
    simulated_g_dc_db: float
    predicted_g_dc_db: float
    #: Same prediction with gmbs forced to 0 — i.e. §6 exactly as it was
    #: written before the body-effect correction. Reported so the size of the
    #: correction stays visible in every run rather than being folded away.
    predicted_verbatim_db: float
    gm: float
    gmbs: float
    rs: float
    rl: float
    tol_db: float

    @property
    def gmbs_over_gm(self) -> float:
        return self.gmbs / self.gm if self.gm else math.nan

    @property
    def body_effect_db(self) -> float:
        """How much the body-effect term moves the prediction, in dB."""
        return self.predicted_verbatim_db - self.predicted_g_dc_db

    def summary(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        return (
            f"[{verdict}] §6 cross-check: simulated {self.simulated_g_dc_db:+.2f} dB "
            f"vs predicted {self.predicted_g_dc_db:+.2f} dB "
            f"(disagreement {self.disagreement_db:.2f} dB, tol {self.tol_db:.2f} dB)\n"
            f"        gm={self.gm * 1e3:.3f} mS  gmbs={self.gmbs * 1e3:.3f} mS  "
            f"gmbs/gm={self.gmbs_over_gm:.3f}\n"
            f"        §6 without the body-effect term would predict "
            f"{self.predicted_verbatim_db:+.2f} dB "
            f"({self.body_effect_db:+.2f} dB optimistic)"
        )

    def raise_if_failed(self) -> "CrossCheckResult":
        """Fail loudly. This is the whole point of the module."""
        if not self.passed:
            raise CrossCheckFailure(
                self.summary()
                + "\n\nCLAUDEwa.md §6: if A_dc from the wrapper disagrees with "
                "gm*RL/k, something upstream is broken and every downstream "
                "number is fiction. Do not proceed past that discrepancy — "
                "check the operating point, the netlist, the AC probe, and the "
                "Rs convention (Rs is the FULL source-to-source resistance)."
            )
        return self


def cross_check_ngspice_output(
    text: str,
    rs: float,
    rl: float,
    tol_db: float = 1.0,
    g_dc_meas_name: str = "g_dc",
    include_body_effect: bool = True,
) -> CrossCheckResult:
    """Run the §6 gate against raw ngspice stdout.

    Parameters
    ----------
    text                 raw stdout (+stderr) of one ngspice batch run.
    rs, rl               the values the netlist was built with, in ohms. `rs`
                         is the FULL resistance between the two sources.
    tol_db               §6's acceptance tolerance. 1 dB by default.
    g_dc_meas_name       name of the `meas ac ... FIND` that captured the DC
                         gain in dB.
    include_body_effect  pass False to reproduce §6 exactly as it was written
                         before the correction. Only useful for demonstrating
                         that the old form fails; never use it as a gate.

    Raises
    ------
    SilentFailure   if the run printed warning-shaped failures.
    ValueError      if a required primitive is missing — a missing number is a
                    failure, never a default.
    """
    assert_no_silent_failures(text)

    gm = find_device_scalar(text, "gm")
    gmbs = find_device_scalar(text, "gmbs")
    g_dc_db, _ = parse_meas(text, g_dc_meas_name)

    missing = [n for n, v in (("gm", gm), ("gmbs", gmbs),
                              (g_dc_meas_name, g_dc_db)) if v is None]
    if missing:
        raise ValueError(
            f"cross-check cannot run: ngspice output has no {missing}. "
            f"Print @m1[gm] and @m1[gmbs] after `op`, and `meas ac "
            f"{g_dc_meas_name} FIND ... AT=<low f>` after `ac`. A missing "
            f"primitive is a failed check, not a zero (CLAUDEwa.md §8 rule 1)."
        )
    assert gm is not None and gmbs is not None and g_dc_db is not None

    if gm <= 0.0:
        raise ValueError(f"gm={gm} is not positive — the device is off, not degenerate.")

    gmbs_used = gmbs if include_body_effect else 0.0
    extracted_lin = 10.0 ** (g_dc_db / 20.0)
    agrees, delta_db = cross_check_extraction(
        extracted_g_dc=extracted_lin, gm=gm, rs=rs, rl=rl,
        tol_db=tol_db, gmbs=gmbs_used,
    )

    def _pred_db(gmbs_val: float) -> float:
        return 20.0 * math.log10(gm * rl / (1.0 + (gm + gmbs_val) * rs / 2.0))

    return CrossCheckResult(
        passed=agrees,
        disagreement_db=delta_db,
        simulated_g_dc_db=g_dc_db,
        predicted_g_dc_db=_pred_db(gmbs_used),
        predicted_verbatim_db=_pred_db(0.0),
        gm=gm, gmbs=gmbs, rs=rs, rl=rl, tol_db=tol_db,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — the derived quantities that used to be computed in `.control`.
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DerivedAc:
    """Quantities the netlist must NOT compute for itself."""

    g_dc_db: float
    g_nyq_db: float
    g_pk_db: float
    f_pk_hz: float

    @property
    def peaking_db(self) -> float:
        return self.g_pk_db - self.g_dc_db

    @property
    def nyquist_boost_db(self) -> float:
        """Gain at Nyquist relative to DC.

        Distinct from `peaking_db`: a stage can show healthy peaking at a
        frequency well below Nyquist and still deliver *less* than its DC gain
        where the data actually lives. S3 constrains both the boost and the
        frequency for exactly this reason.
        """
        return self.g_nyq_db - self.g_dc_db


def derived_ac(
    text: str,
    dc_name: str = "g_dc",
    nyq_name: str = "g_nyq",
    pk_name: str = "g_pk",
) -> DerivedAc:
    """Parse the three AC measurements and derive peaking in Python."""
    assert_no_silent_failures(text)
    g_dc, _ = parse_meas(text, dc_name)
    g_nyq, _ = parse_meas(text, nyq_name)
    g_pk, f_pk = parse_meas(text, pk_name)

    missing = [n for n, v in ((dc_name, g_dc), (nyq_name, g_nyq),
                              (pk_name, g_pk), (f"{pk_name} at=", f_pk))
               if v is None]
    if missing:
        raise ValueError(f"AC output has no {missing}; cannot derive peaking.")
    assert g_dc is not None and g_nyq is not None
    assert g_pk is not None and f_pk is not None
    return DerivedAc(g_dc_db=g_dc, g_nyq_db=g_nyq, g_pk_db=g_pk, f_pk_hz=f_pk)


def power_w(vdd_v: float, i_tail_a: float) -> float:
    """Static power. Trivial, and it lives here because `let power_mw = ...`
    inside `.control` silently produced nothing for a week (G26)."""
    if vdd_v <= 0.0 or i_tail_a <= 0.0:
        raise ValueError(f"vdd={vdd_v}, i_tail={i_tail_a}: both must be positive")
    return vdd_v * i_tail_a


def overdrive_v(text: str) -> float:
    """Vov = Vgs - Vth, from parsed primitives."""
    vgs = find_device_scalar(text, "vgs")
    vth = find_device_scalar(text, "vth")
    if vgs is None or vth is None:
        raise ValueError("output has no @m*[vgs] and/or @m*[vth]")
    return vgs - vth


def in_saturation(text: str) -> bool:
    """Vds > Vdsat, from parsed primitives."""
    vds = find_device_scalar(text, "vds")
    vdsat = find_device_scalar(text, "vdsat")
    if vds is None or vdsat is None:
        raise ValueError("output has no @m*[vds] and/or @m*[vdsat]")
    return vds > vdsat


def check_all(
    text: str,
    rs: float,
    rl: float,
    vdd_v: float,
    i_tail_a: float,
    tol_db: float = 1.0,
    dc_name: str = "g_dc",
    nyq_name: str = "g_nyq",
    pk_name: str = "g_pk",
) -> tuple[CrossCheckResult, DerivedAc]:
    """One call that runs the gate and derives everything. Raises on failure.

    This is what a caller should use: it is not possible to get the derived
    numbers out of it without the §6 gate having passed first.

    The `*_name` arguments are the `meas` labels used by the netlist. They
    differ between the hand-design netlist (`gain_dc_db`, ...) and the
    auto-generated sweep netlist (`g_dc`, ...); `power_w(vdd_v, i_tail_a)` is
    validated here so a bad bias pair fails before the numbers are handed back.
    """
    power_w(vdd_v, i_tail_a)
    result = cross_check_ngspice_output(text, rs=rs, rl=rl, tol_db=tol_db,
                                        g_dc_meas_name=dc_name)
    result.raise_if_failed()
    return result, derived_ac(text, dc_name=dc_name, nyq_name=nyq_name,
                              pk_name=pk_name)


__all__: Sequence[str] = (
    "SilentFailure", "CrossCheckFailure", "CrossCheckResult", "DerivedAc",
    "scan_for_silent_failures", "assert_no_silent_failures",
    "parse_scalar", "parse_meas", "find_device_scalar",
    "cross_check_ngspice_output", "derived_ac", "check_all",
    "power_w", "overdrive_v", "in_saturation",
)
