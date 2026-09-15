"""
experiments/prescreen.py — task 7e. **Does physics alone solve this?**

WHY THIS IS THE PIVOTAL EXPERIMENT AND NOT AN OPTIMISATION
-----------------------------------------------------------
Every method in `baselines.py` spends its budget on ngspice, and 99.7 % of a
run is ngspice (session 17). A filter that rejects a design *before* the
simulator runs is therefore not a small saving — it is a change to what the
project can claim:

    if the pre-screen raises the effective yield above roughly 50 %, physics
    largely solves the nominal problem, no learned method is needed for
    SEARCH, and the RL contribution must rest entirely on amortisation across
    spec targets.

That is a conclusion the project needs in August, not in September, which is
why this module exists before the sweep it wraps.

WHAT IT PREDICTS, AND WHICH PARTS ARE FREE
-------------------------------------------
The S2 topology is one zero and two poles (CLAUDEwa.md §6):

    f_z  = 1 / (2 pi Rs Cs)                     EXACT — passives only
    f_p1 = k / (2 pi Rs Cs)                     needs gm
    f_p2 = 1 / (2 pi RL CL)                     EXACT — passives only
    k    = 1 + (gm + gmbs) Rs / 2

Two of the three are **exact functions of the design vector**: they contain no
device quantity at all, so they cost nothing and cannot be wrong. Only `f_p1`
needs a transconductance, and that is where the two calibrations below live.

**THE PEAK IS COMPUTED, NOT ASSUMED.** Session 10b pre-registered "the peak of
a 1-zero/2-pole response sits near f_p2, so cl = 50 fF must give zero S3
yield"; the measurement came back at 8.73 % and the prediction is recorded as a
miss in `PREDICTIONS.md`. So `predict_response` maximises the **full**
magnitude expression numerically over a log grid. No asymptote, no
`20*log10(k)`, no "the peak is at the geometric mean".

THE TWO CALIBRATIONS, AND WHY NEITHER IS A FUDGE FACTOR
--------------------------------------------------------
**1. gm from the design vector (`GM_LOG_BETA`).** At screen time there is no
`.op`, so `gm` has to come from somewhere. It comes from the standard gm/I_D
characterisation: for a given device, `gm/I_D` is a function of the inversion
level `J = I_D / (W/L)` and of `L`. That is a property of the TRANSISTOR, not
of this circuit, which is why one fit transfers across the box. Fitted once,
by least squares, on the **1890 already-paid-for TT operating points** in
`robust_geometry_data.csv` — no new simulation was run to produce it.

**2. The G60 correction (`K_ALPHA`).** G60, measured in session 16:

    "§6's design equations over-predict the Nyquist boost by 0.8-1.5 dB, and
     the error GROWS with Rs ... it neglects r_o, so the degeneration factor k
     comes out too large ... never integrate a waveform through
     `deq.predict()`. Calibrate first."

`f_z` and `f_p2` are exact, so — exactly as G60 prescribes — **only `k` is
fitted**, and it is fitted as ONE scalar:

    k_eff = 1 + K_ALPHA * (gm + gmbs) * Rs / 2

`K_ALPHA` < 1 is the r_o shunt that §6 omits. It was chosen by minimising the
median absolute percent error of the predicted `f_peak` against `meas ac MAX`
over the same 1890 points, and the peaking bias it produces is reported beside
it rather than being a second free parameter.

**The uncalibrated equations must not be used here** and using them is not a
matter of taste: at `K_ALPHA = 1.0` the same predictor scores 7.0 % MdAPE on
f_peak against 4.3 % calibrated, and biases peaking by +0.36 dB — the direction
and rough size G60 measured on a different experiment.

WHAT THE SCREEN IS ALLOWED TO DO
---------------------------------
Reject, never accept-with-confidence. A rejected design is not simulated, so a
FALSE rejection is unrecoverable — the design is gone from the run — while a
false acceptance costs one simulation and is then caught by the real evaluator.
The two errors are not symmetric and the widening below is set from that:

    the accept window is S3's window widened by the measured 99th percentile
    of the predictor's own error

which is a **rule**, not a number chosen to make the result look good
(CLAUDEwa.md §8 rule 6 forbids an agent picking a spec-tightness heuristic; a
quantile of a measured error distribution is not a picked number, and the
quantile itself is stated here and in `BASELINES.md`).

The screen deliberately tests **only S3's two axes**. S5 (noise) and S6 (power)
are met by 90.7 % of the box and screening on them would buy nothing;
saturation needs a bias solve, which is the simulator's job.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np

from nebula.common.types import SPEC_F_PEAK_HZ_RANGE, SPEC_PEAKING_DB_RANGE
from nebula.device.passives import to_geometry

HERE = Path(__file__).resolve().parent

#: The already-paid-for calibration set: 1890 Latin-hypercube box samples with
#: `.op` primitives and `meas ac MAX` output, from session 11's corner study.
#: Tracked (G49), so the fit below is reproducible from the repo alone.
CALIBRATION_CSV: Path = HERE / "robust_geometry_data.csv"


# ─────────────────────────────────────────────────────────────────────────────
# 1. gm from the design vector — the gm/I_D characterisation.
# ─────────────────────────────────────────────────────────────────────────────

#: Feature order for the gm/I_D fit. `J = I_D / (W/L)` is the inversion level.
#: `nf` is in the basis because G38 measured a +/-10 % non-monotonic finger
#: effect on gm; one log term cannot capture "non-monotonic", and it is not
#: expected to — it is there so the fit is not biased by the calibration set's
#: nf distribution, and the residual it leaves is reported.
GM_FEATURES: tuple[str, ...] = ("1", "logJ", "logJ^2", "logL", "logJ*logL", "lognf")

#: Least-squares coefficients for `log(gm / I_D)` in `GM_FEATURES` order,
#: fitted on all 1890 rows of `CALIBRATION_CSV`. Reproduced exactly by
#: `fit_gm_model()`; `tests/test_prescreen.py` refits and asserts agreement, so
#: a stale constant here cannot survive a change to the data.
GM_LOG_BETA: tuple[float, ...] = (
    -5.223881693399291,
    -1.4982367695273915,
    -0.068146205352423,
    0.6017196819889942,
    0.04584089520927792,
    -0.007339390530293541,
)

#: `gmbs / gm` as an affine function of `(1, logJ, logL)`, same fit set.
#: Measured spread on the calibration set: 0.128 to 0.214 (5th-95th pct).
#: The body effect is NOT optional — CLAUDEwa.md §6's correction, and omitting
#: it moves `k` by up to 20 % here.
GMBS_RATIO_BETA: tuple[float, ...] = (
    0.6765503607146137,
    0.011734346596352755,
    0.02452832979676892,
)


def _gm_features(w_m: float, l_m: float, nf: float, i_bias_a: float) -> np.ndarray:
    """`(1, logJ, logJ^2, logL, logJ*logL, log nf)` for one design.

    `I_D` is HALF the total bias current: `i_bias` is the tail current for the
    whole differential pair and each side carries half of it. Getting this
    wrong is a factor of two in the inversion level and it would not announce
    itself, so it is written once, here.
    """
    i_d = 0.5 * float(i_bias_a)
    j = i_d / (float(w_m) / float(l_m))
    lj, ll = math.log(j), math.log(float(l_m))
    return np.array([1.0, lj, lj * lj, ll, lj * ll, math.log(float(nf))])


def predict_gm(params: Mapping[str, float]) -> tuple[float, float]:
    """`(gm, gmbs)` of ONE input device, siemens, from the design vector alone.

    No simulation. This is the only place in the pre-screen where a device
    quantity is guessed rather than computed, and its measured error is
    reported in `BASELINES.md` (median 2.4 %, p90 7.6 %, p99 24.1 % on the
    calibration set) so that the f_peak error can be attributed.
    """
    x = _gm_features(params["w_in"], params["l_in"], params.get("nf_in", 4.0),
                     params["i_bias"])
    i_d = 0.5 * float(params["i_bias"])
    gm = float(np.exp(x @ np.asarray(GM_LOG_BETA)) * i_d)
    ratio = float(np.asarray(GMBS_RATIO_BETA) @ x[[0, 1, 3]])
    return gm, max(0.0, ratio) * gm


# ─────────────────────────────────────────────────────────────────────────────
# 2. The G60 correction and the response prediction.
# ─────────────────────────────────────────────────────────────────────────────

#: The r_o shunt §6 omits, as a single scalar on the degeneration term.
#:
#: **Fitted exactly the way G60 prescribes, and no other way.** G60: "`f_z` and
#: `f_p2` are EXACT (passives), `g_dc` comes from the measurement, and only `k`
#: is fitted, from the measured boost. Then the peaking and the peak frequency
#: are INDEPENDENT checks." So `K_ALPHA` is chosen to make the MEDIAN predicted
#: peaking bias zero over the calibration set — nothing about `f_peak` enters
#: the fit — and the f_peak error is then a check that was not optimised for.
#:
#:     alpha   median peaking bias   f_peak MdAPE (the independent check)
#:     0.875        -0.068 dB               5.24 %
#:     0.900        -0.009 dB               4.93 %     <- chosen
#:     0.950        +0.118 dB               4.91 %
#:     1.000        +0.267 dB               5.53 %     <- §6 verbatim
#:
#: `K_ALPHA = 1.0` IS the uncalibrated §6 equation, and 7e forbids using it
#: here. Its bias is +0.27 dB on this population — the same direction as G60's
#: +0.77 to +1.47 dB, measured on a different experiment whose designs sat at
#: higher `Rs`, which is where G60 says the error grows.
K_ALPHA: float = 0.90

#: The grid `predict_response` maximises |H| on. Its top is
#: `evaluator.F_PEAK_HZ_LIMITS[1]`-shaped for a reason: `meas ac MAX` searches
#: to 20 GHz and reports the EDGE when the response is still rising (G44), so a
#: predictor searching a different range would disagree with the measurement
#: for a reason that has nothing to do with physics.
GRID_LO_HZ: float = 1e7
GRID_HI_HZ: float = 2e10
GRID_N: int = 1200

_GRID = np.logspace(math.log10(GRID_LO_HZ), math.log10(GRID_HI_HZ), GRID_N)

#: `evaluator.F_PEAK_HZ_LIMITS[1]`, imported rather than restated (rule 9): the
#: frequency above which a reported peak is the sweep edge and not a peak.
from nebula.rl.evaluator import F_PEAK_HZ_LIMITS as _F_PEAK_LIMITS

_MEAS_TOP_HZ: float = _F_PEAK_LIMITS[1]


@dataclass(frozen=True)
class Prediction:
    """One design's predicted AC response. Costs zero simulations."""

    f_zero_hz: float
    f_pole1_hz: float
    f_pole2_hz: float
    f_peak_hz: float
    peaking_db: float
    nyq_boost_db: float
    k_eff: float
    gm_s: float
    gmbs_s: float
    #: True when the predicted peak sits at or above the top of the range
    #: `meas ac MAX` searches, so the SIMULATOR would report the sweep edge and
    #: `evaluator.validate` would reject the result as fictitious. This is
    #: G44's mechanism predicted ANALYTICALLY. 78 % of everything session 17's
    #: policy found was exactly this class of design (G65).
    #:
    #: **It is a RANGE test, not an argmax test, and that distinction is a
    #: correction.** A one-zero/two-pole magnitude falls as 1/f eventually, so
    #: its maximum is ALWAYS interior and an argmax-at-the-grid-edge test can
    #: never fire — it fired zero times on 1890 designs, which is how the
    #: mistake was found. What the simulator reports as an edge is a peak above
    #: its own 20 GHz search top.
    #:
    #: **Measured: this flag also fires zero times on the calibration set**,
    #: because the predicted peak of every one of the 579 no-interior-peak
    #: designs still lands below 18 GHz — just far outside S3's window, where
    #: the f_peak test catches it instead. So the G44 population IS removed for
    #: free (see `accuracy()['g44_free_rejection_rate']`) but under the f_peak
    #: label, and this flag is a belt-and-braces that has never been needed.
    peak_is_grid_edge: bool

    @property
    def f_peak_oct(self) -> float:
        """Octaves relative to Nyquist, the unit every other result uses."""
        from nebula.rl.contract import f_peak_octaves

        return f_peak_octaves(self.f_peak_hz)


