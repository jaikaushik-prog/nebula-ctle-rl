"""
The parameter-deck trim must be free. Not "close" — free.

`nebula/device/pdk_trim.py` deletes 8,823 of the 8,909 `.param` definitions the
extended library's R/C corner decks carry, on the argument that nothing the
library includes references them. This file is the argument's gate. It has
three independent parts, because each one catches a different way of being
wrong:

1. **Provenance.** Every file in `spice/pdk_trim/` is re-derived from the PDK
   and compared byte for byte. Nothing there is hand-written, so a hand edit,
   a stale checkout or a PDK update all show up here rather than in a number.
   This is the rule-9 mechanism: the trim has one definition, in code.

2. **Equivalence, at rel=0 abs=0.** A probe that touches every device the
   netlists use runs through the trimmed library and through the same library
   with the trim undone, and the RAW PRINTED TEXT must agree exactly. Raw
   text, not floats: parsing to float and back hides differences below the
   printed precision, which is the kind of "equivalent" this test refuses
   (PASSIVES.md §3.1). Marked slow only for the full-library leg; the
   trimmed-vs-untrimmed leg is fast enough for every run.

3. **The gate can fail.** `test_a_broken_trim_is_caught` deliberately deletes
   a kept parameter and asserts the comparison goes red. G73: a gate whose
   condition is unreachable is indistinguishable from a deleted gate.

`test_trimmed_lib_passives.py` remains the outer gate — it compares the same
library against the FULL SKY130 library. Both are needed: that one proves the
extended trim is right, this one proves the parameter trim did not break it,
and only this one is cheap enough to run every time.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from nebula.device import pdk_trim as PT
from nebula.device.crosscheck import scan_for_silent_failures

NGSPICE = Path(
    r"C:\Users\DELL\miniforge3\envs\nebula\Library\bin\ngspice_con.exe")
SPICE_DIR = PT.SPICE_DIR
FULL_LIB = PT.PDK_NGSPICE / "sky130.lib.spice"

_needs_tools = pytest.mark.skipif(
    not (NGSPICE.exists() and PT.PDK_NGSPICE.exists() and PT.CTLE_LIB.exists()),
    reason="needs ngspice + the SKY130 PDK install (HANDOFF G33)",
)
_needs_pdk = pytest.mark.skipif(
    not PT.PDK_NGSPICE.exists(),
    reason="needs the SKY130 PDK install (HANDOFF G33)",
)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Provenance — the generated files are a function of the PDK.
# ─────────────────────────────────────────────────────────────────────────────


@_needs_pdk
def test_generated_files_match_a_fresh_derivation():
    """`spice/pdk_trim/` == `python -m nebula.device.pdk_trim --write`.

    Fails on a hand edit, on a PDK update, and — the case that matters — on
    someone adding a device include to `sky130_ctle.lib.spice` without
    regenerating, which would widen the set of parameters the models reference
    while the trim still carried the old, narrower one.
    """
    stale = PT.stale_files()
    assert not stale, (
        "spice/pdk_trim/ does not match a fresh derivation: "
        + ", ".join(stale)
        + ". Run `python -m nebula.device.pdk_trim --write`.")


@_needs_pdk
def test_the_trim_actually_removes_almost_everything():
    """The whole justification is the size of the cut; assert it is there.

    Not a tautology: if a future change made the keep-set explode (a library
    include that references half the deck, say), the trim would still be
    *correct* and would silently stop being *worth it*. That is worth knowing.
    """
    b = PT.build()
    kept = sum(k for k, _ in b.per_deck.values())
    total = sum(t for _, t in b.per_deck.values())
    assert total > 15000, f"only {total} definition lines; the decks shrank?"
    assert kept / total < 0.05, (
        f"the trim now keeps {kept}/{total} = {100 * kept / total:.1f}% of the "
        f"parameter decks. Below ~6x the cut stops paying for the complexity; "
        f"re-measure before assuming it still does.")
    assert len(b.keep) == 86, (
        f"the keep-set moved from 86 to {len(b.keep)} names. That is a real "
        f"change in what the library references — find out what, then update "
        f"this number and the PASSIVES.md §3.2 table together.")


@_needs_pdk
def test_every_kept_parameter_is_reachable_from_the_library():
    """No name survives 'just in case'. The keep-set is derived, not curated."""
    tree = PT.library_include_tree()
    referenced = set()
    for text in tree.values():
        referenced |= set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text))
    b = PT.build()
    defs = PT.parse_param_lines(
        (PT.PDK_NGSPICE / "parameters" / "typical.spice").read_text(errors="replace"))
    closure = PT.needed_names(defs, referenced)
    # `build()` also scans the .cir files and the netlist-building modules, so
    # its keep-set may be a superset. It must never be a subset.
    assert closure <= b.keep, (
        f"names reachable from the library but NOT kept: "
        f"{sorted(closure - b.keep)[:10]}")


#: `render_rc_corner` prefixes a provenance banner and then reproduces the PDK
#: file. The banner is delimited by a blank line, so the comparison below can
#: strip it positionally rather than by guessing which comments are ours.
def _body_after_banner(text: str) -> "list[str]":
    lines = text.splitlines()
    blank = lines.index("")
    return lines[blank + 1:]


@_needs_pdk
def test_the_rc_decks_differ_from_the_pdk_in_exactly_one_line():
    """The corner decks carry the PDK's process constants verbatim.

    Every number in an R/C corner deck — `rp1`, `crpf_precision`, the `tol_m*`
    tolerances — stays the PDK's own text. Only the `.include` moves. If this
    fails, someone has started editing PDK numbers inside a generated file,
    which is the G32 failure: two definitions of one thing, and the one a
    human reads is not the one that produced the numbers.
    """
    for corner in PT.RC_CORNERS:
        pdk = (PT.PDK_NGSPICE / "r+c" / f"{corner}.spice").read_text(
            errors="replace").splitlines()
        ours = _body_after_banner(
            (PT.TRIM_DIR / f"{corner}.spice").read_text(errors="replace"))
        assert len(ours) == len(pdk), (
            f"{corner}: {len(ours)} lines after the banner against the PDK's "
            f"{len(pdk)}")
        differ = [(a, b) for a, b in zip(pdk, ours) if a != b]
        # Two: the `../parameters/x.spice` include becomes the trim, and the
        # `../sky130_fd_pr__model__r+c.model.spice` include becomes absolute
        # because this file no longer sits in the PDK's `r+c/` directory.
        assert len(differ) == 2, (
            f"{corner} differs from the PDK on {len(differ)} lines, expected "
            f"exactly the two includes: {differ[:4]}")
        rewritten = {b for _, b in differ}
        assert any(".trim.spice" in b for b in rewritten), differ
        assert any(b.endswith('sky130_fd_pr__model__r+c.model.spice"')
                   for b in rewritten), differ
        assert all(ln.lstrip().lower().startswith(".include")
                   for _, ln in differ), (
            f"{corner}: a non-include line was rewritten: {differ}")


# ─────────────────────────────────────────────────────────────────────────────
# 2. Equivalence — the probe, and the comparison.
# ─────────────────────────────────────────────────────────────────────────────

#: Every device family the netlists instantiate, at geometries straddling the
#: regimes the models distinguish. Deliberately the same spirit as
#: `test_trimmed_lib_passives.py`'s list, widened to the fixed-width families
#: the trim also has to keep alive.
_RESISTORS = [
    ("sky130_fd_pr__res_high_po",       0.35,  2.000, 1),
    ("sky130_fd_pr__res_high_po",       0.69,  5.000, 1),
    ("sky130_fd_pr__res_high_po",       8.00, 14.785, 2),
    ("sky130_fd_pr__res_high_po",      10.00,  0.500, 1),
    ("sky130_fd_pr__res_xhigh_po",      1.00,  1.780, 1),
    ("sky130_fd_pr__res_xhigh_po",      5.73, 20.000, 1),
    ("sky130_fd_pr__res_high_po_0p35",  0.35,  4.000, 1),
    ("sky130_fd_pr__res_high_po_2p85",  2.85,  9.000, 1),
    ("sky130_fd_pr__res_xhigh_po_0p69", 0.69,  6.000, 1),
    ("sky130_fd_pr__res_xhigh_po_5p73", 5.73, 12.000, 3),
]

_CAPS = [(7.5, 7.5, 1), (30.66, 30.66, 1), (30.0, 30.0, 4), (70.5, 70.5, 1)]

#: THE ELEMENTS THAT MAKE THIS GATE NON-VACUOUS, AND WHY THEY ARE HERE.
#:
#: Measured while building this file, and it is the finding that shaped the
#: probe: **the CTLE netlists read none of the 8,909 parameters in the R/C
#: parameter decks — not the 8,823 the trim removes, and not the 86 it keeps.**
#: Blanking `typical.spice` entirely leaves a resistor + MIM + nfet probe
#: bit-identical on every printed value. The resistor parasitic reads
#: `crpf_precision`, which lives in the R/C *corner* deck this module copies
#: verbatim, not in the parameter deck.
#:
#: So a comparison over those devices alone passes no matter how much is
#: deleted — G73 exactly: a gate whose condition cannot fire is
#: indistinguishable from a deleted gate.
#:
#: The kept parameters feed `.model mc<layer> c cox={...} capsw={...}` routing
#: capacitors in `sky130_fd_pr__model__r+c.model.spice`. Instantiating one per
#: family puts every kept parameter group on a measured path, so a trim that
#: dropped one moves a printed number instead of nothing.
#:
#: **And ngspice's own reporting of this is split down the middle**, which is
#: why the elements are needed rather than trusting the simulator:
#:   * a `.model` card with an undefined parameter that NOTHING instantiates is
#:     accepted in silence and the run exits 0;
#:   * the same card, once instantiated, is `Undefined parameter [cm3d]` and
#:     `ERROR: fatal error in ngspice, exit(1)`.
#: Neither line was in `crosscheck._SILENT_FAILURE_PATTERNS` before session 19
#: — the second because it is upper-case and the `^\\s*Error[:,]` pattern was
#: anchored case-sensitively — so the harness was reading an aborted run as an
#: empty result set. Both are matched now.
_ROUTING_CAPS = [
    ("mcp1f",   2.0, 50.0),      # cp1f/cp1fsw       — poly to field
    ("mcl1f",   2.0, 50.0),      # cl1f/cl1fsw       — local interconnect
    ("mcm1d",   1.0, 30.0),      # cm1d/cm1dsw       — metal 1
    ("mcm3d",   2.0, 50.0),      # cm3d/cm3dsw       — metal 3, the MIM layer
    ("mcm5m4",  3.0, 20.0),      # cm5m4/cm5m4sw     — top metal pair
    ("mcrdlm5", 2.0, 50.0),      # crdlm5/crdlm5sw   — redistribution layer
]

#: The resistors are read at DC *and* at 10 GHz. Only the second sees the
#: `res_po` parasitic plates, and the CTLE's own AC sweep runs to 20 GHz
#: (`MAX_SEARCH_TOP_HZ`), so a DC-only probe would not be checking the library
#: at the frequencies the project actually reads it at. Measured: bending
#: `crpf_precision` by 2x moves `vr(r0)` from 4.72e-04 to 3.41e-04 and leaves
#: every DC value untouched.
_HF_HZ = "10g"

_PROBE = """* pdk_trim equivalence probe
.lib "{lib}" {sect}
{body}
.control
set noaskquit
op
{dc_prints}
ac lin 1 1meg 1meg
{lf_prints}
ac lin 1 {hf} {hf}
{hf_prints}
quit
.endc
.end
"""


def _build_probe(lib: Path, sect: str) -> str:
    body, dc_prints, lf_prints, hf_prints = [], [], [], []
    for i, (sub, w, l, m) in enumerate(_RESISTORS):
        mm = f" m={m}" if m > 1 else ""
        body.append(f"I{i} 0 r{i} 10u ac 1u")
        body.append(f"X{i} r{i} 0 0 {sub} w={w} l={l}{mm}")
        dc_prints.append(f"print v(r{i})")
        hf_prints.append(f"print vr(r{i}) vi(r{i})")
    for j, (w, l, m) in enumerate(_CAPS):
        mm = f" m={m}" if m > 1 else ""
        body.append(f"Rd{j} c{j} 0 1G")
        body.append(f"Ic{j} 0 c{j} ac 1u")
        body.append(f"Xc{j} c{j} 0 sky130_fd_pr__cap_mim_m3_1 w={w} l={l}{mm}")
        lf_prints.append(f"print vr(c{j}) vi(c{j})")
    for k, (model, w, l) in enumerate(_ROUTING_CAPS):
        body.append(f"Rp{k} p{k} 0 1G")
        body.append(f"Ip{k} 0 p{k} ac 1u")
        body.append(f"Cp{k} p{k} 0 {model} w={w} l={l}")
        lf_prints.append(f"print vr(p{k}) vi(p{k})")
    body.append("Vg g 0 0.9")
    body.append("Vd d 0 1.0")
    body.append("XM1 d g 0 0 sky130_fd_pr__nfet_01v8 W=40 L=0.15 nf=4")
    dev = "@m.xm1.msky130_fd_pr__nfet_01v8"
    dc_prints.append(f"print {dev}[gm] {dev}[gmbs] {dev}[vth] {dev}[id]")
    return _PROBE.format(lib=lib.as_posix(), sect=sect, hf=_HF_HZ,
                         body="\n".join(body), dc_prints="\n".join(dc_prints),
                         lf_prints="\n".join(lf_prints),
                         hf_prints="\n".join(hf_prints))


#: Expected number of printed values. A diff of two empty dicts passes
#: vacuously; that false pass happened once during development of
#: `test_trimmed_lib_passives.py`, which is why every comparison here is
#: guarded by a count first.
_EXPECTED_VALUES = (3 * len(_RESISTORS) + 2 * len(_CAPS)
                    + 2 * len(_ROUTING_CAPS) + 4)


def _run(netlist: str, cwd: Path) -> "tuple[dict[str, str], float]":
    """Run one probe. Returns raw printed `name = value` text, and seconds.

    The exit code is not consulted (§8 rule 10, G26/G30/G35): the output is
    grepped for warning-shaped failures and the value count is asserted.
    """
    shutil.copy(SPICE_DIR / ".spiceinit", cwd / ".spiceinit")
    (cwd / "p.cir").write_text(netlist, encoding="ascii")
    t0 = time.perf_counter()
    proc = subprocess.run([str(NGSPICE), "-b", "p.cir"], cwd=str(cwd),
                          capture_output=True, text=True, timeout=600)
    dt = time.perf_counter() - t0
    out = proc.stdout + "\n" + proc.stderr
    offenders = scan_for_silent_failures(out)
    assert not offenders, f"ngspice printed failures as warnings: {offenders[:5]}"
    return dict(re.findall(r"^(\S+)\s*=\s*(\S+)\s*$", out, flags=re.M)), dt


def _compare(sect: str, lib_a: Path, lib_b: Path,
             label_a: str, label_b: str) -> "tuple[float, float]":
    with tempfile.TemporaryDirectory() as td:
        a, ta = _run(_build_probe(lib_a, sect), Path(td))
    with tempfile.TemporaryDirectory() as td:
        b, tb = _run(_build_probe(lib_b, sect), Path(td))
    assert len(a) >= _EXPECTED_VALUES, (
        f"{label_a} produced {len(a)} values, expected >= {_EXPECTED_VALUES}; "
        f"the probe did not run, so a clean diff would be vacuous")
    assert set(a) == set(b), (
        f"different vectors: only-{label_a}={sorted(set(a) - set(b))} "
        f"only-{label_b}={sorted(set(b) - set(a))}")
    diffs = {k: (a[k], b[k]) for k in a if a[k] != b[k]}
    assert not diffs, (
        f"section {sect}: {len(diffs)} value(s) differ between {label_a} and "
        f"{label_b} — the trim is NOT free: "
        + "; ".join(f"{k}: {label_a}={x} {label_b}={y}"
                    for k, (x, y) in list(diffs.items())[:6]))
    return ta, tb


#: One section per passive corner, plus a mixed MOS×passive one. The keep-set
#: is shared across decks, so a name missing from one deck breaks that deck's
#: corner and no other — which is precisely what per-corner coverage catches.
_SECTIONS = ["tt", "ll", "hh", "hl", "lh", "ss_hh"]


@_needs_tools
@pytest.mark.parametrize("sect", _SECTIONS)
def test_trimmed_decks_are_bit_identical_to_the_pdk_decks(sect, tmp_path):
    """rel=0, abs=0 against the same library with the trim undone."""
    ref = tmp_path / "untrimmed.lib.spice"
    ref.write_text(PT.untrimmed_library_text(), encoding="ascii", newline="\n")
    t_ref, t_trim = _compare(sect, ref, PT.CTLE_LIB, "untrimmed", "trimmed")
    assert t_trim < t_ref, (
        f"the trimmed library ({t_trim:.2f} s) is not faster than the "
        f"untrimmed one ({t_ref:.2f} s) — the trim bought nothing")


@_needs_tools
@pytest.mark.parametrize("sect", _SECTIONS)
def test_one_section_libraries_are_bit_identical_to_the_monolithic_one(sect):
    """The section split must change nothing but the parse cost.

    ngspice expands every `.lib` section in a file, so the 25-section library
    costs 15x what one section costs (G78). The split is pure extraction —
    `render_section_library` copies the block verbatim and only rewrites the
    relative `pdk_trim/` includes to `../` — but "pure extraction" is a claim
    about a regex, so it is measured rather than asserted.
    """
    per_section = PT.section_library_path(sect, "sky130_ctle")
    assert per_section.exists(), (
        f"{per_section} is missing; run "
        f"`python -m nebula.device.pdk_trim --write`")
    t_mono, t_split = _compare(sect, PT.CTLE_LIB, per_section,
                               "monolithic", "one-section")
    assert t_split < t_mono, (
        f"the one-section library ({t_split:.2f} s) is not faster than the "
        f"25-section one ({t_mono:.2f} s) — the split bought nothing")


@_needs_pdk
@pytest.mark.parametrize("stem,count", sorted(PT.SPLIT_LIBRARIES.items()))
def test_every_section_has_a_one_section_library(stem, count):
    """All of them, so no corner silently falls back to the slow path."""
    sections = PT.library_sections(stem)
    assert len(sections) == count, sections
    missing = [s for s in sections
               if not PT.section_library_path(s, stem).exists()]
    assert not missing, f"{stem}: no one-section library for {missing}"
    for s in sections:
        text = PT.section_library_path(s, stem).read_text(errors="replace")
        assert len(re.findall(r"^\.lib\s+(\S+)", text, flags=re.M)) == 1, (
            f"{stem}/{s}'s file holds more than one section, which is the "
            f"whole thing it exists not to do")
        assert ".option scale=1.0u" in text, (
            f"{stem}/{s} lost `.option scale=1.0u` in the split — W=5 would "
            f"mean five METRES (G31/G36)")


@_needs_pdk
def test_the_runner_selects_the_one_section_library():
    """`lib_for_device` must actually take the fast path, for every corner.

    A generated file nothing reads is not an optimisation. This is the wiring
    check: without it the split could be perfect and unused, and the only
    symptom would be a number in a cost table that nobody could reproduce.
    """
    from nebula.device.sky130_runner import (CTLE_LIB, NFET_01V8, TRIMMED_LIB,
                                             lib_for_device)

    for corner in ("tt", "ss", "ff", "sf", "fs"):
        assert lib_for_device(NFET_01V8, real_passives=True, section=corner) \
            == PT.section_library_path(corner, "sky130_ctle")
        assert lib_for_device(NFET_01V8, section=corner) \
            == PT.section_library_path(corner, "sky130_nfet_only")
    # No section named => the monolithic library, not a crash. The fallback
    # matters: a tree that has not been regenerated must still run.
    assert lib_for_device(NFET_01V8, real_passives=True) == CTLE_LIB
    assert lib_for_device(NFET_01V8) == TRIMMED_LIB
    assert lib_for_device(NFET_01V8, section="no_such_section") == TRIMMED_LIB


@_needs_tools
@pytest.mark.slow
@pytest.mark.parametrize("sect", ["tt", "hh"])
def test_trimmed_decks_are_bit_identical_to_the_full_library(sect):
    """The outer gate, restated after the parameter trim.

    `test_trimmed_lib_passives.py` already compares against the full library,
    but it was written before `pdk_trim` existed. Keeping a leg of the chain
    here means the two files cannot drift into checking the same thing twice
    and the real thing zero times.
    """
    _compare(sect, FULL_LIB, PT.CTLE_LIB, "full", "trimmed")


# ─────────────────────────────────────────────────────────────────────────────
# 3. The gate can fail (G73).
# ─────────────────────────────────────────────────────────────────────────────


def _library_with_broken_trim(tmp_path: Path, mutate) -> Path:
    """A copy of the extended library whose `pdk_trim/` has been sabotaged.

    Relative `.include`s resolve against the directory of the file holding
    them, so dropping the library and a modified `pdk_trim/` into one temp
    directory is enough to redirect it — the real library is never touched.
    """
    shutil.copytree(PT.TRIM_DIR, tmp_path / "pdk_trim")
    mutate(tmp_path / "pdk_trim")
    lib = tmp_path / "broken.lib.spice"
    lib.write_text(PT.CTLE_LIB.read_text(), encoding="ascii", newline="\n")
    return lib


def _reference_library(tmp_path: Path) -> Path:
    ref = tmp_path / "untrimmed.lib.spice"
    ref.write_text(PT.untrimmed_library_text(), encoding="ascii", newline="\n")
    return ref


@_needs_tools
def test_a_trim_that_dropped_a_kept_parameter_is_caught(tmp_path):
    """Delete one kept parameter and watch the comparison go red.

    Once `mcm3d` is instantiated — which is why `_ROUTING_CAPS` exists — the
    missing name is fatal: `Undefined parameter [cm3d]`, `ERROR: fatal error in
    ngspice, exit(1)`. Neither line was matched by
    `crosscheck.scan_for_silent_failures` until session 19, so this run used to
    come back as a clean, empty result set. Asserting on the *scan* rather than
    on the value diff is deliberate: it pins the guard, not just the outcome.
    """
    def drop_cm3d(d: Path) -> None:
        deck = d / "typical.trim.spice"
        lines = deck.read_text().splitlines()
        kept = [ln for ln in lines if not re.match(r"\.param\s+cm3d\s*=", ln)]
        assert len(kept) == len(lines) - 1, (
            "`cm3d` is no longer a kept parameter; pick another name from the "
            "keep-set rather than deleting this test")
        deck.write_text("\n".join(kept) + "\n", encoding="ascii", newline="\n")

    broken = _library_with_broken_trim(tmp_path, drop_cm3d)
    with pytest.raises(AssertionError, match="printed failures as warnings"):
        _compare("tt", _reference_library(tmp_path), broken, "untrimmed", "broken")


def test_the_silent_failure_scan_catches_an_undefined_parameter():
    """The `crosscheck` half of the above, without needing ngspice.

    Verbatim output from the run the test above provokes. Both lines used to
    pass the scan: `Undefined parameter` was not listed at all, and
    `ERROR: fatal error` missed the `^\\s*Error[:,]` pattern on case.
    """
    text = ("Undefined parameter [cm3d]\n"
            "ERROR: fatal error in ngspice, exit(1)\n")
    offenders = scan_for_silent_failures(text)
    assert len(offenders) == 2, offenders


@_needs_tools
def test_a_corner_deck_with_an_edited_process_constant_is_caught(tmp_path):
    """The other half: the copied R/C deck, not the trimmed parameter deck.

    `crpf_precision` sets the poly resistor's parasitic plate capacitance and
    is one of the constants `render_rc_corner` copies verbatim. A generated
    file that had drifted from the PDK would be invisible to the parameter
    tests above, so it gets its own falsification.
    """
    def bend_crpf(d: Path) -> None:
        deck = d / "res_typical__cap_typical.spice"
        text = deck.read_text()
        new = re.sub(r"(crpf_precision\s*=\s*)1\.06e-04", r"\g<1>2.06e-04", text)
        assert new != text, "crpf_precision is no longer in the copied deck"
        deck.write_text(new, encoding="ascii", newline="\n")

    broken = _library_with_broken_trim(tmp_path, bend_crpf)
    with pytest.raises(AssertionError, match="differ between"):
        _compare("tt", _reference_library(tmp_path), broken, "untrimmed", "broken")
