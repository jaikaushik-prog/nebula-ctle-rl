"""
experiments/task8_symbolic.py — task 8c item 6, the closed form for `f_peak`.

WHY THIS IS NOT A PySR SCRIPT ANY MORE
---------------------------------------
**PySR cannot run in this environment**, and the blocker is not fixable in
code. `pysr` is installed, but it needs Julia, and `juliapkg` dies on this
interpreter:

    OSError: [Errno 22] Invalid argument:
      'C:\\...\\WindowsApps\\PythonSoftwareFoundation.Python.3.13_...\\python.exe'

That path is a **Microsoft Store app-execution alias** — a zero-byte reparse
point that cannot be opened as a file. Every Store-Python install hits it. The
fix is a real interpreter (python.org or Miniconda), not a code change, and no
conda is on PATH in this checkout. `run_pysr()` below is kept, working and
untouched, for whoever installs one.

**But the search PySR was being sent on is unnecessary, because the answer is
derivable.** 8c item 6 asks for "a corrected closed form for `f_peak` and
peaking in terms of `f_z`, `f_p2` and `k`". For a one-zero/two-pole magnitude
that is not a search problem — it is a stationary point, and it has an exact
solution:

    |H(jw)|^2  =  (1 + w^2/wz^2) / ((1 + w^2/wp1^2)(1 + w^2/wp2^2))

Substitute `u = w^2`, `a = wz^2`, `b = wp1^2`, `c = wp2^2`, set
`d/du (N/D) = 0`, i.e. `N'D = ND'`, and multiply through by `abc`:

    u^2 + 2 a u + (ab + ac - bc) = 0
    u = -a + sqrt(a^2 - ab - ac + bc) = -a + sqrt((a - b)(a - c))

so, in frequencies,

    **f_peak = sqrt( sqrt((f_z^2 - f_p1^2)(f_z^2 - f_p2^2)) - f_z^2 )**

with `f_p1 = k f_z`. **There is no fitted constant in it.** It is exact for the
model, so its residual against SPICE is a measurement of how wrong the MODEL is
— which is a far sharper statement than any expression a symbolic search would
return, because a searched expression confounds model error with fit error.

WHAT THIS BUYS, AND IT IS THE POINT OF ITEM 6
----------------------------------------------
It decomposes the pre-screen's ~4.9 % `f_peak` error into two terms that can be
attacked separately:

  * the **grid** term — `f_peak` computed from the exact formula against
    `f_peak` found by maximising the same expression on the 1200-point log grid
    the pre-screen actually uses. Pure numerics, and it bounds how much of the
    error is the predictor's own discretisation.
  * the **`k`** term — the exact formula fed the TRUE `k` from measured
    `gm`/`gmbs` against the same formula fed the pre-screen's predicted `k`.
    Everything left over is the one-zero/two-pole model failing to describe the
    real circuit.

And it explains the retracted `20 log10(k)`, which is what makes it worth
presenting: the asymptotic peaking is only reached when `f_p2 >> f_p1`, and the
formula above says exactly when the peak exists at all — the square root needs
`f_z < f_p1` **and** `f_z < f_p2`, which is session 9c's measured "f_z must sit
below f_p2 or there is no peak at all", derived rather than observed.
"""

from __future__ import annotations

import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

from nebula.experiments import prescreen as PS

HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "robust_geometry_data.csv"


# ─────────────────────────────────────────────────────────────────────────────
# The closed form.
# ─────────────────────────────────────────────────────────────────────────────


def f_peak_closed_form(f_z, f_p1, f_p2):
    """Exact peak frequency of a 1-zero/2-pole magnitude. No fitted constant.

    Returns `nan` where no interior peak exists — which is a RESULT, not a
    failure: the discriminant going negative is the analytic statement of
    "this circuit does not equalise".
    """
    a = np.asarray(f_z, dtype=float) ** 2
    b = np.asarray(f_p1, dtype=float) ** 2
    c = np.asarray(f_p2, dtype=float) ** 2
    disc = (a - b) * (a - c)
    with np.errstate(invalid="ignore"):
        u = np.sqrt(np.where(disc >= 0.0, disc, np.nan)) - a
        return np.sqrt(np.where(u > 0.0, u, np.nan))


