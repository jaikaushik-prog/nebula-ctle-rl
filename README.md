# SerDes DSP Framework
## DSP-Assisted Wireline & Optical Transceiver Design Environment

**Target:** 112G/224G PAM-4 SerDes | Silicon Photonics | Co-Packaged Optics  
**Technology:** 28nm CMOS (methodology scales to FinFET)  
**Tools:** Python · MATLAB · Verilog-A · SystemVerilog · Cadence Spectre AMS

---

## Repository Structure

```
serdes_dsp_framework/
│
├── python_models/              Python behavioral simulation
│   ├── channel.py              S-parameter / loss-model channel + waveform apply()
│   ├── pam4_chain.py           PRBS, scrambler, Gray coding, TX FFE,
│   │                           oversampled TX waveform w/ RJ+SJ injection
│   ├── equalizers.py           FFE, DFE (joint single-pass LMS), MLSE, MMSE init
│   ├── statistical_eye.py      Semi-analytic BER engine (StatEye-class):
│   │                           ISI PMF + Q-folding, bathtub to 1e-15,
│   │                           CTLE optimizer w/ CDR-feasibility constraint
│   ├── rx_frontend.py          CTLE (1z/2p), AGC, CDR-driven sampler
│   │                           (Alexander BB PD + PI loop, TI mismatch, ADC)
│   ├── cdr.py                  Standalone CDR study models (TEDs, loop filters)
│   ├── adc_model.py            TI-ADC, aperture jitter, ENOB, mismatch
│   ├── optical_dsp.py          CD compensation, coherent DSP, IM-DD
│   ├── visualization.py        Eye diagrams, BER curves, bathtub plots
│   └── link_sim.py             Waveform-level link harness + CLI sweeps
│
├── tests/                      pytest suite (48 tests) — run `pytest tests`
│
├── veriloga_models/            Cadence Spectre VerilogA behavioral models
│   ├── tia.vams                TIA (single-ended + differential)
│   └── analog_frontend.vams    CTLE, VGA, ADC, VCO, Photodiode, Loop filter
│
├── rtl/                        Synthesisable SystemVerilog RTL
│   ├── ffe_dfe_lms.sv          32-parallel FFE + speculative DFE + SS-LMS
│   └── bb_cdr_ber.sv           Bang-bang CDR + PRBS-31 BER checker
│
├── matlab_models/              MATLAB algorithm verification
│   └── dsp_verify.m            FFE/DFE, fixed-point, BER sweeps, CDR Bode
│
├── scripts/
│   └── cadence/
│       └── ams_setup.ocn       Ocean: AMS setup, PVT corners, Monte Carlo
│
├── ams/                        Cadence AMS testbench configuration
├── verification/               UVM testbenches (add per block)
├── results/                    Simulation output CSVs (auto-created)
└── docs/                       Block diagrams, link budgets
```

---

## Quick Start

### 1. Install Python dependencies
```bash
pip install numpy scipy matplotlib pandas scikit-rf
```

### 2. Run unit + end-to-end tests
```bash
python -m pytest tests
```

### 3. Single link simulation (waveform engine, closed CDR loop)
```bash
cd python_models
python link_sim.py --channel_cm 3 --snr_db 26 --plot
```

### 4. BER vs SNR sweep (with no-ISI theory overlay)
```bash
python link_sim.py --mode sweep_snr --channel_cm 3
```

### 5. Channel loss sweep / Monte Carlo / jitter tolerance
```bash
python link_sim.py --mode sweep_loss --snr_db 28
python link_sim.py --mode monte_carlo --n_runs 50
python link_sim.py --mode jtol --channel_cm 3 --snr_db 26
```

### 6. Statistical (semi-analytic) BER + link optimization
```bash
python link_sim.py --mode statistical --channel_cm 3 --snr_db 26   # bathtub, eye width, CDR feasibility
python link_sim.py --mode optimize   --channel_cm 6 --snr_db 28    # CTLE sweep w/ timing constraint
python make_report_figures.py                                       # all report figures
```

