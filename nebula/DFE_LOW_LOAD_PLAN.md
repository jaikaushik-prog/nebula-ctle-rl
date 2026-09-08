# Entry 111: approved lower-load buffer/storage chain

Frozen 2026-09-06 before measurements. Owner approved two fixed candidates:
all sixteen buffer/memory MOS at W=2 um, then W=1 um, nf=1 in both cases.
All L=.15 um. The eleven comparator MOS retain their existing width-4
definition, including the W=8 um tail and their original fingers. No other
device, connection, model, stimulus, clock or acceptance window changes.

## Budget and interpretation

Exactly two TT / 1.8 V / 27 C calls, in order 2 then 1 um; stop afterward
regardless of outcome. No retry, adaptive selection, PVT, topology change,
extra size or product integration. This is a NEW approved two-call family,
not an extension of Entry 108's failed grid. The real comparator is included;
ideal sources supply only its input/common-mode and external clock, as before.

Hypothesis: reducing the whole buffer/storage chain's gate widths reduces the
load presented to the unchanged comparator without making the first buffer
drive an unchanged large downstream chain. It may also weaken drive/storage;
no speed, area-compliance or success claim is assumed.

Use the exact Entry 106/107 pattern (LinkConfig seed=1, 36 bits, four warmup),
hash-verified Entry 105 TT output common mode, +/-50 mV differential inputs,
5 GHz external clock, 2 ps edges, 96 ps high plateau, max step 1 ps. Keep
the original raw 88..98 ps and held 110..190 ps windows and VDD/2 decoding.
Both complementary raw decisions AND held bits must pass for all 32 bits.
Do not substitute the clean-input control or relax a missed window.

## Voltage diagnostics, not unearned reliability claims

Entry 110's saved buffer PMOS VDS briefly reaches about -2.014 V. Its 32/32
result is a LOGIC-only isolation result, not operation validated inside all
PDK model ranges. Preserve it unchanged and carry the caveat forward.

Save every named DUT terminal-node voltage on the same solver time axis and
derive signed VDS=Vd-Vs, VGS=Vg-Vs and VBS=Vb-Vs from the exact rendered
connections. Do not infer stress from node-to-ground voltage alone. Check
the published model-domain intervals, separately from the unchanged logic gate:

| Standard 1.8 V model | VDS | VGS | VBS |
|---|---|---|---|
| NFET | 0..1.95 V | 0..1.95 V | -1.95..0.3 V |
| PFET | -1.95..0 V | -1.95..0 V | -0.1..1.95 V |

Source: [SKY130 device details](https://skywater-pdk.readthedocs.io/en/main/rules/device-details.html),
standard 1.8 V NMOS/PMOS sections, checked 2026-09-06. These are documented
SPICE model-validity ranges, NOT absolute-maximum reliability ratings.
Report extrema and out-of-range sample counts per drawn transistor/quantity,
without clipping, a time exemption or an invented reliability tolerance.
No source/drain relabelling is applied. A reverse/off-state signed excursion
is distinguished from exceeding 1.95 V gate/drain magnitude; neither an
excursion nor a clean check independently proves damage or reliability.

Keep logic and range results separate. Missing/malformed terminal data is an
instrument failure. Even a logic pass with no range excursions is only a
nominal block result, not a PVT/DFE/receiver pass.

## Evidence and stopping

Use the shared dfe_slicer lock and strict fresh-process launcher. Save exact
decks, logs, primary/buffer/all-terminal traces, source common-mode provenance,
per-bit results, supply and external-source power, W*L-only inventory,
source/plan snapshots and SHA256 hashes, including failures. Tests before
implementation, complete before/after regression, reproduce raw results.
Legacy defaults and previous evidence stay unchanged. No RL/CTLE/Rs/Cs,
behavioral DFE, dashboard, cached demo or old report change. Further circuit
choices require owner approval after these two results.
