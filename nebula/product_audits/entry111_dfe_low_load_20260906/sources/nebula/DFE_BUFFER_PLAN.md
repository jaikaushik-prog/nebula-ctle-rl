# Entry 107: approved buffered decision/hold experiment

Frozen 2026-09-06 before implementation and measurements. Owner said yes to
the buffered version proposed after Entry 106: same three widths, maximum
48 simulations. Rs/Cs work remains unchanged. This is not an RL training run.

## Exact change

Reuse the Entry 106 StrongARM decision circuit and NAND SR hold. Between each
raw decision node and its memory input insert TWO cascaded CMOS inverters:
`x -> bx1 -> bx`, `y -> by1 -> by`. Memory active-low inputs become `bx/by`.
Four inverters add eight PDK MOS instances: 27 MOS total. Each added NMOS and
PMOS has total W equal to that trial's existing width (4, 8 or 16 um),
L=0.15 um and nf=W/2 (2 um fingers). No geometry, bias, or other connection
changes in the original 19 devices except the four memory gate connections
from x/y to bx/by. Tail remains 2W. No ideal/behavioural buffer elements.

These are the approved starting dimensions, not claimed optimal sizes.
Hypothesis: isolation may reduce the preferred-zero behaviour observed with
the direct dynamic-node/memory connection. Success or failure does not by
itself isolate every physical mechanism; report observations, not certainty.

## Unchanged experiment and stopping rule

Reuse Entry 106's single stimulus generator, trace reader and per-bit gate.
36 bits (four warmup + 32 scored), same `LinkConfig.seed=1`, +/-50 mV input
differential levels, measured/hash-verified Entry 105 output common mode per
corner, external 5 GHz clock, 2 ps edges, 96 ps high plateau, 1 ps max step.

The executable gate's raw window is 88-98 ps after the evaluation edge and
the held window is 110-190 ps. These remain EXACTLY unchanged; Entry 106's
plan described the raw window approximately as the final 10 ps before reset.
No new timing/amplitude tolerance, relaxed polarity or scoring threshold.

1. Three nominal TT/1.00/27 C calls, W=4/8/16 um.
2. Select the smallest passing width; if none pass, STOP after three calls.
3. For that one frozen width, run all 45 specified process/supply/temperature
   conditions. Keep every result including failures. No reselection after PVT.
4. Maximum 48 calls total. No retry, alternate buffering, resized device,
   changed clock phase or broadened search after results become visible.

Record raw buffer-node waveforms in an additional file for diagnosis, without
changing the original measurement vectors or decision gate. Refuse malformed
or missing auxiliary data; do not use extra traces to relax the pass rule.
Keep net DUT VDD power, ideal external clock net/positive-supplied power and
input-source power distinct. MOS W*L subtotal includes the eight new devices;
full layout area remains unknown. No complete receiver-power claim.

## Evidence, implementation boundaries and acceptance

Old renderer/experiment defaults and all Entry 106 raw files remain unchanged.
Add an explicit opt-in buffered mode, never monkeypatch the old circuit or
duplicate the PDK cards. Unit tests must prove the exact connectivity delta,
legacy deck byte equality, correct W/L/nf inventory, unmodified stimulus and
measurement block, old raw-result reproduction and 3/48-call stopping logic.

Tests first; full suite before/after. Save plan/source snapshots, exact decks,
logs, both waveform files, per-bit results, source common-mode provenance and
SHA256 manifest in a new Entry 107 directory. Never inherit a cached pass.

A passing result is a standalone decision/hold block only, NOT a complete
one-tap DFE. Causal previous-bit register, summing/tap circuit, connected CTLE
loading/kickback, actual clock generation, mismatch, dynamic noise and complete
receiver eyes/power/area remain unverified. Do not change CTLE/RL/product/UI,
old demo/report, Rs/Cs work or existing compliance claims in this experiment.