def _mag(f: np.ndarray, fz: float, fp1: float, fp2: float) -> np.ndarray:
    return (np.sqrt(1.0 + (f / fz) ** 2)
            / (np.sqrt(1.0 + (f / fp1) ** 2) * np.sqrt(1.0 + (f / fp2) ** 2)))


def predict_response(params: Mapping[str, float],
                     drawn: bool = True) -> Prediction:
    """The design vector -> its predicted response. **No SPICE.**

    `drawn=True` quantises `rs`, `cs`, `rl` onto real SKY130 devices first and
    adds half the load resistor's `res_po` bottom plate to `cl`, which is G66's
    mechanism: measured at **+1.4 to +24.3 fF on a 32.6 fF cl, up to +75 %**,
    always in the same direction. A predictor fed the REQUESTED passives would
    therefore be biased in a known direction by a known amount, for free — so
    it is not.

    `to_geometry` is pure Python and costs 0.036 ms, so this stays free.
    """
    rs = float(params["rs"])
    cs = float(params["cs"])
    rl = float(params["rl"])
    cl = float(params["cl"])
    if drawn:
        try:
            geo = to_geometry(rs, cs, rl)
        except ValueError:
            # An undrawable geometry is the evaluator's `unrealisable geometry`
            # invalidity, reached without SPICE. Predict on the request rather
            # than raising: the screen's caller decides what to do about it,
            # and `accept()` rejects it by name.
            geo = None
        if geo is not None:
            rs = geo.rs.r_actual_ohm
            cs = geo.cs.c_actual_f
            rl = geo.rl.r_actual_ohm
            cl = cl + 0.5 * geo.rl.parasitic_to_bulk_f()

    # A non-positive passive is a PROGRAMMING error, not a policy move: `rs`,
    # `cs` and `rl` are log-scaled box axes with positive floors and `cl` is
    # CONTEXT. So this raises rather than returning a named invalidity, which
    # is the opposite of `evaluator.evaluate`'s contract and deliberately so.
    for nm, v in (("rs", rs), ("cs", cs), ("rl", rl), ("cl", cl)):
        if not (math.isfinite(v) and v > 0.0):
            raise ValueError(f"prescreen: {nm} = {v!r} must be positive and "
                             f"finite; it is not something a policy can choose")

    gm, gmbs = predict_gm(params)
    k = 1.0 + K_ALPHA * (gm + gmbs) * rs / 2.0
    fz = 1.0 / (2.0 * math.pi * rs * cs)
    fp1 = k * fz
    fp2 = 1.0 / (2.0 * math.pi * rl * cl)

    h = _mag(_GRID, fz, fp1, fp2)
    j = int(np.argmax(h))
    f_peak = float(_GRID[j])
    # `meas ac MAX` searches to MAX_SEARCH_TOP_HZ and reports its own edge when
    # the response has not turned over inside it. `evaluator.F_PEAK_HZ_LIMITS`
    # rejects anything above 1.8e10 for that reason, so the predictor uses the
    # SAME number rather than a second opinion about where the edge is.
    edge = bool(f_peak >= _MEAS_TOP_HZ)
    peaking_db = float(20.0 * math.log10(h[j] / h[0]))
    from nebula.common.types import NYQUIST_HZ
    nyq = float(_mag(np.array([NYQUIST_HZ]), fz, fp1, fp2)[0])
    nyq_boost_db = float(20.0 * math.log10(nyq / h[0]))

    return Prediction(
        f_zero_hz=fz, f_pole1_hz=fp1, f_pole2_hz=fp2, f_peak_hz=f_peak,
        peaking_db=peaking_db, nyq_boost_db=nyq_boost_db, k_eff=k,
        gm_s=gm, gmbs_s=gmbs, peak_is_grid_edge=edge)


