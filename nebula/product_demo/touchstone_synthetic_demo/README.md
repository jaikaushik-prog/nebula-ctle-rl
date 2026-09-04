# Synthetic Touchstone intake demo

This is a parser/product demonstration, **not measured channel evidence**.
`synthetic_board.s4p` is an intentionally simple reciprocal four-port fixture
whose S13/S31 magnitude falls with frequency.

Generate the report with:

```powershell
python -m nebula.channel_upload nebula/product_demo/touchstone_synthetic_demo/synthetic_board.s4p --ports 1 3 --out nebula/product_demo/touchstone_synthetic_demo/report
```

The report records the source hash, port map, Nyquist loss and fit residual.
It deliberately says `PROFILED_NOT_RL_VERIFIED`: uploading a file does not
transfer the frozen 315/315 result to that new channel.
