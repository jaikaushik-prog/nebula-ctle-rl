"""
component_importance.py
------------------------
Reproduces Sec. IV / Eq. 5-6: feature/component influence from the ensemble
regressor's FIRST-layer weight magnitudes, scale-invariant, weights-only.

    I_j,SNDR^(m) = |w_SNDR,j^(m)| / sum_k |w_SNDR,k^(m)|
    I_j,SFDR^(m) = |w_SFDR,j^(m)| / sum_k |w_SFDR,k^(m)|
    I_j = (1 / 2M) * sum_m (I_j,SNDR^(m) + I_j,SFDR^(m))

Note: the paper's Eq. 5 normalizes per-output-head weights, but a standard
MLP's first Linear layer is shared across both heads (the branches split
later). We treat the shared first layer's weight magnitude as contributing
equally to both the SNDR and SFDR terms of Eq. 6 -- i.e. I_j^(m) reduces to
|w_j^(m)| / sum_k |w_k^(m)| (the two terms in Eq. 6 become identical for a
shared first layer), which preserves Eq. 6's ensemble-averaging and
normalization while matching this codebase's architecture (regressor.py).
If you give SNDR/SFDR fully separate first layers, swap in the literal
per-head weights here instead.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List
from circuits import CIRCUITS, Param
from regressor import EnsembleRegressor


def component_importance(ensemble: EnsembleRegressor, circuit: str) -> pd.DataFrame:
    names = [p.name for p in CIRCUITS[circuit]]
    first_layers = ensemble.first_layer_weights()  # list of (64, d) arrays
    M = len(first_layers)
    d = len(names)

    scores = np.zeros(d)
    for W in first_layers:
        # collapse the 64 first-layer units -> per-input-feature magnitude
        col_abs = np.abs(W).sum(axis=0)          # (d,)
        col_norm = col_abs / (col_abs.sum() + 1e-12)
        scores += col_norm  # counted once for SNDR-branch, once for SFDR-branch (shared layer, see docstring)
    scores = scores / M  # matches the (1/2M) * (I_SNDR + I_SFDR) normalization for a shared trunk

    df = pd.DataFrame({"feature": names, "rel_score": scores})
    df = df.sort_values("rel_score", ascending=False).reset_index(drop=True)
    df["rank"] = np.arange(1, len(df) + 1)
    return df[["rank", "feature", "rel_score"]]


def collapse_device_level(df: pd.DataFrame) -> pd.DataFrame:
    """Sum W/L/nf triples back into one score per named device (e.g. samp_nmos_W
    + samp_nmos_L + samp_nmos_nf -> samp_nmos), and keep system-level scalars
    (Fs, CB, source_res, duty_cycle, CS, fbin, ...) as-is, so the ranking is
    directly comparable to the paper's Table I (which ranks whole devices,
    not individual W/L/nf)."""
    base_names = []
    for f in df["feature"]:
        for suffix in ("_W", "_L", "_nf"):
            if f.endswith(suffix):
                base_names.append(f[: -len(suffix)])
                break
        else:
            base_names.append(f)
    out = df.copy()
    out["base"] = base_names
    collapsed = out.groupby("base")["rel_score"].sum().sort_values(ascending=False)
    collapsed = collapsed.reset_index()
    collapsed.columns = ["feature", "rel_score"]
    collapsed["rank"] = np.arange(1, len(collapsed) + 1)
    return collapsed[["rank", "feature", "rel_score"]]


if __name__ == "__main__":
    from circuits import denormalize, dim
    from simulator import SyntheticSpiceEnv

    circuit = "buffer_switch"
    rng = np.random.default_rng(0)
    spice = SyntheticSpiceEnv(circuit, seed=0, mismatch_std=0.3)
    A = rng.uniform(0, 1, size=(600, dim(circuit)))
    X = np.array([denormalize(a, circuit) for a in A])
    y = np.array([spice.evaluate(x)[:2] for x in X])

    ens = EnsembleRegressor(in_dim=dim(circuit), n_models=5)
    stats = ens.fit(X, y, epochs=40)
    print("Regressor val R2:", stats["val_r2"])

    df = component_importance(ens, circuit)
    df_collapsed = collapse_device_level(df)
    print(df_collapsed.to_string(index=False))