# ─────────────────────────────────────────────────────────────────────────────
# 3. The screen.
# ─────────────────────────────────────────────────────────────────────────────

#: Widening of S3's window, in octaves and dB, applied to the ACCEPT test.
#:
#: **Set by a stated rule against a declared cost, not chosen.** The rule is:
#: the smallest pair on `margin_scan`'s ladder whose measured FALSE-rejection
#: rate is at or below `FALSE_REJECTION_BUDGET` = 1 %. Measured on the
#: calibration set (1890 designs, 254 of them meeting S3):
#:
#:     widening      free rejection   false rejection   effective S3 yield
#:     0.00 / 0.0        85.2 %        15.75 % (40)         76.4 %
#:     0.10 / 0.5        80.1 %         4.72 % (12)         64.4 %
#:     0.20 / 1.0        75.6 %         3.54 %  (9)         53.0 %
#:     0.30 / 1.5        69.0 %         1.57 %  (4)         42.7 %
#:     0.40 / 2.0        61.7 %         0.39 %  (1)         34.9 %   <- chosen
#:     0.75 / 3.0        42.9 %         0.00 %  (0)         23.5 %
#:
#: **Read that table before quoting any single number from it.** The screen
#: can be made to clear 7e's 50 % effective-yield threshold — but only at a
#: widening that throws away 17 % of the designs that actually meet S3, and a
#: rejected design is gone from the run for good while a false acceptance costs
#: one simulation and is then caught by the evaluator. The two errors are not
#: symmetric, which is the whole argument for erring outward.
MARGIN_OCT: float = 0.40
MARGIN_DB: float = 2.00


