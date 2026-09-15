# Submission target-coverage planning review — cached eligibility only

Campaign: 15 September 2026. Planning review generated 2026-09-14T23:50:19 local time. Status: planning preflight, not physical measurement.
Scope: existing characterized bank only; zero SPICE calls, zero training calls and no policy inference. No campaign runtime was measured. This review does not alter the campaign plan, candidate ordering, tolerances, registry or source data.

## Result

Five of the thirteen declared requests have at least one **single fixed cached setting** that satisfies the existing acceptance rows at every one of the 45 PVT corners and all seven constructed channel losses. Eight have an empty intersection.

| Requested boost (dB) | Requested peak (GHz) | Fixed eligible count | Complete eligible setting list |
|---:|---:|---:|---|
| 3 | 1.25 | 0 | None |
| 3 | 1.9 | 3 | 273, 337, 401 |
| 3 | 2.5 | 0 | None |
| 6 | 1.25 | 0 | None |
| 6 | 1.9 | 9 | 288, 346, 352, 353, 410, 417, 473, 474, 481 |
| 6 | 2.5 | 1 | 480 |
| 9 | 1.25 | 0 | None |
| 9 | 1.9 | 1 | 490 |
| 9 | 2.5 | 0 | None |
| 12 | 1.25 | 0 | None |
| 12 | 1.9 | 0 | None |
| 12 | 2.5 | 0 | None |
| 6 | 2.1 | 7 | 288, 352, 416, 417, 473, 480, 481 |

The 6 dB / 2.1 GHz row is the separately declared exposed diagnostic. These are not held-out generalization results. Empty eligibility means this cached bank supplies no compliant fixed proposal; it does not establish physical impossibility. Nonempty eligibility does not establish fresh physical acceptance, output completion or a full receiver pass. With this unchanged selection domain, delivered physical coverage cannot exceed 5/13 declared requests; the actual measured number remains unknown.

## Domain and method

- Source: `nebula/experiments/joint_bank_73_run.jsonl.gz`.
- Gzip SHA-256: `d1ce3759bd93854e8a051fc85696da755e8737328bf132b479f411619f8cae22`.
- Decoded source SHA-256, matched to the production pin: `1B5F941DF4B34F3C90F6DD050F264D8A77C7BB2E5CE4D9EED8CC29EBD9F9843F`.
- Exactly 23,040 unique cached setting/corner records: all 512 settings and the mandated 45 corners, checked for complete Cartesian membership.
- Losses: 3, 4.5, 6, 7.5, 9, 10.5, 12 dB at Nyquist; no channel-loss override.
- For each target, intersect `MarginBankTable.compliant_settings(corner, loss, boost, frequency)` across all 315 conditions using the existing `physical_design.select_fixed_setting` implementation.
- Each target checks 161,280 cached setting/condition combinations; all thirteen check 2,096,640. These are cached comparisons, not simulator invocations or elapsed-time evidence.
- Unchanged request match tolerances: +/-1.5 dB and +/-0.3 octave, with the separate absolute S3 frequency/peaking bands and all other V6 rows also required.

The exact required rows are: `S3_f_peak_band`, `S3_f_peak_match`, `S3_peaking`, `S3_peaking_match`, `S3_nyq_boost`, `S5_noise`, `S6_power`, `saturation`, `tail_saturation`, `S8_eye_h`, `S8_eye_w`, `S7_area`, `S4_hd3_nyq`. The underlying bank has the older bias implementation and modeled link/ideal-DFE evidence. Its operating-point harmonic and geometry rows must not be relabeled as the later physical-reference verifier or the separate integrated transistor receiver.

The production policy and the classical fixed-intersection path reference the same decoded bank identity. This review performs no `hybrid_designer.solve`, policy loading, candidate export, geometry search or physical verification. It derives eligibility only.

## Implications for the declared campaign

1. The 12 dB / 2.5 GHz timing target is an empty-domain diagnostic. Retain its scheduled workflows and their complete cost/status accounting; it cannot supply a both-success timing pair with this fixed selection domain. Across three repeats, at most nine of the twelve declared target/repetition pairs can be both-success pairs.
2. The shared verified registry selects setting 401 for 3 dB / 1.9 GHz in both arms. At 9 dB / 1.9 GHz there is only setting 490. The benchmark's multi-candidate, nonregistry case is 6 dB / 2.1 GHz, with seven eligible settings. This structure limits what any policy-versus-classical result can establish; do not infer a speedup before measurement.
3. The 6 dB / 1.9 GHz coverage row has nine eligible settings but an eight-candidate cap. An exhausted eight-slot workflow is not an exhaustive physical rejection of all nine. The pre-existing registry proposes 474 first for both arms; each proposal still needs fresh acceptance.
4. Static review of the current `physical_recovery.prepare` finds that fixed eligibility is computed before policy inference, and an empty intersection bypasses the policy proposer. This avoids treating a known empty domain as a policy exception. Instrument errors and unknown call counts still need separate statuses.
5. Keep the complete thirteen-row coverage denominator and the registered twenty-four-workflow benchmark schedule. Do not drop empty, failed or unfinished rows, or pool RL-only coverage rows into the paired-arm comparison.

Existing first-target memberships reproduce the historical coverage record: 3 dB / 1.9 GHz gives [273, 337, 401], and 6 dB / 1.9 GHz gives [288, 346, 352, 353, 410, 417, 473, 474, 481]. This is a consistency check, not new physical evidence.

## Read dependencies and reproducibility

Planning sources:
- `nebula/SUBMISSION_RECOVERY_BENCHMARK_PLAN_20260915.md`: exact thirteen-target coverage and four-target matched subset; all results exposed.
- `nebula/experiments/exp_submission_recovery_benchmark.py`: `schedule("coverage")` and `schedule("benchmark")`.
- `nebula/physical_recovery.py`: shared DEVELOPMENT bank and current ordering/empty-domain handling.
- `nebula/physical_design.py`: `select_fixed_setting`; `nebula/physical_verified_registry.json`: shared historical target proposals.
- `nebula/rl/margin_adapt_env.py`: table membership and cached compliance.
- `nebula/experiments/exp_joint_bank.py`, `exp_margin_improve_controls.py`, `exp_shielded_ppo.py`: exact decoded source identity and common selection table.
- `nebula/rl/reward_v1.py` and `nebula/experiments/exp_bank_sweep.py`: unchanged V6 acceptance rows and request tolerances.

The bank digest is frozen above. Source code and the campaign plan were still being prepared during this independent review; the campaign must pin its own final committed versions before measurement. No plan/source file was modified by this review.

Reproduction outline (read-only, no SPICE):

```python
from nebula.experiments import exp_joint_bank as J
from nebula.experiments import exp_margin_improve_controls as BASE
from nebula.rl.margin_adapt_env import MarginBankTable
from nebula.physical_design import select_fixed_setting

assert J._decoded_sha256(BASE.SOURCE) == BASE.SOURCE_SHA256
table = MarginBankTable.from_path(BASE.SOURCE)
targets = [(p, f * 1e9) for p in (3., 6., 9., 12.)
           for f in (1.25, 1.9, 2.5)] + [(6., 2.1e9)]
for target in targets:
    try:
        _, eligible, checks = select_fixed_setting(
            table, target, None, table.losses)
    except RuntimeError as exc:
        if "no single fixed setting" not in str(exc):
            raise
        eligible = []
    print(target, len(eligible), eligible)
```

