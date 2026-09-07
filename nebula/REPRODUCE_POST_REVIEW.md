# Reproducing the reviewed Nebula submission

The release is a private working-tree source/evidence snapshot, including the
previously uncommitted physical product implementation. It is not a claim that
all files came from one clean Git commit. RELEASE_MANIFEST.json records every
included file hash, the Git HEAD, Python version and observed package versions.

## What is reproducible now

The original final example is:
nebula/product_demo/physical_bias_9db_1p9ghz_20260906/

Supplemental evidence is in:
nebula/product_audits/entry113_attribution_20260907/
nebula/product_audits/entry113_coverage_20260907/
nebula/product_audits/entry113_models_20260907/

Each contains its own hash manifest. POST_REVIEW_RESULTS.md explains scope,
costs and failures. The PDF includes the new results on pages 18 and 19.

From the repository root on the documented development machine:

    py -3.13 -m pytest tests nebula/tests -q -m "not slow"
    py -3.13 -m nebula.report.competition_submission
    py -3.13 -m nebula.report.check_competition_pdf

A fresh physical design run (137 maximum calls; choose a new directory):

    py -3.13 -m nebula.design --method rl-physical --peaking 9 --f-peak 1.9 --out output/my_physical_design

The CLI frequency argument is GHz; the Python physical_design.run argument is Hz.
The browser now visibly selects physical mode by default; the API's historical
default remains unchanged for compatibility. The generated request is still
validated, and unsupported bank requests are refused.

The experimental runners are anti-overwrite and require the protocol to match
its committed version. Rerun them from the private checkout containing protocol
commit 030b8f2 into NEW output directories; do not overwrite the supplied results.
Replaying an already exposed set does not create new held-out evidence.

## Environment boundary

- Development interpreter: system Python 3.13; exact observed versions are in
  requirements-reviewed.txt and RELEASE_MANIFEST.json.
- Simulator: ngspice 41, ngspice_con.exe, installed in the nebula conda environment.
- Full SKY130A remains external. Recorded volare revision:
  c6d73a35f524070e85faff4a6a9eef49553ebc2b.
- Current PDK pointers use C:/Users/DELL/sky130A. They are machine-specific.
  Model hashes in the supplemental model audit allow checking the actual
  installed resistor cards.
- Generated trim libraries reference the external PDK. Do not casually replace
  them or the PDK; changes require the electrical equality checks and new
  circuit verification.
- The runners copy .spiceinit into their simulation directory and use fresh
  ngspice parses. Preserve it, scale=1e-6 semantics, and micron instance values.
- No API credential is included. A configured LLM client was unavailable;
  default natural-language parsing is deterministic, and live LLM use is
  NOT_VERIFIED.

requirements-reviewed.txt is an observed version inventory, not a tested
cross-platform lock. A clean-machine package installation and complete physical
run remain NOT_VERIFIED. Extracted-copy checks on this host are reported
separately; they do not remove the external PDK and environment requirements.

## Verify the release

The packager checks membership, rejects reference PDFs and credential files,
and hashes every included payload. To verify an archive using this checkout:

    py -3.13 -c "from nebula.release_snapshot import verify_archive; verify_archive('output/release/Nebula_Reviewed_Submission_20260907.zip'); print('PASS')"

The ZIP's companion .sha256 fingerprints the whole archive. The full PDK,
copyrighted reference PDFs, Git metadata, credentials and caches are excluded.
Keep this release private. No upload or push is performed by the packager.

## What must not be claimed

One of twelve enumerated requests passed all fixed physical model conditions.
Eight bank refusals are not physical impossibility; the other three selected
physical candidates have measured failures or rejected linear-eye assumptions.
The behavioural DFE, unknown full receiver area/power, ignored resistor voltage
dependence and synthetic/noiseless eye assumptions remain explicit boundaries.