@dataclass(frozen=True)
class ScreenVerdict:
    accept: bool
    reason: Optional[str]
    prediction: Optional[Prediction]


def screen(params: Mapping[str, float],
           margin_oct: float = MARGIN_OCT,
           margin_db: float = MARGIN_DB,
           target_f_peak_hz: Optional[float] = None) -> ScreenVerdict:
    """Accept or reject one design **before any simulation**.

    Three rejection reasons, in the order that names the mechanism rather than
    a symptom — the same discipline `evaluator.validate` uses, and for the same
    reason (session 17: checked the other way round, 159 of 203 invalidities
    were reported under the wrong label):

      1. `unrealisable_geometry` — `to_geometry` cannot draw it. Free and
         certain; the evaluator would return exactly this.
      2. `predicted_sweep_edge`  — |H| is still rising at 20 GHz, so the
         circuit has no interior peak at all. G44/G65's mechanism, predicted.
      3. `predicted_f_peak` / `predicted_peaking` — a real peak, in the wrong
         place or of the wrong size, by more than the predictor's own p99
         error.
    """
    try:
        to_geometry(float(params["rs"]), float(params["cs"]), float(params["rl"]))
    except (ValueError, KeyError) as exc:
        return ScreenVerdict(False, f"unrealisable_geometry: {exc}", None)

    p = predict_response(params)
    if p.peak_is_grid_edge:
        return ScreenVerdict(False, "predicted_sweep_edge: |H| is still rising "
                                    "at 20 GHz, so there is no interior peak "
                                    "(G44's mechanism, predicted)", p)

    lo_hz, hi_hz = SPEC_F_PEAK_HZ_RANGE
    centre = math.sqrt(lo_hz * hi_hz) if target_f_peak_hz is None else float(target_f_peak_hz)
    half_oct = 0.5 * math.log2(hi_hz / lo_hz)
    off = abs(math.log2(p.f_peak_hz / centre))
    if off > half_oct + margin_oct:
        return ScreenVerdict(False, f"predicted_f_peak: {p.f_peak_hz / 1e9:.3f} GHz "
                                    f"is {off:.3f} octaves off centre, against "
                                    f"{half_oct:.2f} + {margin_oct:.2f}", p)

    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    if not (pk_lo - margin_db <= p.peaking_db <= pk_hi + margin_db):
        return ScreenVerdict(False, f"predicted_peaking: {p.peaking_db:.2f} dB "
                                    f"outside [{pk_lo - margin_db:.2f}, "
                                    f"{pk_hi + margin_db:.2f}]", p)
    return ScreenVerdict(True, None, p)


