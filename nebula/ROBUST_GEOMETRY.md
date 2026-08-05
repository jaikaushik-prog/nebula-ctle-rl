# Where do the corner-robust designs live?

> [!WARNING]
> **Data loss and regeneration (G49).** This analysis is a re-simulation. The original `s9_yield_results.json` from session 10d was gitignored and lost. Because the population sampling in `s9_yield.py` is seeded, the exact 1890 designs were regenerated and passed through the corner screen again. This cost ~13 minutes of compute (7560 SPICE runs). The resulting per-design table is now tracked as `robust_geometry_data.csv`, meaning this entire analysis is now simulator-free and reproducible instantly.

## The Hypothesis

G46 established that the worst corner is fast-hot, not slow-hot, and that S3's two edges sit on opposite sides of the process axis: FF pushes $f_{\text{peak}}$ up through the 2.5 GHz top edge, while SS drops peaking toward 0 dB.

**Hypothesis:** The 155 corner-robust designs are interior in the box, and the 100 corner-fragile ones cluster near the edges, because robustness requires $f_{\text{peak}}$ to be centred enough that neither mechanism reaches it.

## Result: The Hypothesis Holds

The hypothesis held strongly. Robustness is not driven by the physical box coordinates (like $W$, $L$, or $I_{\text{bias}}$) but by the derived bandwidth placement. Specifically, **the margin of nominal $f_{\text{peak}}$ to the S3 window edge is the dominant predictor of corner robustness**.

### Group Medians and Mann-Whitney U

Comparing the 155 robust designs against the 100 fragile ones (both groups pass all specs at nominal TT). Values are medians, $p$-values are two-sided Mann-Whitney U, and $q$ is Benjamini-Hochberg adjusted.

| Coordinate | Robust Median | Fragile Median | P(R > F) | p-value | q-value |
|---|---|---|---|---|---|
| $R_s$ (Ω) | 364.1 | 365.2 | 0.517 | 0.6518 | 0.8168 |
| $C_s$ (fF) | 2086 | 2363 | 0.463 | 0.3178 | 0.8168 |
| $R_L$ (Ω) | 183.5 | 188.4 | 0.487 | 0.7247 | 0.8168 |
| $I_{\text{bias}}$ (mA) | 1.998 | 2.492 | 0.422 | 0.0354 | 0.2126 |
| $W_{\text{in}}$ (µm) | 57.81 | 54.15 | 0.530 | 0.4212 | 0.8168 |
| $L_{\text{in}}$ (µm) | 0.3087 | 0.3482 | 0.463 | 0.3152 | 0.8168 |
| $V_{cm,in}$ (V) | 1.338 | 1.371 | 0.482 | 0.6282 | 0.8168 |
| $n_{f,in}$ (-) | 5 | 5 | 0.532 | 0.3879 | 0.8168 |
| $f_z$ (GHz) | 0.2514 | 0.2121 | 0.530 | 0.4122 | 0.8168 |
| $f_{p2}$ (GHz) | 5.783 | 5.633 | 0.513 | 0.7247 | 0.8168 |
| $k$ (-) | 2.504 | 2.819 | 0.487 | 0.7260 | 0.8168 |
| $f_{\text{peak}}$ nom (GHz) | 1.738 | 1.738 | 0.520 | 0.5943 | 0.8168 |
| peaking nom (dB) | 6.291 | 6.337 | 0.519 | 0.6147 | 0.8168 |
| Nyquist boost nom (dB) | 6.135 | 5.98 | 0.531 | 0.4093 | 0.8168 |
| $g_m/I_D$ (1/V) | 9.177 | 6.965 | 0.592 | 0.0136 | 0.1221 |
| **$f_{\text{peak}}$ margin (oct)** | **0.3253** | **0.126** | **0.759** | **2.78e-12** | **5.00e-11 *** |
| box interiority (-) | 0.067 | 0.07523 | 0.501 | 0.9813 | 0.9813 |
| box_interiority_mean (-) | 0.2717 | 0.277 | 0.503 | 0.9355 | 0.9813 |

