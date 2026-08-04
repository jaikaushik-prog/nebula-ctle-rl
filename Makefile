# ============================================================================
# Makefile — SerDes DSP Framework build and simulation automation
# ============================================================================

PYTHON    := python3
PY_DIR    := python_models
RTL_DIR   := rtl
VER_DIR   := verification
RES_DIR   := results
SIM_DIR   := simulation
XCELIUM   ?= xrun          # Cadence Xcelium (or substitute vcs / iverilog)
GENUS     ?= genus          # Cadence Genus for synthesis

.PHONY: all clean sim_python sim_rtl sim_ber sim_monte_carlo \
        sim_sweep_snr sim_sweep_loss synthesis lint help

# ── Default ──────────────────────────────────────────────────────────────────
all: check_deps sim_python

# ── Setup ─────────────────────────────────────────────────────────────────────
setup:
	@echo "Installing Python dependencies..."
	pip install -r requirements.txt
	@mkdir -p $(RES_DIR) $(SIM_DIR)
	@echo "Setup complete."

check_deps:
	@$(PYTHON) -c "import numpy, scipy, matplotlib, pandas" 2>/dev/null \
		|| (echo "ERROR: Missing Python deps. Run: make setup" && exit 1)
	@echo "Python dependencies OK."

# ── Python simulations ────────────────────────────────────────────────────────
sim_python: check_deps
	@echo "=== Running 112G PAM-4 link simulation ==="
	$(PYTHON) $(PY_DIR)/link_sim.py

sim_ber:
	@echo "=== BER vs SNR sweep ==="
	$(PYTHON) $(PY_DIR)/link_sim.py --mode sweep_snr \
		--fbaud 56e9 --channel_cm 30 --n_symbols 30000 \
		--out_csv $(RES_DIR)/ber_vs_snr.csv

sim_sweep_loss:
	@echo "=== Channel loss sweep ==="
	$(PYTHON) $(PY_DIR)/link_sim.py --mode sweep_loss \
		--fbaud 56e9 --n_symbols 30000 \
		--out_csv $(RES_DIR)/sweep_loss.csv

sim_monte_carlo:
	@echo "=== Monte Carlo simulation (50 runs) ==="
	$(PYTHON) $(PY_DIR)/link_sim.py --mode monte_carlo \
		--n_runs 50 --n_symbols 20000 \
		--out_csv $(RES_DIR)/monte_carlo.csv

sim_optical:
	@echo "=== Optical DSP test ==="
	$(PYTHON) -c "\
from python_models.optical_dsp import *; \
import numpy as np; np.random.seed(0); \
dsp = CoherentDSP(f_s=64e9, fbaud=32e9, D_ps_nm_km=17.0, L_km=80.0); \
N=4096; tx=np.exp(1j*np.random.choice([0,1.5708,3.14159,4.71239],N)); \
rx,_=dsp.process(apply_phase_noise(tx,100e3,64e9),tx); \
print('Coherent DSP OK, SNR=%.1f dB' % (20*np.log10(np.mean(np.abs(rx)))))"

# ── Unit tests ────────────────────────────────────────────────────────────────
test:
	@echo "=== Running Python unit tests ==="
	$(PYTHON) $(PY_DIR)/channel.py
	$(PYTHON) $(PY_DIR)/pam4_chain.py
	$(PYTHON) $(PY_DIR)/equalizers.py
	$(PYTHON) $(PY_DIR)/adc_model.py
	$(PYTHON) $(PY_DIR)/cdr.py
	$(PYTHON) $(PY_DIR)/optical_dsp.py
	@echo "=== All unit tests PASSED ==="

# ── RTL simulation ────────────────────────────────────────────────────────────
sim_rtl:
	@echo "=== RTL simulation (Xcelium) ==="
	@mkdir -p $(SIM_DIR)/rtl
	$(XCELIUM) \
		$(RTL_DIR)/ffe_dfe_lms.sv \
		$(RTL_DIR)/bb_cdr_ber.sv \
		$(VER_DIR)/tb_ffe_dfe.sv \
		-sv -timescale 1ps/1fs \
		-access +rwc \
		-log $(SIM_DIR)/rtl/xrun.log \
		-run

# ── RTL lint ─────────────────────────────────────────────────────────────────
lint:
	@echo "=== RTL lint check ==="
	$(XCELIUM) $(RTL_DIR)/ffe_dfe_lms.sv $(RTL_DIR)/bb_cdr_ber.sv \
		-sv -elaborate -nocopyright -nolog

# ── Synthesis (Cadence Genus) ─────────────────────────────────────────────────
synthesis:
	@echo "=== RTL synthesis (Genus, 28nm) ==="
	@mkdir -p $(SIM_DIR)/synthesis
	$(GENUS) -legacy_ui -f scripts/genus_synthesis.tcl \
		| tee $(SIM_DIR)/synthesis/genus.log

# ── Results plotting ──────────────────────────────────────────────────────────
plot_results:
	@echo "=== Plotting simulation results ==="
	$(PYTHON) -c "\
import pandas as pd, matplotlib.pyplot as plt; \
df=pd.read_csv('$(RES_DIR)/ber_vs_snr.csv'); \
plt.figure(); \
plt.semilogy(df.snr_db, df.final_ber, 'o-', label='Simulation'); \
plt.grid(True); plt.xlabel('SNR [dB]'); plt.ylabel('BER'); \
plt.title('BER vs SNR — 112G PAM-4'); plt.legend(); \
plt.savefig('$(RES_DIR)/ber_vs_snr.png', dpi=150); \
print('Plot saved to $(RES_DIR)/ber_vs_snr.png')"

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	rm -rf $(SIM_DIR) __pycache__ $(PY_DIR)/__pycache__ *.pyc
	rm -rf xrun.d xcelium.d .simvision
	@echo "Clean complete."

clean_results:
	rm -rf $(RES_DIR)/*.csv $(RES_DIR)/*.png
	@echo "Results cleaned."

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo "SerDes DSP Framework — Make targets:"
	@echo ""
	@echo "  setup            Install Python dependencies"
	@echo "  test             Run all Python module unit tests"
	@echo "  sim_python       Default 112G PAM-4 link simulation"
	@echo "  sim_ber          BER vs SNR sweep → results/ber_vs_snr.csv"
	@echo "  sim_sweep_loss   Channel loss sweep"
	@echo "  sim_monte_carlo  50-run Monte Carlo"
	@echo "  sim_optical      Optical DSP (CD + coherent) test"
	@echo "  sim_rtl          RTL simulation with Xcelium"
	@echo "  lint             RTL lint check"
	@echo "  synthesis        Cadence Genus synthesis (28nm)"
	@echo "  plot_results     Plot CSV results to PNG"
	@echo "  clean            Remove simulation artifacts"
	@echo ""
	@echo "Variables:"
	@echo "  XCELIUM=xrun     Verilog simulator binary"
	@echo "  GENUS=genus      Synthesis tool binary"
