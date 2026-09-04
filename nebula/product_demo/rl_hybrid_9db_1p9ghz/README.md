# Shielded-RL product example

This directory was generated with:

```powershell
python -m nebula.design --method rl-hybrid --peaking 9 --f-peak 1.9 --out nebula/product_demo/rl_hybrid_9db_1p9ghz
```

The user supplied only the desired CTLE response: 9 dB peaking near 1.9 GHz.
Channel loss was not a target. The product automatically checked all seven
characterised channel losses across all 45 PVT corners.

Result: **315/315 channel/PVT conditions passed** the V6 simulator-backed
acceptance set. The frozen policy proposed 2,406 measured settings; the
classical safety fallback was used for 49 conditions. This is the combined
RL-proposer + verifier + fallback product result, not a pure-RL compliance
claim.

Files:

- `design.json`: complete 315-condition adaptive code map, measured results,
  and the actor's actual eye-measurement/action trace for every condition.
- `design.cir`: exact representative TT/7.5 dB configuration sent to ngspice.
- `design_schematic.png`: schematic drawn by parsing that exact deck.
- `rl_dashboard.png`: judge-facing 7 x 45 map of RL-versus-fallback decisions
  plus the longest real adaptation trace from this run.
- `programmable_architecture.png`: all 512 logical A/R/C settings, their exact
  target values and the selected code. It labels the PMOS attenuator as
  netlisted/measured and the Rs/Cs selector switches as not yet netlisted.

The single deck is representative. It is not one fixed configuration claimed
to pass all 315 conditions; the verified attenuator/Rs/Cs code is allowed to
change according to the map in `design.json`.

The Rs/Cs values in the code map were each measured as a separately drawn
passive geometry. This demo does not claim that their physical selector switch
transistors or parasitics have been implemented.