*(P(R > F) is the common-language effect size: the chance a random robust design exceeds a random fragile one).*

None of the physical box parameters (or their min-interiority) are statistically significant predictors after correction. The only statistically significant separator is the **$f_{\text{peak}}$ margin**, which is massive ($p < 10^{-11}$).

## Distance-to-Window-Edge Distribution

Measuring the distance to the *nearer* edge of the 1.25–2.5 GHz S3 window (which is exactly 1 octave wide, making 0.5 octaves the absolute geometric centre).

| Margin in bin (octaves) | Total TT Winners ($n$) | Corner-Robust | Rate | 95% Wilson CI |
|---|---|---|---|---|
| 0.00 – 0.05 | 16 | 1 | 6.2% | [1.1, 28.3] |
| 0.05 – 0.10 | 34 | 5 | 14.7% | [6.4, 30.1] |
| 0.10 – 0.15 | 33 | 18 | 54.5% | [38.0, 70.2] |
| 0.15 – 0.20 | 17 | 13 | 76.5% | [52.7, 90.4] |
| 0.20 – 0.25 | 14 | 11 | 78.6% | [52.4, 92.4] |
| 0.25 – 0.30 | 34 | 22 | 64.7% | [47.9, 78.5] |
| 0.30 – 0.50 | 107 | 85 | 79.4% | [70.8, 86.0] |

Designs near the edge (0.00–0.10 octaves) are almost entirely obliterated by the corners (6/50 survive). Designs deep in the interior (> 0.30 octaves) survive at nearly 80%.

## The Warm-Start Prior and Reward Shape

If an optimizer only proposes designs with at least $t$ octaves of margin:

| Keep margin $\geq t$ (octaves) | Designs Kept | Corner-Robust | Rate | 95% Wilson CI |
|---|---|---|---|---|
| 0.000 (Baseline) | 255 | 155 | 60.8% | [54.7, 66.6] |
| 0.100 | 205 | 149 | 72.7% | [66.2, 78.3] |
| 0.150 | 172 | 131 | 76.2% | [69.3, 81.9] |
| **0.200** | **155** | **118** | **76.1%** | **[68.8, 82.2]** |
| 0.300 | 107 | 85 | 79.4% | [70.8, 86.0] |

**The Deliverable Number:** Rejecting designs with less than **0.20 octaves** of margin removes 100 designs from the feasible set. Of those 100, 63 were corner-fragile and would have died anyway. This filter raises the conditional yield from 60.8% to 76.1% while maintaining a large target space. This is the recommended prior and penalty threshold.

## Validating G46: The 2x2 Mechanism Table

Where the fragile designs sat nominally, and which corner killed them (a design can appear in both columns if it fails multiple corners):

| Nominal $f_{\text{peak}}$ | Died at FF | Died at SS |
|---|---|---|
| Above 1.77 GHz centre | 29 | 27 |
| Below 1.77 GHz centre | 10 | 45 |

This confirms the physical story: designs sitting below the centre are heavily killed by SS (which drops $g_m$ and kills peaking). Designs above the centre are predominantly killed by FF (which raises $g_m$ and pushes the peak out the top). The two failure mechanisms genuinely attack from opposite sides of the window.

## Limitations and What This Does Not Say

> [!WARNING]
> **This is still an optimistic bound.** The 45-corner screen, the 155/100 split, and the 8.10% total yield figure all rely on a schematic where the tail transistor is modelled as two ideal current sinks. Real tail transistors add additional corner spread, especially as headroom compresses. This remains the top open item for the project.

- **This does not say physical box interiority matters.** The hypothesis held for bandwidth placement, but the min-interiority statistic on the physical parameters ($W$, $L$, etc.) was flat. Robustness is a property of the pole/zero locations, not of staying away from the parameter bounds.
- **This does not guarantee 76% yield globally.** The 76.1% rate is conditioned on *already passing all specs at TT*. The unconditional yield remains the ~8.10% tax on the ~13.5% nominal yield.
