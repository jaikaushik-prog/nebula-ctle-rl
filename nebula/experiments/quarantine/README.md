# quarantine/ — artifacts that must not be read

## `coverage_results.CONTAMINATED_concurrent_run.json` (+ its run log)

**Two coverage sweeps ran CONCURRENTLY on 2026-08-21 and the wrong one won.**

| run | screen audit | solved on screen | **mandated 45-corner** | screen grew to | SPICE runs | wall clock |
|---|---|---|---|---|---|---|
| `b234jcq3l` — **the corrected run** | against the design-load grid it targets | 11 / 16 | **10 / 16** | 5 points | 16 094 | 149.7 min |
| `bjzvuvxy7` — **the superseded run** | against the full 135-point sweep (the G110 bug) | 1 / 16 | **8 / 16** | **8 points** | 24 294 | 209 min |

The second was launched first, was believed killed, was not, and **finished last
— so it overwrote the first one's artifact.** Everything in this directory is
from that superseded run.

**Three separate problems, and only the first was noticed at the time:**

1. **The artifact is from the run with the known-bad audit** (G110: the screen
   was graded against a grid it deliberately does not cover, so it "missed"
   repeatedly and grew 4 -> 8 points, inflating every later request's cost).
2. **Both runs' WALL-CLOCK numbers are inflated.** G70: one concurrent ngspice
   makes each ~4.8x slower. `b234jcq3l`'s 7-9 min per request should have been
   ~6. **Simulation COUNTS are unaffected** — they are counts, not times — so
   any claim in simulations survives and any claim in minutes does not.
3. **A completed run silently clobbered a completed run.** No run id, no
   refusal, no warning.

**Do not read these files.** They are kept rather than deleted because rule 10
forbids destroying a superseded measurement, and because the concurrency
failure is only legible with both runs side by side.

The numbers actually reported for `b234jcq3l` are recoverable from its console
log and are reproduced in `PREDICTIONS.md` entry 24. The corrected re-run on
`V6_SPECS` regenerates everything cleanly and is owed regardless (G111).