def accept(params: Mapping[str, float], **kw) -> bool:
    return screen(params, **kw).accept


# ─────────────────────────────────────────────────────────────────────────────
# 4. Calibration and accuracy, from the tracked CSV. No new simulation.
# ─────────────────────────────────────────────────────────────────────────────


def _load_calibration(path: Path = CALIBRATION_CSV) -> dict:
    with Path(path).open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise ValueError(f"{path} is empty")
    col = lambda k: np.array([float(r[k]) for r in rows])
    return {k: col(k) for k in
            ("w_in", "l_in", "nf_in", "i_bias", "rs", "cs", "rl", "cl",
             "vcm_in", "gm", "gmbs", "id_a", "f_pk_hz", "peaking_db",
             "g_pk_db", "g_top_db", "g_dc_db", "g_nyq_db")}


def fit_gm_model(d: Optional[dict] = None) -> tuple[np.ndarray, np.ndarray]:
    """Refit `GM_LOG_BETA` and `GMBS_RATIO_BETA`. Deterministic least squares."""
    d = _load_calibration() if d is None else d
    n = len(d["gm"])
    X = np.empty((n, len(GM_FEATURES)))
    for i in range(n):
        X[i] = _gm_features(d["w_in"][i], d["l_in"][i], d["nf_in"][i],
                            d["i_bias"][i])
    beta, *_ = np.linalg.lstsq(X, np.log(d["gm"] / (0.5 * d["i_bias"])), rcond=None)
    Xb = X[:, [0, 1, 3]]
    bb, *_ = np.linalg.lstsq(Xb, d["gmbs"] / d["gm"], rcond=None)
    return beta, bb


