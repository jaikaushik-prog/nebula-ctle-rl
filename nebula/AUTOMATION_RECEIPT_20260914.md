# Automation receipt for one saved production run

This receipt makes the RL role and deterministic recovery inspectable. It extracts the existing 9 dB / 1.9 GHz `rl-hybrid` production run, without rerunning a policy or simulator. It is separate from the saved 3 dB physical CTLE used in the video and from the integrated 73-device transistor checkpoint.

Source: `nebula/product_demo/rl_hybrid_9db_1p9ghz/design.json`.
Source SHA-256: `906bcedce089909acf3504462fad6270d8712a6f9f2c521ef35df356c694e4f3`.
Machine-readable receipt: `nebula/results/submission_receipt_20260914/receipt.json`.

## What the run actually did

1. Accepted 9 dB peaking and 1.9 GHz peak frequency. The frozen seed was 2026090500; the nearest training request was 8 dB / 1.921094 GHz, supplying fixed start 360.
2. Ran an actual policy trace for each of 45 PVT corners across seven constructed channel losses. The actor saw request, current code and measured eye history. Its moves changed attenuation, Rs or Cs codes within the 512-setting characterized library.
3. Checked full V6 compliance using saved transistor/link measurements. A large or valid eye alone could not pass every constraint. Safe visits were ranked by normalized target distance, then eye area; deterministic bank search supplied missing or better-centered candidates.
4. Exported representative TT / 1.8 V / 27 C, 7.5 dB-loss setting 425 (A6/R5/C1). The original deck export records one fresh SPICE invocation. The exported schematic and deck describe that representative circuit; the complete result uses an adaptive code map.

| Accounting field | Saved count | Meaning |
|---|---:|---|
| Model conditions passed | 315 / 315 | Adaptive codes across 45 PVT x 7 losses |
| Billed visits | 2,406 | Includes 315 fixed starts and repeated settings |
| Policy move visits | 2,091 | Visits after the fixed starts, with repeats billed |
| Verifier calls | 2,406 | Cached compliance checks on the visited settings |
| RL-shield selections | 81 | Final code was in the actual visited trace |
| Bank selections | 234 | 185 target refinements plus 49 safety recoveries |
| Bank rows checked | 119,808 | 234 enumerations of 512 saved settings |
| Original new SPICE calls | 1 | Representative export only; search/measure counters are zero |
| New SPICE calls for this receipt | 0 | Saved-record extraction only |

The nominal representative record reports 8.632696 dB at 1.896053 GHz, 0.571622 mVrms input noise, 6.68034 mW CTLE power, and 285.511962 mV / 0.828125 UI modeled eye. These are saved bank/model measurements of this earlier circuit. The original partial passive-area scalar is not full area compliance. The later readiness audit found that the representative fixed setting does not inherit the adaptive 315/315 result; do not present it as one fixed all-corner receiver.

## A recorded recovery that the policy did not supply

At FS / 0.95 VDD / 125 C and 3 dB channel loss, the stored trace is:

| Visit | Setting | Action into visit | Link observation | Full verifier |
|---:|---:|---|---|---|
| 0 | 360 | Fixed start | Valid eye | Rejected |
| 1 | 296 | Attenuation down | Valid eye | Rejected |
| 2 | 232 | Attenuation down | Valid eye | Rejected |
| 3 | 168 | Attenuation down | Invalid link | Rejected |
| 4 | 104 | Attenuation down | Invalid link | Rejected |
| 5 | 168 | Attenuation up | Invalid link | Rejected |
| 6 | 232 | Attenuation up | Valid eye; then LOCK | Rejected |

The saved `no-compliant-rl-proposal` decision establishes that none of these visits passed full V6. The record does not store the failed constraint names for each visit; those are left unknown. Invalid-link zero eye values in the raw record are sentinels, not measured closed eyes.

The deterministic bank search checked 512 saved settings and selected compliant setting **496** (A7/R6/C0). It was never visited by the actor. The receipt retains that final selection separately and does not append it as an eighth policy measurement.

The representative export is a different condition within the same run: its eight visits were 360, 296, 232, 168, 104, 168, 232, 168; deterministic **target refinement** selected 425. This explains why the exported circuit must not be credited to an unobserved policy action.

## Recorded time and its limits

The saved design-plus-deck timer is **5.893642 s**, including **0.224587 s** for representative-deck preparation. The remaining 5.669055 s is the arithmetic difference of those two recorded timers, not a separately instrumented policy timer.

This is **not end-to-end latency**: subsequent schematic/dashboard generation, file writing and startup outside the timer are excluded. Policy, verifier and fallback stage times were not individually logged. The receipt keeps these missing fields null. It establishes no matched runtime speedup. The 91.8x historical figure concerns candidate visits in a separate five-seed benchmark, not seconds saved in this run.

## Reproduce and inspect

Run `py -3.13 -m nebula.experiments.build_submission_receipt` from the repository root. The builder checks the pinned saved JSON hash, exact condition membership, trace actions, endpoint identity, selection attribution and aggregate accounting. It reads no training or simulator module. All 315 original traces remain in the receipt, alongside SHA-256 identities for the saved JSON, CIR, schematic, RL dashboard and current explanatory source files.

The current source hashes document the implementation inspected during receipt construction; they are not claimed to be a contemporaneous Git snapshot of the original run. Existing artifacts are referenced in place and remain unchanged. The receipt is a new derived artifact, not a new scientific measurement.

Professor-ready takeaway: the policy contributes a bounded sequence of candidate settings; the verifier decides what is acceptable, and deterministic recovery can supply the final circuit. Keeping those roles visible makes the automation credible even when a proposal fails.
