# Continuous-Cs production recovery integration - 15 September 2026

For exactly 6 dB / 2.5 GHz, automatic physical recovery now proposes the validated
`base480_cs1p02` continuous refinement before legacy bank setting 480, equally for
RL and classical selection modes. Other requests retain their previous ordering.
The prior result, its complete raw manifest and the exact normalized sizing are
checked before selection. No bank entry, training range, reward, tolerance or
scientific measurement definition was changed. The old two-entry physical
registry remains untouched.

The new candidate keeps `base_setting=480`, `bank_setting=null`, `bank_code=null`
and its explicit continuous candidate identity. Its geometry is derived by the
frozen adapter from the original base parameters with Cs multiplied by 1.02;
all other normalized coordinates are identical. The selection receipt records
the prior result and manifest hashes and states that the prior pass is for
selection only. Every future request still runs the fresh, unchanged 137-call
physical gate. A fresh failure is retained and billed before normal recovery
continues. The existing eight-candidate total ceiling and same-machine exclusion
lock remain in force. The adapter retains the normal per-invocation timeouts;
production recovery has no experiment-wide wall limit.

The experimental adapter, source snapshots, all three candidate results and
campaign manifests remain byte-for-byte frozen. Only `physical_recovery.py` and
the new `tests/test_continuous_cs_recovery.py` change production behavior. The
shared output renderer already accepts the explicit string candidate identity
and nullable bank code through its physical path. Continuous verification emits
a start progress event; its frozen adapter currently does not forward intermediate
corner progress to the UI.

Validation: four failure-first tests preceded implementation. The final focused
run passed 36 tests in 2.52 seconds, including exact-target exclusion, both-mode
ordering, evidence corruption refusal, unchanged canonical measurement source,
all-three experimental scheduling, fresh accepted and failed verification,
partial-failure billing and existing recovery behavior. No further SPICE, full
regression, report or package operation was performed for this integration.

Production recovery SHA-256 before: `3c1d4adbdb9f83964757df222335dc5f1d558adcbf7c2de00cce73866d3b5b14`.
Production recovery SHA-256 after: `2b54facab6b93d4dcbfcc011e3e38af17cef9564fcb3c8462d4f48075ee77c68`.
New test SHA-256: `39769d163dd635082cc2f88606ff7fbeb29a319c5d5eb71b131c1cdac0c0b7b7`.

See [the measured pilot results](TARGET_COVERAGE_CS_RESULTS_20260915.md) and
[its independent review](CONTINUOUS_CS_COVERAGE_REVIEW_20260915.json). The historical
campaign source fingerprints refer to the frozen old recovery source; this later
production extension does not revise that evidence.
