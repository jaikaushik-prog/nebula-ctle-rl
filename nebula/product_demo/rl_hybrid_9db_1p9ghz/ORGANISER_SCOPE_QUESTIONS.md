# Scope clarification - draft for the organisers

Not sent. Please send this to the official competition contact and retain their reply.

Subject: Clarification of DFE, physical tunability and area/power scope

Hello,

We are building the RL-driven automated equalizer design flow for the 5 Gbps
PCIe Gen2 problem statement. Before finalising the implementation, could you
please clarify these requirements?

1. For "CTLE + 1-tap DFE", must the DFE, slicer and clocked feedback be
   transistor-level SPICE circuits, or is a transistor-level SKY130 CTLE
   connected to an explicitly disclosed behavioural 1-tap DFE acceptable?
2. For "variable Rs, Cs", must one fabricated circuit include physical selector
   switches covering the tuning range, or may the framework generate a different
   fixed, physically drawn Rs/Cs configuration for each requested specification?
   If settings may change across PVT, is per-corner retuning permitted?
3. Do the 0.05 mm2 and 15 mW limits include the complete receiver (DFE, slicer,
   clocking, bias generation and tuning controls)? What area evidence is expected:
   drawn-device estimate, placed core bounding box, or DRC-clean layout?

Our current implementation includes a real SKY130 CTLE and input-attenuator
switches. The DFE is behavioural; Rs/Cs variants are independently drawn passive
configurations, not a completed switch matrix. We will clearly distinguish
these boundaries and will not claim full-receiver area/power compliance from
partial CTLE measurements.

Thank you.