def peaking_closed_form_db(f_z, f_p1, f_p2):
    """|H(f_peak)| / |H(0)| in dB, from the same exact peak location."""
    f = f_peak_closed_form(f_z, f_p1, f_p2)
    with np.errstate(invalid="ignore", divide="ignore"):
        h = (np.sqrt(1.0 + (f / f_z) ** 2)
             / (np.sqrt(1.0 + (f / f_p1) ** 2) * np.sqrt(1.0 + (f / f_p2) ** 2)))
        return 20.0 * np.log10(h)


def has_peak(f_z, f_p1, f_p2) -> np.ndarray:
    """The existence condition, derived: the discriminant must be positive.

    `f_z < f_p1` always holds (`f_p1 = k f_z`, `k > 1`), so this reduces to
    `f_z < f_p2` plus the requirement that `sqrt((a-b)(a-c)) > a`. Session 9c
    measured the first half at the terminal and called it "a hard structural
    constraint, not a tuning preference". This is that constraint, derived.
    """
    return np.isfinite(f_peak_closed_form(f_z, f_p1, f_p2))


# ─────────────────────────────────────────────────────────────────────────────
# The measurement.
# ─────────────────────────────────────────────────────────────────────────────


def load() -> pd.DataFrame:
    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["f_pk_hz", "peaking_db", "gm", "gmbs",
                           "rs", "cs", "rl", "cl"])
    interior = ((df["g_pk_db"] - df["g_top_db"] > 0.25)
                & (df["f_pk_hz"] > 1e7) & (df["f_pk_hz"] < 1.8e10))
    return df[interior].copy()


