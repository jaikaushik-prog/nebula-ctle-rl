# Entry 138: partial loaded initialization recovery

The unchanged transistor CTLE + configurable Rs/Cs + DFE has three accepted
held-state/polarity measurements out of four. Both original state-0 branches
now initialize correctly. State-1 negative reproduces the accepted prior
DC/AC/noise/power reference. State-1 positive still produces a convergence
warning and is rejected, even though ngspice exits normally.

Accepted input-referred noise is approximately 0.63584 mVrms over 10 MHz-5 GHz;
VDD power is 9.276-9.281 mW. The loaded peak is 1.747-1.750 GHz, so the
requested 1.9 GHz target still misses the internal 100 MHz tolerance.
These are held-clock small-signal noise results, not periodic receiver noise.

The frozen four-state gate remains FAILED. No HD3 call ran. A released
`.nodeset` guess is numerical initialization, not hardware reset. Generic
poly voltage-dependent nonlinearity, full receiver signoff and loaded map
accuracy remain unverified. Entry 139 separately registers clocked distortion
from the accepted starting state without revising this result.

Evidence: `product_audits/entry138_dfe_loaded_initialization_20260910/`.
Exactly four calls, 129.7941215 s including 0.1767439 s preflight; no retries.
Source freeze: ca8cfb9246dbf62ce6ea80c4c362b46b9a567a90. Source and PDK hashes
unchanged. All 106 manifested files plus manifest are retained. Five tests
verify complete membership and replay all accepted/rejected measurements.
