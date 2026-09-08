# Preflight refusal, zero simulator calls

2026-09-06: source-manifest lookup expected forward slashes but the Entry 105
manifest uses Windows backslashes. SHA256 of the unchanged TT log actually
matches ff374ec3d84b3ab3fce229d018616fab57a3137a049e99cab141fe3198c86b9d.
No DUT deck or simulator process was launched, so no physical finding exists.
Initial source snapshots retained. Add a failing Windows-path regression test,
normalize separators without relaxing the hash check, then start into a fresh
directory. This does not extend the registered 48-call budget.