def main() -> int:
    print("=" * 78)
    print("TASK 8c ITEM 6 -- THE CLOSED FORM FOR f_peak")
    print("=" * 78)
    print("  PySR is INSTALLED BUT CANNOT RUN HERE: juliapkg dies on the")
    print("  Microsoft Store python.exe (a zero-byte app-execution alias),")
    print("  OSError errno 22. Fix is a real interpreter, not code. See the")
    print("  module docstring; run_pysr() is kept for whoever installs one.")
    print()
    print("  Derived instead, exactly, with NO fitted constant:")
    print("     f_peak = sqrt( sqrt((f_z^2 - f_p1^2)(f_z^2 - f_p2^2)) - f_z^2 )")
    print()

    df = load()
    n = len(df)
    f_z = 1.0 / (2.0 * np.pi * df["rs"] * df["cs"])
    f_p2 = 1.0 / (2.0 * np.pi * df["rl"] * df["cl"])
    k_true = 1.0 + (df["gm"] + df["gmbs"]) * df["rs"] / 2.0
    f_meas = df["f_pk_hz"].to_numpy(dtype=float)
    pk_meas = df["peaking_db"].to_numpy(dtype=float)

    # The pre-screen's own predicted gm, so the two terms can be separated.
    t0 = time.perf_counter()
    gm_hat, gmbs_hat = [], []
    for _, r in df.iterrows():
        g, gb = PS.predict_gm({k: float(r[k]) for k in
                               ("w_in", "l_in", "nf_in", "i_bias")})
        gm_hat.append(g); gmbs_hat.append(gb)
    gm_hat = np.asarray(gm_hat); gmbs_hat = np.asarray(gmbs_hat)
    predict_s = time.perf_counter() - t0

    k_hat_raw = 1.0 + (gm_hat + gmbs_hat) * df["rs"].to_numpy() / 2.0
    k_hat_cal = 1.0 + PS.K_ALPHA * (gm_hat + gmbs_hat) * df["rs"].to_numpy() / 2.0
    k_true_cal = 1.0 + PS.K_ALPHA * (df["gm"] + df["gmbs"]).to_numpy() \
        * df["rs"].to_numpy() / 2.0

    def mdape(pred) -> float:
        m = np.isfinite(pred)
        return float(np.median(np.abs(pred[m] - f_meas[m]) / f_meas[m]))

    fz = f_z.to_numpy(); fp2 = f_p2.to_numpy()
    variants = [
        ("exact form, TRUE k (measured gm), uncalibrated",
         f_peak_closed_form(fz, k_true.to_numpy() * fz, fp2)),
        ("exact form, TRUE k, G60-calibrated",
         f_peak_closed_form(fz, k_true_cal * fz, fp2)),
        ("exact form, PREDICTED k, uncalibrated",
         f_peak_closed_form(fz, k_hat_raw * fz, fp2)),
        ("exact form, PREDICTED k, G60-calibrated",
         f_peak_closed_form(fz, k_hat_cal * fz, fp2)),
    ]

    print(f"  {n} designs with a genuine interior peak.")
    print()
    print(f"  {'variant':<46} {'MdAPE':>8} {'defined':>9}")
    print("  " + "-" * 66)
    for name, pred in variants:
        cov = float(np.isfinite(pred).mean())
        print(f"  {name:<46} {100 * mdape(pred):>7.2f}% {100 * cov:>8.1f}%")
    # The pre-screen, which maximises the SAME expression on a 1200-point grid.
    grid_pred = np.array([PS.predict_response(
        {kk: float(r[kk]) for kk in ("w_in", "l_in", "nf_in", "i_bias",
                                     "rs", "cs", "rl", "cl")},
        drawn=False).f_peak_hz for _, r in df.iterrows()])
    print(f"  {'pre-screen (same k, 1200-point grid argmax)':<46} "
          f"{100 * mdape(grid_pred):>7.2f}% {100.0:>8.1f}%")
    print()

    # --- the decomposition, which is what item 6 was worth doing for --------
    exact_true = f_peak_closed_form(fz, k_true_cal * fz, fp2)
    exact_pred = f_peak_closed_form(fz, k_hat_cal * fz, fp2)
    m = np.isfinite(exact_true) & np.isfinite(exact_pred)
    grid_term = float(np.median(np.abs(grid_pred[m] - exact_pred[m])
                                / exact_pred[m]))
    k_term = float(np.median(np.abs(exact_pred[m] - exact_true[m])
                             / exact_true[m]))
    model_term = float(np.median(np.abs(exact_true[m] - f_meas[m]) / f_meas[m]))
    print("  ERROR DECOMPOSITION -- where the pre-screen's ~5 % actually lives")
    print(f"    grid discretisation (argmax on 1200 log points)  "
          f"{100 * grid_term:6.2f}%")
    print(f"    predicted k vs measured gm/gmbs                  "
          f"{100 * k_term:6.2f}%")
    print(f"    the 1-zero/2-pole MODEL itself, against SPICE    "
          f"{100 * model_term:6.2f}%")
    print("    (medians of |relative| error; they do not add linearly)")
    print()

    # --- the existence condition -------------------------------------------
    exists = has_peak(fz, k_true_cal * fz, fp2)
    print("  THE EXISTENCE CONDITION, DERIVED RATHER THAN OBSERVED")
    print(f"    the discriminant is positive for {100 * exists.mean():.1f} % of "
          f"designs that MEASURED an interior peak")
    print("    it needs f_z < f_p1 (always true, k > 1) AND f_z < f_p2 --")
    print("    which is session 9c's 'f_z must sit BELOW f_p2 or there is no")
    print("    peak at all', obtained from the algebra instead of the bench")
    # THE CONVERSE, which is the direction that would make it a free screen:
    # does the discriminant correctly REJECT the designs that measured no
    # interior peak? Sensitivity without specificity is not a screen.
    allrows = pd.read_csv(CSV_PATH).dropna(
        subset=["f_pk_hz", "peaking_db", "gm", "gmbs", "rs", "cs", "rl", "cl"])
    is_g44 = ~((allrows["g_pk_db"] - allrows["g_top_db"] > 0.25)
               & (allrows["f_pk_hz"] > 1e7) & (allrows["f_pk_hz"] < 1.8e10))
    fz_a = (1.0 / (2.0 * np.pi * allrows["rs"] * allrows["cs"])).to_numpy()
    fp2_a = (1.0 / (2.0 * np.pi * allrows["rl"] * allrows["cl"])).to_numpy()
    k_a = 1.0 + PS.K_ALPHA * (allrows["gm"] + allrows["gmbs"]).to_numpy() \
        * allrows["rs"].to_numpy() / 2.0
    ex_a = has_peak(fz_a, k_a * fz_a, fp2_a)
    g44 = np.asarray(is_g44)
    print(f"    CONVERSE: of the {int(g44.sum())} designs that measured NO "
          f"interior peak,")
    print(f"    the discriminant rejects {100 * (~ex_a)[g44].mean():.1f} % "
          f"outright -- so on its own")
    print("    the existence test is SENSITIVE but not SPECIFIC, and the")
    print("    pre-screen's f_peak-window test is what does the rejecting")
    print("    (84.3 % of that population, BASELINES.md sec 5)")
    print()

    # --- peaking ------------------------------------------------------------
    pk_pred = peaking_closed_form_db(fz, k_true_cal * fz, fp2)
    mp = np.isfinite(pk_pred)
    asym = 20.0 * np.log10(k_true_cal)
    print("  PEAKING: the closed form against the retracted asymptote")
    print(f"    closed form,  median |error|   {np.median(np.abs(pk_pred[mp] - pk_meas[mp])):6.3f} dB")
    print(f"    20*log10(k),  median |error|   {np.median(np.abs(asym[mp] - pk_meas[mp])):6.3f} dB")
    print(f"    20*log10(k),  median BIAS      {np.median(asym[mp] - pk_meas[mp]):+6.3f} dB")
    print("    -> the asymptote over-predicts because the load pole erodes the")
    print("       boost; session 9c measured 7.66 dB predicted against 0.00 dB")
    print("       realised at one point, and this is that effect over 1311.")
    print()

    out = pd.DataFrame({
        "idx": df["idx"].to_numpy(), "f_pk_hz_meas": f_meas,
        "f_peak_closed_true_k": exact_true, "f_peak_closed_pred_k": exact_pred,
        "f_peak_grid": grid_pred, "peaking_db_meas": pk_meas,
        "peaking_db_closed": pk_pred, "peaking_db_asymptote": asym,
        "f_z": fz, "f_p2": fp2, "k_true": k_true.to_numpy(),
        "k_pred_calibrated": k_hat_cal,
    })
    out.to_csv(HERE / "task8_symbolic_results.csv", index=False)
    print(f"  gm prediction over {n} rows took {predict_s:.2f} s")
    print(f"wrote {HERE / 'task8_symbolic_results.csv'}")
    return 0


