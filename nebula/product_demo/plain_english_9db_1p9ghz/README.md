# Plain-English shielded-RL product example

This directory was generated offline with:

```powershell
python -m nebula.llm "I need about 9 dB of peaking with the peak near 1.9 GHz" --out nebula/product_demo/plain_english_9db_1p9ghz
```

The deterministic parser read the sentence as 9 dB peaking at 1.9 GHz, then
called the same frozen `rl-hybrid` product used by the numeric front door. No
API key or network connection was used.

Result: **315/315 channel/PVT conditions passed**. The frozen policy made 2,406
eye measurements; the simulator shield accepted an RL-visited code in 266
conditions, and the deterministic measured-bank fallback supplied 49.

Files:

- `design.json`: parsed request, 315 adaptive codes, per-condition policy
  traces, measured results and grounded explanation provenance.
- `design.cir`: exact representative TT/7.5 dB configuration sent to ngspice.
- `design_schematic.png`: schematic parsed from that exact deck.
- `rl_dashboard.png`: 7 x 45 RL-versus-fallback map and real adaptation trace.
- `explanation.txt`: deterministic prose containing only recorded facts.

The deck, schematic and dashboard are byte-identical to the numeric
`rl_hybrid_9db_1p9ghz` demo. Natural language changes only request entry and
explanation; it cannot alter the optimiser, widen S3, or fabricate a measured
result.