#: The `meas ac MAX` guard the calibration set has to be read through. A row
#: whose reported peak IS the sweep edge is not a measurement of a peak (G44),
#: so it cannot score a f_peak predictor — it is scored as a REJECTION target
#: instead, which is where most of the screen's value turns out to be.
def _has_interior_peak(d: dict) -> np.ndarray:
    return (d["g_pk_db"] - d["g_top_db"] > 0.25) & (d["f_pk_hz"] < 1.8e10) \
        & (d["f_pk_hz"] > 1e7)


def accuracy(path: Path = CALIBRATION_CSV, k_alpha: float = K_ALPHA,
             margin_oct: float = MARGIN_OCT,
             margin_db: float = MARGIN_DB) -> dict:
    """7e's numbers: MdAPE, free-rejection rate, false-rejection rate.

    Every row of the calibration set is a design that WAS simulated, so both
    error rates are measured rather than assumed. The band restriction to
    0.5-5 GHz is 7e's: it is the region near S3's decision boundary and the
    only region where an f_peak error changes an outcome.
    """
    d = _load_calibration(path)
    n = len(d["gm"])
    preds, screens = [], []
    for i in range(n):
        p = {k: d[k][i] for k in ("w_in", "l_in", "nf_in", "i_bias", "rs",
                                  "cs", "rl", "cl", "vcm_in")}
        preds.append(_predict_with_alpha(p, k_alpha))
        screens.append(screen(p, margin_oct=margin_oct, margin_db=margin_db))

    f_hat = np.array([p.f_peak_hz for p in preds])
    pk_hat = np.array([p.peaking_db for p in preds])
    interior = _has_interior_peak(d)
    band = interior & (d["f_pk_hz"] >= 0.5e9) & (d["f_pk_hz"] <= 5.0e9)

    ape = np.abs(f_hat - d["f_pk_hz"]) / d["f_pk_hz"]
    oct_err = np.log2(f_hat / d["f_pk_hz"])
    pk_err = pk_hat - d["peaking_db"]

    # S3 truth, as the evaluator would read it: an interior peak, in the
    # window, with peaking in band. This is the quantity the screen predicts.
    lo, hi = SPEC_F_PEAK_HZ_RANGE
    pk_lo, pk_hi = SPEC_PEAKING_DB_RANGE
    s3_true = (interior & (d["f_pk_hz"] >= lo) & (d["f_pk_hz"] <= hi)
               & (d["peaking_db"] >= pk_lo) & (d["peaking_db"] <= pk_hi))
    acc = np.array([s.accept for s in screens])

    reasons: dict = {}
    for s in screens:
        if not s.accept:
            key = (s.reason or "?").split(":")[0]
            reasons[key] = reasons.get(key, 0) + 1

    n_acc = int(acc.sum())
    return {
        "n": n,
        "n_interior_peak": int(interior.sum()),
        "k_alpha": k_alpha,
        "margin_oct": margin_oct, "margin_db": margin_db,
        # --- predictor accuracy -------------------------------------------
        "f_peak_mdape_global": float(np.median(ape[interior])),
        "f_peak_mdape_band": float(np.median(ape[band])),
        "f_peak_p90_ape_global": float(np.percentile(ape[interior], 90)),
        "f_peak_abs_oct_p99": float(np.percentile(np.abs(oct_err[interior]), 99)),
        "f_peak_oct_bias": float(np.median(oct_err[interior])),
        "n_band": int(band.sum()),
        "peaking_mae_db": float(np.median(np.abs(pk_err[interior]))),
        "peaking_bias_db": float(np.median(pk_err[interior])),
        "peaking_abs_db_p99": float(np.percentile(np.abs(pk_err[interior]), 99)),
        # --- the screen ----------------------------------------------------
        "accept_rate": n_acc / n,
        "free_rejection_rate": 1.0 - n_acc / n,
        "reject_reasons": reasons,
        "s3_base_rate": float(s3_true.mean()),
        # False rejection: a design that MEETS S3 and the screen threw away.
        # Unrecoverable, and the reason the widening rule errs outward.
        "false_rejection_rate": float((s3_true & ~acc).sum() / max(int(s3_true.sum()), 1)),
        "n_false_rejected": int((s3_true & ~acc).sum()),
        "n_s3_true": int(s3_true.sum()),
        # The headline: the S3 rate AMONG ACCEPTED designs. This is "effective
        # yield" and 7e's >50 % threshold applies to it.
        "effective_yield": float(s3_true[acc].mean()) if n_acc else float("nan"),
        "yield_lift": (float(s3_true[acc].mean() / s3_true.mean())
                       if n_acc and s3_true.mean() > 0 else float("nan")),
        # --- the G44 population, cross-tabulated ---------------------------
        # 78 % of everything session 17's policy found was a fictitious peak at
        # the sweep edge (G65), each of which cost a full simulation. This is
        # the fraction of that population the screen removes for free, and it
        # is reported separately because it is a different claim from "the
        # screen raises the yield": it says the screen removes the class of
        # design the evaluator would have had to reject anyway.
        "n_no_interior_peak": int((~interior).sum()),
        "g44_free_rejection_rate": float((~interior & ~acc).sum()
                                         / max(int((~interior).sum()), 1)),
        "n_g44_accepted": int((~interior & acc).sum()),
    }