> Two engines, one link: the **time-domain** engine counts errors (floor
> ~1e-5, Wilson confidence bounds); the **statistical** engine computes BER
> semi-analytically to 1e-15. They are built from the same LinkConfig and
> cross-validated against each other (see tests/test_statistical_eye.py and
> results/fig5_crossval.png).

### 6. MATLAB verification
```matlab
cd matlab_models
run('dsp_verify.m')
run_all()          % runs all test suites
ber_vs_snr()       % BER sweep only
cdr_loop_analysis() % CDR Bode + JTOL
```

### 7. Cadence AMS simulation
```
Load ams_setup.ocn in Cadence IC Virtuoso:
  CIW> load("scripts/cadence/ams_setup.ocn")
  CIW> runAMSSim()
  CIW> sweepCTLEPeaking()
  CIW> runMonteCarlo(50)
  CIW> runPVTCorners()
```

---

## Design Parameters (112G PAM-4 Reference Design, 28nm CMOS)

| Parameter | Value | Notes |
|---|---|---|
| Baud rate | 56 Gbaud | 2 b/sym PAM-4 |
| Channel loss @ Nyquist | 25 dB | 30cm PCB, FR4 |
| TIA transimpedance | 2 kΩ | 180nm SOI variant |
| TIA bandwidth | 35 GHz | |
| CTLE peaking | 0–15 dB (4-bit) | Active, tunable |
| ADC | 6-bit, 56 GS/s, 16× TI | ENOB target 5.3 |
| Aperture jitter | < 150 fs rms | |
| FFE | 3 pre + 1 + 17 post | 32-parallel, SS-LMS |
| DFE | 5 taps | Speculative tap 1 |
| CDR | Type-II BB, PI filter | 1.75 GHz system clock |
| Parallelism | 32× | fbaud/1.75GHz |
| FEC | KP4 RS(544,514) | Pre-FEC target 2.4×10⁻⁴ (random errors, 802.3bs); design margin target 1×10⁻⁴. 224G/802.3dj concatenated Hamming(128,120)+KP4 relaxes this to ~10⁻³ |
| Power budget | ~350 mW/lane | 3.1 pJ/bit |

---

## Fixed-Point Format Summary

| Block | Word width | Format | Notes |
|---|---|---|---|
| ADC output | 6-bit signed | integer | ±32 LSB range |
| FFE input buffer | 6-bit signed | integer | shift register |
| FFE coefficients | 10-bit signed | Q2.8 | ±1.99, 1/256 LSB |
| FFE output | 18-bit signed | extended | prevents MAC overflow |
| DFE feedback | 10-bit signed | Q2.8 | same as FFE |
| LMS accumulator | 16-bit signed | Q4.12 | high-precision update |
| CDR phase acc | 10-bit | unsigned | 0.1° resolution |
| CDR freq word | 20-bit signed | fractional | frequency offset |

---

## Module API Reference

### `channel.py`
```python
ch = Channel.from_loss_model(alpha_skin=0.30, alpha_diel=0.05, length_cm=30)
ch = Channel.from_sparam('channel.s4p', port_pair=(1,2))
ch = Channel.optical_imdd(bw_laser=30e9, bw_pd=35e9, cd_ps_nm=10.0)
il_db  = ch.nloss_at_nyquist(fbaud=56e9)
pr     = ch.pulse_response(fbaud=56e9, osr=8)
taps   = ch.isi_taps(fbaud=56e9)
rx_n   = Channel.add_awgn(rx, snr_db=20)
```

### `equalizers.py`
```python
rx = FFEDFEReceiver(n_ffe_pre=3, n_ffe_post=17, n_dfe=5, adc_bits=6)
rx.ffe.init_from_channel(h_ch, snr_db=20)
decisions, ber_trace = rx.process(r, ref_bits=bits, training_len=5000)
# Standalone FFE:
ffe = FFE(n_pre=3, n_post=17, mu=5e-4, ss_lms=True)
y, e = ffe.process(r, ref=ref_syms, adapt=True)
# MLSE:
mlse = MLSE(h_ch[:4])
d = mlse.detect(r[:2000])
```

