# Saved submission demonstration

This directory preserves the completed 3 dB / 1.9 GHz physical design run
`ab981d69dac840e9820155d7e46e14dc` for the owner to rehearse and record.
It is an exact-byte copy of the existing temporary run, not a new design run.
All 622 files (28,437,981 bytes), all 617 original evidence-manifest entries,
and the selected-eye reconstruction were independently verified on 14 September.
`preservation.json` records the source location and every copied file hash.
Original provenance paths remain unchanged; the copy does not rewrite history.

From the repository root, if the existing app is not already running:

```powershell
py -3.13 -m nebula.web --port 8765 --run-root nebula/product_demo/submission_runs_20260914 --no-browser
```

Open http://127.0.0.1:8765 and select the completed run. Measured peaking is
3.910115 dB at 2.131144 GHz; modeled eye is 341.791199 mV / 0.859375 UI.
315/315 means one fixed exported CTLE across 45 PVT corners and seven
constructed channel losses, using transistor AC response and ideal DFE scoring.
This is separate from both the earlier adaptive 9 dB automation receipt and
the integrated 73-device transistor receiver checkpoint. No video is implied.

The raw outputs and source snapshots are project-owned; external PDK libraries
are referenced, not bundled. This preserved run supports playback on the
configured project environment; it does not certify a clean-machine rebuild.
