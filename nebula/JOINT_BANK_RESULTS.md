# Real attenuator x CTLE bank -- entry 81 result

**Measured 2026-09-02.** This is the outcome of the experiment preregistered
in `PREDICTIONS.md` entry 81. It is improvement 2 and the measurement that was
required before any channel-adaptation policy could be trained.

## Question and scope

The experiment measured one fixed transistor design with:

- 8 real-PMOS input-attenuator codes;
- 64 drawn-passive CTLE `Rs`/`Cs` codes;
- all 45 mandated process/voltage/temperature corners; and
- seven constructed channel losses from 3.0 to 12.0 dB.

That is **23,040 real SKY130/ngspice circuit evaluations**. Each circuit result
was re-scored on all seven channels in Python. The circuit was evaluated at the
design load with `V6_SPECS` and operating-point/Nyquist HD3. This is not the
project's separate 135-point load grid, and the channels are constructed models
rather than measured boards.

## Result

| Channel loss | Scorable setting/corner rows | Solvable corner/request pairs | Requests served at all 45 corners |
|---:|---:|---:|---:|
| 3.0 dB | 7,519 | 704 / 720 | 11 / 16 |
| 4.5 dB | 10,803 | 718 / 720 | 15 / 16 |
| 6.0 dB | 14,430 | 720 / 720 | 16 / 16 |
| 7.5 dB | 17,681 | 720 / 720 | 16 / 16 |
| 9.0 dB | 19,694 | 720 / 720 | 16 / 16 |
| 10.5 dB | 20,755 | 720 / 720 | 16 / 16 |
| 12.0 dB | 21,427 | 720 / 720 | 16 / 16 |

The input attenuator therefore fixes the short-channel blocker broadly. At
3 dB every corner has at least 54 scorable settings; the total rises
monotonically with attenuation code from 6 rows at code 0 to 2,212 at code 7.
At 12 dB, codes 6 and 7 make all 2,880 setting/corner rows scorable.

## Preregistered questions

| Question | Outcome | Evidence |
|---|---|---|
| Q1 membership | **HIT** | 23,040 rows, 23,040 unique expected keys, no missing/extra/truncated row; `membership_ok=true` |
| Q2 reproduction control | **HIT** | Attenuator 5 / CTLE R4C3 at TT is device-valid; both 3 and 12 dB links are scorable. Noise is 0.4268671 mV_rms, exactly reproducing entry 78's row |
| Q3 attenuator clears PVT blocker | **HIT** | 7,519 scorable rows at 3 dB; every corner has at least 54 |
| Q4 request coverage | **HIT** | 11/16 at 3 dB and 16/16 at 12 dB, above the registered 4/16 and 8/16 floors |
| Q5 report all losses | **HONOURED** | All seven losses are shown above; no edge was selected after the result |
| Q6 RL go/no-go | **MISS** | **0/720** pairs require different channel-specific settings, below the registered 72/720 threshold |
| Q7 cost | **MISS** | The post-restart segment alone took 5,798.91 s = 96.65 min, already above 90 min. The initial 8,060-row segment and shutdown pause are not included, so no false total is reported |

Four of the six outcome predictions hit; Q5 was a reporting guard rather than a
directional prediction and was honoured.

## What the RL gate means

Of the 720 `(corner, request)` pairs, 704 are solvable on every channel. For
every one of those 704 pairs, at least one common setting complies across all
seven channels. The preregistered hypothesis that channel variation creates a
compliance-level hidden-state problem is therefore falsified.

The best-eye setting still changes with channel loss in **551/704 = 78.27%**
of those pairs. That shows an opportunity to optimise margin, but it does not
override the gate written before the data existed. Under entry 81's decision
rule, no RL policy is trained on this table. The correct controller for the
present compliance objective is a conservative fixed setting. A margin-
optimising adaptive objective would be a new research question and requires a
new human decision and preregistration before training.

## Failure audit and the next analog question

There were **zero hard simulator failures**. Of the 23,040 rows, 21,427 were
device/link-scorable at 12 dB and all 1,613 rejected rows explicitly reported
output-swing compression. Re-scoring those valid rows on shorter channels adds
only the same failure class: 13,908 compression failures at 3 dB, falling to
zero at 12 dB. No other channel failure reason appears.

The remaining 16 unsolved 3 dB corner/request pairs are concentrated at high
boost and low requested frequency:

| Request | Missing corners |
|---|---:|
| 8 dB @ 1.387 GHz | 3 |
| 10 dB @ 1.387 GHz | 8 |
| 10 dB @ 1.627 GHz | 3 |
| 10 dB @ 1.921 GHz | 1 |
| 10 dB @ 2.253 GHz | 1 |

Five of the misses occur at `sf/0.95/125C`; all 16 occur in only eight
corners, and 15 of 16 are at VDD -5%. This is the focused boundary for the
next analog investigation. It should be diagnosed before changing attenuator
range, CTLE values, bias or device sizes.

## Evidence and reproduction

- `experiments/joint_bank_results.json` is the compact result.
- `experiments/joint_bank_run.jsonl.gz` is the complete journal, compressed
  from 24,021,107 to 3,878,881 bytes. The decompressed SHA-256 is
  `A205303614ABCC5F76D6EA78CFA1C9687E49A3817FA1E9FA9EC314336E20CA33`.
- The completed process exited zero, and the parser independently established
  exact membership before this note was written.
- The local uncompressed journal is retained for analysis and ignored by Git.

The original run command was:

```text
python -m nebula.experiments.exp_joint_bank --run --workers 8
```

After the laptop shutdown, it continued without losing accepted work using:

```text
python -m nebula.experiments.exp_joint_bank --resume --workers 8
```

The output's historical `wall_clock_s` field is the resume segment, not the
whole experiment. Future runs now include `rows_before_segment`,
`spice_invocations_this_segment` and `wall_clock_scope` so this cannot be
misread again.

## Verification certificate

The timing-metadata regression failed before its implementation and the
focused joint-bank file then passed **14/14** tests. The complete post-change
non-slow suite passed **2,572 tests**, with 13 deselected and two existing
warnings, in 306.14 s.