### `cdr.py`
```python
cdr = MuellerMullerCDR(Kp=0.015, Ki=8e-4)
phase, err = cdr.update(r_now, d_now)
# BB CDR (2× oversampled):
bb = BangBangCDR(Kp=0.01, Ki=5e-4, fbaud=56e9, step_ui=0.02)
baud_out, result = bb.process(r_2x)
print(f"RMS jitter: {result.rms_jitter_ui:.4f} UI")
```

### `adc_model.py`
```python
adc = ADC(n_bits=6, f_s=56e9, v_ref=0.5, jitter_rms_ps=0.15, n_sub=16)
y = adc.convert(x, apply_ti_mismatch=True)
sinad, enob = adc.characterise(f_in=1e9)
```

### `optical_dsp.py`
```python
# CD compensation:
rx_comp = cd_compensate_freq_domain(rx_cd, f_s=64e9, D=17.0, L_km=80.0)
# Coherent DSP chain:
dsp = CoherentDSP(f_s=64e9, fbaud=32e9, D_ps_nm_km=17.0, L_km=80.0)
rx_x, rx_y = dsp.process(sig_x, sig_y)
# IM-DD link:
link = IMDDLink(er_db=6.0, p_avg_dbm=-3.0, tia_noise_a_rthz=15e-12)
I_pd = link.transmit(symbols, f_s=56e9)
snr  = link.snr_db(fbaud=56e9)
```

---

## VerilogA Model Usage in Spectre

```spice
; TIA (optical receiver front-end)
XTIA (net_iin net_vout vdd vss) tia
+  Zt=2e3 f3dB=35e9 noise_A=15e-12 Vout_max=0.8

; CTLE with 4-bit digital peaking control
XCTLE (net_vout net_veq vdd vss net_ctle_ctrl) ctle
+  f_zero=18e9 f_pole=45e9 peaking_max_db=15

; 6-bit 56GS/s ADC
XADC (net_veq net_clk<5:0> vdd vss) adc_6b_56g
+  Vref_p=0.5 Vref_n=-0.5 tj_rms=150e-15 n_sub=16

; Photodiode
XPD (net_popt net_iphoto vbias vss) photodiode
+  responsivity=0.8 f_bw=35e9
```

---

## RTL Integration Notes

- **Synthesis target:** 1.75 GHz in 28nm (for 32-parallel 56G)
- **Timing critical paths:**
  - FFE adder tree: 3 pipeline stages (target < 570 ps/stage)
  - DFE tap-1 speculation: must complete within 570 ps
  - CDR phase accumulator: 1 cycle at 1.75 GHz
- **Clock domains:**
  - `clk_baud_div32` = 1.75 GHz — ADC + FFE + DFE + LMS
  - `clk_fec`        = 437.5 MHz — FEC encoder/decoder (÷4)
  - `clk_ref`        = 156.25 MHz — management, adaptation (÷32)
- **CDC crossings:** elastic FIFOs at all domain boundaries (min depth: 16)

---

## Research Extensions

| Topic | Entry Point | Key Files |
|---|---|---|
| ML equalizer | Replace `FFEDFEReceiver` with PyTorch inference | `equalizers.py` |
| Cryogenic CMOS | Scale noise params in VerilogA models to 4K | `analog_frontend.vams` |
| 224G (112 Gbaud) | Double `fbaud`, increase FFE/DFE taps | `link_sim.py` config |
| Co-packaged optics | Use `optical_imdd` channel, short reach | `optical_dsp.py` |
| THP precoding | Add `thp_precoder.py` module to TX chain | `pam4_chain.py` |
| ADC-aware CTLE | Joint optimisation in `link_sim.py` sweep | `link_sim.py` |

---

*BITS Pilani, EEE Department — Analog/RF/Mixed-Signal VLSI Group*  
*Contact: N. Mishra*