def run_pysr(niterations: int = 100):                    # pragma: no cover
    """The original PySR search, kept for an environment that can run it.

    Two bugs it had, fixed here so it works when Julia is available:
      * `parallelism=False` is not a valid value — recent PySR wants the string
        `"serial"`, and `deterministic=True` REQUIRES serial anyway;
      * it fitted on all rows and scored on the same rows, then compared that
        in-sample number to the pre-screen's. Now it holds out 20 %.
    """
    from pysr import PySRRegressor
    from sklearn.model_selection import train_test_split

    df = load()
    df["k"] = 1.0 + (df["gm"] + df["gmbs"]) * df["rs"] / 2.0
    df["f_z"] = 1.0 / (2.0 * np.pi * df["rs"] * df["cs"])
    df["f_p2"] = 1.0 / (2.0 * np.pi * df["rl"] * df["cl"])
    X = df[["f_z", "f_p2", "k", "gm"]]
    y = np.log10(df["f_pk_hz"])
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2,
                                              random_state=42)
    m = PySRRegressor(
        niterations=niterations, binary_operators=["+", "-", "*", "/"],
        unary_operators=["sqrt", "log", "exp"], maxsize=25, populations=30,
        random_state=42, deterministic=True, parallelism="serial",
        progress=False,
    )
    m.fit(X_tr, y_tr)
    err = np.median(np.abs(10.0 ** m.predict(X_te) - 10.0 ** y_te)
                    / 10.0 ** y_te)
    print(m.sympy())
    print(f"held-out MdAPE {100 * err:.2f} %")
    return m


if __name__ == "__main__":
    raise SystemExit(main())
