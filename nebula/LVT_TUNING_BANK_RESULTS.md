# Entry 97 -- Safe LVT Capacitor-Selector Screen

**Date:** 2026-09-04

**Verdict:** **FAIL -- no LVT width meets the loss and capacitance limits together**

## Plain-language result

The official SKY130 low-threshold transistor was tested as the capacitor-bank
switch at six sizes, from the Entry 96 width through 32 times that width. A
wider switch initially reduces its unwanted series resistance. Unfortunately,
it also increases parasitic capacitance. The trade-off has no usable overlap:
the only scale that passes capacitance accuracy fails loss by 19.13 times, and
the scale with the lowest loss still fails loss by 3.15 times while also
failing capacitance accuracy.

All 384 registered `scale x Rcode x Ccode` rows completed with real SKY130 LVT
transistors, ordinary resistor switches, poly resistors and MIM capacitors. No
boosted voltage or ideal switch was used.

## Frozen gate results

| Gate | Requirement | Result |
|---|---|---|
| L1 | Exactly 384 valid unique rows | **PASS** |
| L2 | Both code axes ordered at every scale | **PASS** |
| L3 | At least one scale has G error <= 0.913434 mS | **FAIL** |
| L4 | At least one scale has C error <= 0.593954 pF | **PASS** |
| L5 | Select smallest scale passing loss and C together | **FAIL: none** |
| L6 | Safe 0--1.8 V isolated screen | **PASS** |
| Overall | L1--L6 all pass | **FAIL** |

Per the frozen stopping rule, no all-corner bank run, CTLE insertion, link
measurement or RL retraining was performed.

## Measured width trade-off

| Scale | Per-side LVT widths (um) | Max G error (mS) | Max C error (pF) | Simultaneous pass |
|---:|---|---:|---:|---|
| 1 | 160 / 320 / 640 | 17.477435 | **0.550334** | No |
| 2 | 320 / 640 / 1280 | 8.838182 | 0.806647 | No |
| 4 | 640 / 1280 / 2560 | 4.395057 | 1.183030 | No |
| 8 | 1280 / 2560 / 5120 | **2.875972** | 2.127597 | No |
| 16 | 2560 / 5120 / 10240 | 4.374492 | 3.035017 | No |
| 32 | 5120 / 10240 / 20480 | 6.207598 | 4.472337 | No |

Bold values are the best measured value in each metric. They occur at
different scales, and even the best G error remains above the fixed limit.

## Why widening eventually becomes worse

From scale 1 to scale 8, lower ON resistance reduces the high-code series-loss
error. Beyond scale 8, the disabled devices are so large that their parasitic
paths dominate. The worst G-error row moves from the fully enabled `R7/C7`
case at scale 1 to low-capacitance codes at large scales. At scale 32, the
worst capacitance error is 4.472 pF against a 0.594 pF allowance.

This measured U-shaped curve is why extrapolating `Ron proportional to 1/W`
would have produced a wrong design. A larger MOS switch is simultaneously a
better conductor and a larger unwanted capacitor.

## Prediction score

1. Scale-1 LVT improves loss by less than 2x and still fails: **HIT**.
2. Width reduces loss until OFF parasitics become important: **HIT**.
3. At least one scale individually passes the loss gate: **MISS**.
4. No scale passes loss and capacitance simultaneously: **HIT**.
5. No candidate is selected and the run stops before CTLE: **HIT**.

## Product implication

The existing product is unaffected. It still generates a real fixed-passive
CTLE for each user request and uses the frozen RL/classical selection flow.
Entry 97 tested an optional programmable capacitor switch matrix; it did not
replace the working design path.

A further programmable attempt should change the tuning principle rather than
try another size of a series MOS switch. A PDK varactor controlled by a safe
bias/DAC is a plausible next research candidate, but it changes the topology
and must be separately approved and preregistered. Stopping the switch-matrix
work and presenting per-request fixed sizing is also a technically honest
option because the competition statement asks for automated circuit sizing,
not an on-chip digitally programmable bank.

## Evidence

- Result: `experiments/lvt_tuning_bank_results.json`
- 384-row SHA-256:
  `E8273184E56C7B31EBDD9518203CC3B2F9FCF4FC513657BC812A4BF904A46F0D`
- Result-file SHA-256:
  `6B4584A2BA2B8C9889CFF785D886A3AB3CF008ABE12DD98ED1D78D2FE6DC9502`
- Registration commit: `fc55185`
- Frozen runner commit: `60f921581ff52c97255361bf9b17e75957c40d0d`
- Measured wall clock: 80.279 s with six workers
- Final non-slow regression: 2,766 passed, 13 deselected, 2 known warnings