def _predict_with_alpha(params: Mapping[str, float], k_alpha: float) -> Prediction:
    """`predict_response` at an arbitrary `K_ALPHA`, for the calibration scan."""
    global K_ALPHA
    old = K_ALPHA
    try:
        K_ALPHA = float(k_alpha)
        return predict_response(params)
    finally:
        K_ALPHA = old


def alpha_scan(alphas: Sequence[float] = tuple(np.arange(0.60, 1.05, 0.025)),
               path: Path = CALIBRATION_CSV) -> list[dict]:
    """The G60 calibration, as a table. `alpha = 1.0` is §6 verbatim."""
    out = []
    for a in alphas:
        r = accuracy(path, k_alpha=float(a))
        out.append({"k_alpha": float(a),
                    "f_peak_mdape_global": r["f_peak_mdape_global"],
                    "f_peak_mdape_band": r["f_peak_mdape_band"],
                    "peaking_bias_db": r["peaking_bias_db"],
                    "effective_yield": r["effective_yield"],
                    "false_rejection_rate": r["false_rejection_rate"]})
    return out


#: The false-rejection rate the widening rule is allowed to spend. **A declared
#: cost, not a tuned threshold**: a screen that discards feasible designs is
#: worse than no screen (7e), so the rule fixes what fraction of them may be
#: lost and then reports the free rejection that buys.
FALSE_REJECTION_BUDGET: float = 0.01


def margin_scan(margins: Sequence[tuple[float, float]] = (
        (0.0, 0.0), (0.1, 0.5), (0.2, 1.0), (0.3, 1.5), (0.4, 2.0),
        (0.5, 2.5), (0.75, 3.0), (1.0, 4.0)),
        path: Path = CALIBRATION_CSV) -> list[dict]:
    """The widening trade-off, as a table a human can read and overrule.

    CLAUDEwa.md §8 rule 6 forbids an agent choosing a spec-tightness heuristic.
    So this reports the whole curve — what each widening costs in feasible
    designs and buys in skipped simulations — and `MARGIN_OCT`/`MARGIN_DB` are
    the smallest pair on it whose false-rejection rate is at or below
    `FALSE_REJECTION_BUDGET`, which is the stated rule.
    """
    out = []
    for mo, md in margins:
        r = accuracy(path, margin_oct=mo, margin_db=md)
        out.append({"margin_oct": mo, "margin_db": md,
                    "free_rejection_rate": r["free_rejection_rate"],
                    "false_rejection_rate": r["false_rejection_rate"],
                    "n_false_rejected": r["n_false_rejected"],
                    "effective_yield": r["effective_yield"],
                    "yield_lift": r["yield_lift"]})
    return out


def accuracy_from_log(path, problem: str = "P1",
                      margin_oct: float = MARGIN_OCT,
                      margin_db: float = MARGIN_DB) -> dict:
    """Re-measure the screen on a BENCHMARK RUN LOG, not the calibration set.

    **This is the transfer test, and it is the reason it exists as a function
    rather than as a paragraph.** The calibration set (`robust_geometry_data.
    csv`) sits at `cl` = 150 fF with `nf_in` varying 1-8 and IDEAL R/C
    elements. The benchmark runs `nf_in` = 4 at `cl_mid` = 32.63 fF with DRAWN
    passives and a real current mirror. Those are different populations, and
    `PREDICTIONS.md` entry 6 pre-registered "the calibration does not transfer"
    as falsification condition 2.

    Only UNSCREENED rows are read: a screened arm's evaluations are the
    accepted subset by construction, so measuring the screen on them would be
    measuring it on its own output.
    """
    import json
    from pathlib import Path as _P

    rows = []
    for line in _P(path).open("r", encoding="utf-8"):
        d = json.loads(line)
        if (d.get("event") == "trial" and not d.get("prescreen")
                and d.get("problem") == problem
                and d.get("role", "measured") == "measured"):
            rows.append(d)
    if not rows:
        raise ValueError(f"{path} has no unscreened {problem} trials")

    valid = [r for r in rows if r.get("verdict") == "valid" and r.get("predicted")]
    f_hat = np.array([r["predicted"]["f_peak_hz"] for r in valid])
    pk_hat = np.array([r["predicted"]["peaking_db"] for r in valid])
    f_true = np.array([2.5e9 * 2 ** r["meas"]["f_peak_oct"] for r in valid])
    pk_true = np.array([r["meas"]["peaking_db"] for r in valid])
    ape = np.abs(f_hat - f_true) / f_true
    band = (f_true >= 0.5e9) & (f_true <= 5.0e9)

    target = math.sqrt(SPEC_F_PEAK_HZ_RANGE[0] * SPEC_F_PEAK_HZ_RANGE[1])
    acc = np.array([screen(r["params"], margin_oct=margin_oct,
                           margin_db=margin_db,
                           target_f_peak_hz=target).accept for r in rows])
    feas = np.array([bool(r["feasible"]) for r in rows])
    return {
        "source": str(path), "problem": problem, "n": len(rows),
        "n_valid": len(valid),
        "f_peak_mdape_global": float(np.median(ape)) if len(ape) else float("nan"),
        "f_peak_mdape_band": (float(np.median(ape[band])) if band.any()
                              else float("nan")),
        "peaking_mae_db": float(np.median(np.abs(pk_hat - pk_true))),
        "peaking_bias_db": float(np.median(pk_hat - pk_true)),
        "free_rejection_rate": float(1.0 - acc.mean()),
        # NOTE this is feasibility under reward v1's SEVEN rows, not S3 alone,
        # so it is not the same quantity `accuracy()` reports and the two are
        # labelled differently everywhere they appear.
        "feasible_base_rate": float(feas.mean()),
        "false_rejection_rate": (float((feas & ~acc).sum() / feas.sum())
                                 if feas.sum() else float("nan")),
        "n_false_rejected": int((feas & ~acc).sum()),
        "n_feasible": int(feas.sum()),
        "effective_yield": (float(feas[acc].mean()) if acc.sum()
                            else float("nan")),
        "yield_lift": (float(feas[acc].mean() / feas.mean())
                       if acc.sum() and feas.mean() > 0 else float("nan")),
        "within_budget": bool((feas & ~acc).sum() / feas.sum()
                              <= FALSE_REJECTION_BUDGET) if feas.sum() else None,
    }


__all__: Sequence[str] = (
    "Prediction", "ScreenVerdict", "FALSE_REJECTION_BUDGET", "margin_scan",
    "accuracy_from_log",
    "GM_LOG_BETA", "GMBS_RATIO_BETA", "GM_FEATURES", "K_ALPHA",
    "MARGIN_OCT", "MARGIN_DB", "CALIBRATION_CSV",
    "predict_gm", "predict_response", "screen", "accept",
    "fit_gm_model", "accuracy", "alpha_scan",
)
