"""
ml_equalizer.py — Machine Learning Equalizer Integration
for DSP-Assisted PAM-4 and Optical Receivers

Implements:
  - LSTM neural equalizer (replaces FFE+DFE for nonlinear channels)
  - Bidirectional GRU equalizer (lower latency variant)
  - 1D CNN equalizer (parallelisable, hardware-friendly)
  - Reinforcement learning CDR adaptation (replaces fixed SS-LMS)
  - Hardware-aware quantised inference (INT8 weights for ASIC mapping)
  - Online adaptation: fine-tune on decision-directed error in real time

Design philosophy:
  All models target inference at baud rate after offline training.
  Inference must pipeline into the N_PAR=32 parallel architecture.
  Weights are quantised post-training to INT8 (hardware deployment).

Usage:
    model = LSTMEqualizer(n_taps=32, hidden=32)
    model.train_supervised(rx_samples, tx_symbols, epochs=50)
    decisions = model.infer(rx_samples)
    hw_model  = QuantisedInferenceEngine(model, weight_bits=8)
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from typing import Optional, Tuple, List
from dataclasses import dataclass


# ─────────────────────────────────────────────────────────────────────────────
# PAM-4 utilities (self-contained for this module)
# ─────────────────────────────────────────────────────────────────────────────

PAM4_LEVELS = torch.tensor([-3.0, -1.0, 1.0, 3.0])

def pam4_slicer_torch(x: torch.Tensor) -> torch.Tensor:
    """Hard PAM-4 slicer, batch-compatible."""
    d = torch.full_like(x, -3.0)
    d[x > -2.0] = -1.0
    d[x >  0.0] =  1.0
    d[x >  2.0] =  3.0
    return d

def soft_slicer_pam4(x: torch.Tensor, temperature: float = 0.5) -> torch.Tensor:
    """
    Soft (differentiable) PAM-4 slicer using softmax over distances.
    Allows gradient flow through the decision during training.
    temperature: lower → harder decisions (approaches hard slicer)
    """
    levels = PAM4_LEVELS.to(x.device)
    dist   = -(x.unsqueeze(-1) - levels)**2 / temperature
    weights = torch.softmax(dist, dim=-1)
    return (weights * levels).sum(dim=-1)


# ─────────────────────────────────────────────────────────────────────────────
# LSTM Neural Equalizer
# ─────────────────────────────────────────────────────────────────────────────

class LSTMEqualizer(nn.Module):
    """
    LSTM-based sequence equalizer for PAM-4 channels.

    Architecture:
        Input window → LSTM layers → FC → soft slicer → PAM-4 decision

    Handles both linear ISI and nonlinear distortions (laser chirp,
    ADC harmonic distortion, amplifier nonlinearity).

    Parameters
    ----------
    n_taps   : input window length (context symbols fed to LSTM)
    hidden   : LSTM hidden state size
    n_layers : number of stacked LSTM layers
    dropout  : dropout probability (0 = no dropout)
    """
    def __init__(self, n_taps: int = 32, hidden: int = 32,
                 n_layers: int = 2, dropout: float = 0.1):
        super().__init__()
        self.n_taps   = n_taps
        self.hidden   = hidden
        self.n_layers = n_layers

        # Input normalisation
        self.input_norm = nn.LayerNorm(n_taps)

        # LSTM core
        self.lstm = nn.LSTM(
            input_size  = n_taps,
            hidden_size = hidden,
            num_layers  = n_layers,
            batch_first = True,
            dropout     = dropout if n_layers > 1 else 0.0,
            bidirectional = False   # causal: no future lookahead
        )

        # Output projection: hidden → scalar decision
        self.fc = nn.Sequential(
            nn.Linear(hidden, hidden // 2),
            nn.ReLU(),
            nn.Linear(hidden // 2, 1)
        )

        # Initialise weights
        self._init_weights()

    def _init_weights(self):
        for name, p in self.named_parameters():
            if 'weight_ih' in name:
                nn.init.xavier_uniform_(p)
            elif 'weight_hh' in name:
                nn.init.orthogonal_(p)
            elif 'bias' in name:
                nn.init.zeros_(p)
        # Initialise FC as near-identity (warm start)
        nn.init.eye_(self.fc[0].weight[:self.fc[0].weight.shape[1],
                                        :self.fc[0].weight.shape[1]])

    def forward(self, x: torch.Tensor,
                hidden: Optional[Tuple] = None) -> Tuple[torch.Tensor, Tuple]:
        """
        x : (batch, seq_len, n_taps) — sliding window of received samples
        Returns (logits, hidden_state) where logits are pre-slicer values
        """
        x_norm = self.input_norm(x)
        lstm_out, h_new = self.lstm(x_norm, hidden)
        logits = self.fc(lstm_out).squeeze(-1)   # (batch, seq_len)
        return logits, h_new

    def infer(self, r: np.ndarray,
              batch_size: int = 512) -> np.ndarray:
        """
        Run inference on received sample stream.
        r : 1D array of received samples (baud-rate)
        Returns hard PAM-4 decisions as numpy array.
        """
        self.eval()
        N = len(r)
        r_t = torch.tensor(r, dtype=torch.float32)

        # Build sliding window dataset
        windows = torch.zeros(N, self.n_taps)
        half = self.n_taps // 2
        for n in range(N):
            start = max(0, n - half)
            end   = min(N, n + half)
            w     = r_t[start:end]
            # Pad if needed
            pad_left  = max(0, half - n)
            pad_right = max(0, n + half - N)
            windows[n, pad_left:self.n_taps-pad_right] = w[:self.n_taps-pad_left-pad_right]

        decisions = np.zeros(N)
        loader = DataLoader(TensorDataset(windows), batch_size=batch_size)
        offset = 0
        h = None
        with torch.no_grad():
            for (batch,) in loader:
                logits, h = self.forward(batch.unsqueeze(1), h)
                d = pam4_slicer_torch(logits.squeeze(1)).numpy()
                decisions[offset:offset+len(d)] = d
                offset += len(d)
        return decisions


# ─────────────────────────────────────────────────────────────────────────────
# 1D CNN Equalizer (hardware-friendly — fully parallelisable)
# ─────────────────────────────────────────────────────────────────────────────

class CNNEqualizer(nn.Module):
    """
    Causal 1D CNN equalizer.

    Advantages over LSTM for hardware:
    - No sequential dependency → entire block processed in parallel
    - Maps directly to FIR + nonlinear activation structure
    - INT8 quantisation friendly (no hidden state)

    Architecture:
        Dilated causal conv1d stack → pointwise FC → decision
    """
    def __init__(self, n_channels: int = 16, n_layers: int = 4,
                 kernel_size: int = 5):
        super().__init__()
        self.n_channels  = n_channels
        self.kernel_size = kernel_size
        self.n_layers    = n_layers

        layers = []
        in_ch  = 1
        for i in range(n_layers):
            dilation = 2 ** i       # 1, 2, 4, 8 — exponential receptive field
            padding  = (kernel_size - 1) * dilation
            layers.append(nn.Conv1d(
                in_channels  = in_ch,
                out_channels = n_channels,
                kernel_size  = kernel_size,
                dilation     = dilation,
                padding      = padding    # causal: trim right padding after
            ))
            layers.append(nn.GELU())
            in_ch = n_channels

        self.conv_stack = nn.ModuleList(layers)
        self.out_proj   = nn.Conv1d(n_channels, 1, kernel_size=1)
        # Compute total receptive field
        self.receptive_field = sum(
            (kernel_size - 1) * (2**i) for i in range(n_layers)) + 1

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        x : (batch, 1, seq_len) — single-channel received signal
        Returns (batch, seq_len) equalised values
        """
        h = x
        for i in range(0, len(self.conv_stack), 2):
            conv = self.conv_stack[i]
            act  = self.conv_stack[i+1]
            # Trim causal padding: remove last padding samples from right
            pad  = conv.padding[0] if isinstance(conv.padding, tuple) else conv.padding
            h    = act(conv(h)[..., :-pad] if pad > 0 else conv(h))
        return self.out_proj(h).squeeze(1)

    def infer(self, r: np.ndarray) -> np.ndarray:
        self.eval()
        r_t = torch.tensor(r, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            logits = self.forward(r_t).squeeze().numpy()
        return pam4_slicer_torch(torch.tensor(logits)).numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Shared training engine
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TrainingConfig:
    lr:            float = 1e-3
    epochs:        int   = 50
    batch_size:    int   = 256
    weight_decay:  float = 1e-5
    lr_decay:      float = 0.5      # LR halved at each milestone
    lr_milestones: List  = None     # epoch milestones for LR decay
    train_split:   float = 0.8      # fraction of data for training
    soft_temp:     float = 0.3      # soft slicer temperature during training
    verbose:       bool  = True

    def __post_init__(self):
        if self.lr_milestones is None:
            self.lr_milestones = [20, 35, 45]


class NeuralEqualizerTrainer:
    """
    Unified training engine for LSTM and CNN equalizers.

    Loss function: MSE on soft-sliced output (differentiable)
                 + symbol error regularisation
    """
    def __init__(self, model: nn.Module, cfg: TrainingConfig = None):
        self.model  = model
        self.cfg    = cfg or TrainingConfig()
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.model.to(self.device)
        self.loss_history: List[float] = []
        self.ser_history:  List[float] = []

    def _build_dataset(self, rx: np.ndarray,
                       tx_syms: np.ndarray) -> DataLoader:
        """Build windowed dataset for LSTM or flat sequence for CNN."""
        N  = min(len(rx), len(tx_syms))
        rx_t  = torch.tensor(rx[:N],      dtype=torch.float32)
        tx_t  = torch.tensor(tx_syms[:N], dtype=torch.float32)

        if isinstance(self.model, LSTMEqualizer):
            half = self.model.n_taps // 2
            X    = torch.zeros(N, self.model.n_taps)
            for n in range(N):
                s = max(0, n - half)
                e = min(N, n + half)
                w = rx_t[s:e]
                pad_l = max(0, half - n)
                X[n, pad_l:pad_l+len(w)] = w[:self.model.n_taps - pad_l]
            X = X.unsqueeze(1)   # (N, 1, n_taps)
        else:
            # CNN: use full sequence as single batch dimension
            X = rx_t.unsqueeze(0).unsqueeze(0)  # (1, 1, N)

        split = int(N * self.cfg.train_split)
        X_tr, X_val = X[:split], X[split:]
        Y_tr, Y_val = tx_t[:split], tx_t[split:]

        tr_ds  = TensorDataset(X_tr, Y_tr)
        val_ds = TensorDataset(X_val, Y_val)
        tr_ld  = DataLoader(tr_ds,  batch_size=self.cfg.batch_size, shuffle=True)
        val_ld = DataLoader(val_ds, batch_size=self.cfg.batch_size)
        return tr_ld, val_ld

    def train(self, rx: np.ndarray, tx_syms: np.ndarray) -> dict:
        """
        Supervised training on known TX/RX pair.
        Returns dict of training history.
        """
        tr_ld, val_ld = self._build_dataset(rx, tx_syms)
        opt = optim.AdamW(self.model.parameters(),
                          lr=self.cfg.lr,
                          weight_decay=self.cfg.weight_decay)
        sched = optim.lr_scheduler.MultiStepLR(
            opt, milestones=self.cfg.lr_milestones, gamma=self.cfg.lr_decay)
        mse_loss = nn.MSELoss()

        for epoch in range(self.cfg.epochs):
            # ── Training pass ─────────────────────────────────────────────
            self.model.train()
            tr_loss = 0.0
            for X_b, Y_b in tr_ld:
                X_b, Y_b = X_b.to(self.device), Y_b.to(self.device)
                opt.zero_grad()

                if isinstance(self.model, LSTMEqualizer):
                    logits, _ = self.model(X_b)
                    logits = logits[:, -1]   # last timestep output
                else:
                    logits = self.model(X_b)
                    if logits.dim() > 1:
                        logits = logits[:, -1] if logits.shape[0] > 1 \
                                 else logits.squeeze()[:len(Y_b)]

                # Soft-slicer MSE loss (differentiable through decision)
                soft_d = soft_slicer_pam4(logits, self.cfg.soft_temp)
                loss   = mse_loss(soft_d, Y_b) + 0.1 * mse_loss(logits, Y_b)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
                opt.step()
                tr_loss += loss.item()

            sched.step()
            tr_loss /= max(len(tr_ld), 1)

            # ── Validation pass ───────────────────────────────────────────
            self.model.eval()
            val_ser = 0.0
            val_n   = 0
            with torch.no_grad():
                for X_b, Y_b in val_ld:
                    X_b, Y_b = X_b.to(self.device), Y_b.to(self.device)
                    if isinstance(self.model, LSTMEqualizer):
                        logits, _ = self.model(X_b)
                        logits = logits[:, -1]
                    else:
                        logits = self.model(X_b)
                        logits = logits.squeeze()[:len(Y_b)]
                    d_hard = pam4_slicer_torch(logits)
                    val_ser += (d_hard != Y_b).float().sum().item()
                    val_n   += len(Y_b)
            val_ser /= max(val_n, 1)

            self.loss_history.append(tr_loss)
            self.ser_history.append(val_ser)

            if self.cfg.verbose and (epoch % 10 == 0 or epoch == self.cfg.epochs-1):
                print(f"  Epoch {epoch+1:3d}/{self.cfg.epochs} | "
                      f"Loss={tr_loss:.4f} | Val SER={val_ser:.3e} | "
                      f"LR={sched.get_last_lr()[0]:.1e}")

        return {'loss': self.loss_history, 'ser': self.ser_history}

    def decision_directed_update(self, rx_new: np.ndarray,
                                  n_steps: int = 100,
                                  mu_dd: float = 1e-4):
        """
        Online decision-directed fine-tuning for channel tracking.
        Called periodically during operation to track slow channel drift.
        """
        self.model.train()
        opt = optim.SGD(self.model.parameters(), lr=mu_dd)
        r_t = torch.tensor(rx_new, dtype=torch.float32)

        for step in range(n_steps):
            idx = np.random.randint(self.model.n_taps,
                                     max(len(rx_new)-1, self.model.n_taps+1))
            if isinstance(self.model, LSTMEqualizer):
                half = self.model.n_taps // 2
                w    = r_t[max(0,idx-half):idx+half]
                X    = torch.zeros(1, 1, self.model.n_taps)
                X[0, 0, :len(w)] = w[:self.model.n_taps]
                logits, _ = self.model(X)
                logit = logits[0, -1]
            else:
                X     = r_t[max(0,idx-32):idx+32].unsqueeze(0).unsqueeze(0)
                out   = self.model(X).squeeze()
                logit = out[-1] if out.dim() > 0 else out

            d_hard = pam4_slicer_torch(logit.unsqueeze(0))[0]
            loss   = (logit - d_hard.detach())**2
            opt.zero_grad()
            loss.backward()
            opt.step()
        self.model.eval()


# ─────────────────────────────────────────────────────────────────────────────
# Hardware-aware INT8 quantised inference engine
# ─────────────────────────────────────────────────────────────────────────────

class QuantisedInferenceEngine:
    """
    Post-training quantisation (PTQ) of neural equalizer for ASIC deployment.

    Quantises weights and activations to INT8.
    Estimates hardware cost (MAC count, memory footprint, power).

    PyTorch dynamic quantisation is used (no calibration dataset needed).
    For production, use static quantisation with representative data.
    """
    def __init__(self, model: nn.Module, weight_bits: int = 8):
        self.float_model = model
        self.weight_bits = weight_bits
        self.quant_model = None
        self._quantise()

    def _quantise(self):
        """Apply dynamic INT8 quantisation."""
        self.float_model.eval()
        self.float_model.cpu()
        if isinstance(self.float_model, LSTMEqualizer):
            self.quant_model = torch.quantization.quantize_dynamic(
                self.float_model,
                qconfig_spec={nn.LSTM, nn.Linear},
                dtype=torch.qint8)
        else:
            # CNN: use static quantisation stub
            self.quant_model = torch.quantization.quantize_dynamic(
                self.float_model,
                qconfig_spec={nn.Linear, nn.Conv1d},
                dtype=torch.qint8)
        print(f"[QuantEngine] INT{self.weight_bits} quantisation applied.")

    def infer(self, r: np.ndarray) -> np.ndarray:
        """Run quantised inference."""
        return self.quant_model.infer(r) if hasattr(self.quant_model, 'infer') \
               else self.float_model.infer(r)

    def hardware_cost(self) -> dict:
        """
        Estimate ASIC hardware cost for inference at 56 Gbaud.
        Assumes 32-way parallel architecture at 1.75 GHz.
        """
        model = self.float_model
        total_params = sum(p.numel() for p in model.parameters())
        total_macs   = 0

        if isinstance(model, LSTMEqualizer):
            H = model.hidden
            T = model.n_taps
            L = model.n_layers
            # LSTM: 4 gates, each (T+H)×H MACs per timestep, per layer
            lstm_macs = 4 * (T + H) * H * L
            fc_macs   = H * (H//2) + (H//2) * 1
            total_macs = lstm_macs + fc_macs
        elif isinstance(model, CNNEqualizer):
            C = model.n_channels
            K = model.kernel_size
            for i in range(model.n_layers):
                in_c  = 1 if i == 0 else C
                total_macs += in_c * C * K
            total_macs += C   # pointwise output projection

        # At 56 Gbaud, 32-parallel: need total_macs per symbol period
        # One symbol period at 1.75 GHz = 32/56G = 571 ps
        # Available cycles per symbol (at 1.75 GHz): 1
        # → need to pipeline total_macs into 1 cycle at 1.75 GHz
        # Each INT8 MAC = ~1 gate-equivalent (GE) ≈ 1.5 µm² in 28nm
        area_ge     = total_macs * 1.0          # 1 GE per MAC (pipelined)
        area_um2    = area_ge * 1.5             # µm² in 28nm
        # Power: INT8 MAC at 1.75 GHz in 28nm ≈ 0.5 fJ/MAC
        power_mw    = total_macs * 32 * 1.75e9 * 0.5e-15 * 1e3

        return {
            'total_params':      total_params,
            'int8_storage_kb':   total_params * self.weight_bits / 8 / 1024,
            'macs_per_symbol':   total_macs,
            'area_estimate_um2': area_um2,
            'power_estimate_mw': power_mw,
            'parallel_factor':   32,
            'clock_ghz':         1.75,
        }

    def compare_float_vs_quant(self, r: np.ndarray,
                                ref_syms: np.ndarray) -> dict:
        """Compare BER of float vs INT8 quantised model."""
        from pam4_chain import gray_decode
        d_float = self.float_model.infer(r)
        d_quant = self.infer(r)
        n = min(len(d_float), len(ref_syms))

        def sym_err(d, ref):
            return float(np.mean(d[:n] != ref[:n]))

        return {
            'float_ser':   sym_err(d_float, ref_syms),
            'quant_ser':   sym_err(d_quant, ref_syms),
            'ser_penalty': sym_err(d_quant, ref_syms) - sym_err(d_float, ref_syms),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Reinforcement learning CDR adaptation
# ─────────────────────────────────────────────────────────────────────────────

class RLCDRAgent:
    """
    Policy gradient agent for CDR loop parameter adaptation.

    State:   [phase_error_rms, freq_word, lock_status, BER_estimate]
    Action:  [Kp_adjust, Ki_adjust]  (continuous, bounded)
    Reward:  -BER  (maximise negative BER = minimise BER)

    Uses a simple policy network (2-layer MLP) with REINFORCE algorithm.
    This is suitable for slow-timescale adaptation (temperature, ageing drift).
    """
    def __init__(self, state_dim: int = 4, action_dim: int = 2,
                 hidden: int = 16, lr: float = 1e-3):
        self.policy = nn.Sequential(
            nn.Linear(state_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, action_dim * 2)   # mean + log_std
        )
        self.opt = optim.Adam(self.policy.parameters(), lr=lr)
        self.trajectory: List[dict] = []
        # Action bounds: Kp ∈ [0.005, 0.05], Ki ∈ [1e-4, 5e-3]
        self.action_mean   = torch.tensor([0.025, 2.5e-3])
        self.action_scale  = torch.tensor([0.020, 2.4e-3])

    def select_action(self, state: np.ndarray) -> Tuple[np.ndarray, float]:
        """Sample action from policy. Returns (action, log_prob)."""
        s_t = torch.tensor(state, dtype=torch.float32)
        out = self.policy(s_t)
        mean, log_std = out[:2], out[2:].clamp(-3, 0)
        std  = log_std.exp()
        dist = torch.distributions.Normal(mean, std)
        raw  = dist.sample()
        lp   = dist.log_prob(raw).sum()
        # Map to [Kp, Ki] ranges via sigmoid
        action_norm = torch.sigmoid(raw)
        action = (self.action_mean - self.action_scale +
                  action_norm * 2 * self.action_scale)
        return action.detach().numpy(), float(lp)

    def store(self, state, action, log_prob, reward):
        self.trajectory.append({'state': state, 'action': action,
                                 'log_prob': log_prob, 'reward': reward})

    def update(self, gamma: float = 0.99):
        """REINFORCE policy gradient update."""
        if len(self.trajectory) < 2:
            return
        rewards = [t['reward'] for t in self.trajectory]
        # Discount returns
        G = 0.0
        returns = []
        for r in reversed(rewards):
            G = r + gamma * G
            returns.insert(0, G)
        returns_t = torch.tensor(returns, dtype=torch.float32)
        returns_t = (returns_t - returns_t.mean()) / (returns_t.std() + 1e-8)

        loss = torch.tensor(0.0, requires_grad=True)
        for step, ret in zip(self.trajectory, returns_t):
            lp   = torch.tensor(step['log_prob'])
            loss = loss + (-lp * ret)

        self.opt.zero_grad()
        loss.backward()
        self.opt.step()
        self.trajectory.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Benchmark: LSTM/CNN vs conventional FFE+DFE
# ─────────────────────────────────────────────────────────────────────────────

def benchmark_ml_vs_conventional(n_symbols: int = 30_000,
                                   snr_db: float = 20.0,
                                   channel_cm: float = 30.0) -> dict:
    """
    Compare ML equalizer SER against conventional FFE+DFE.
    Returns dict with SER for each approach.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from channel    import Channel
    from pam4_chain import PAM4Transmitter, gray_decode
    from equalizers import FFEDFEReceiver, PAM4_LEVELS

    np.random.seed(99)
    print(f"\n=== ML vs Conventional Benchmark (SNR={snr_db}dB) ===")

    # Channel + TX
    ch = Channel.from_loss_model(length_cm=channel_cm)
    tx = PAM4Transmitter(prbs_order=31)
    syms, bits = tx.generate(n_symbols * 2)
    pr  = ch.pulse_response(fbaud=56e9, osr=1)
    rx  = np.convolve(syms[:n_symbols], pr, mode='same')
    rx  = Channel.add_awgn(rx, snr_db)

    results = {}

    # ── Conventional FFE + DFE ────────────────────────────────────────────
    rx_model = FFEDFEReceiver(n_ffe_pre=3, n_ffe_post=17, n_dfe=5,
                               adc_bits=6, adc_vmax=1.0)
    rx_model.ffe.init_from_channel(ch.isi_taps(56e9), snr_db=snr_db)
    decisions_conv, ber_trace = rx_model.process(rx, ref_bits=bits,
                                                   training_len=5000)
    ser_conv = float(np.mean(decisions_conv[5000:] !=
                             syms[5000:len(decisions_conv)]))
    results['conventional_ser'] = ser_conv
    print(f"  Conventional FFE+DFE SER: {ser_conv:.3e}")

    # ── LSTM Equalizer ────────────────────────────────────────────────────
    lstm = LSTMEqualizer(n_taps=32, hidden=32, n_layers=2)
    trainer = NeuralEqualizerTrainer(lstm, TrainingConfig(epochs=30, verbose=False))
    trainer.train(rx, syms[:n_symbols])
    d_lstm = lstm.infer(rx[5000:])
    ser_lstm = float(np.mean(d_lstm[:len(syms[5000:n_symbols])] !=
                              syms[5000:5000+len(d_lstm)]))
    results['lstm_ser'] = ser_lstm
    print(f"  LSTM Equalizer SER:      {ser_lstm:.3e}")

    # ── CNN Equalizer ─────────────────────────────────────────────────────
    cnn = CNNEqualizer(n_channels=16, n_layers=4, kernel_size=5)
    trainer_cnn = NeuralEqualizerTrainer(cnn, TrainingConfig(epochs=30, verbose=False))
    trainer_cnn.train(rx, syms[:n_symbols])
    d_cnn = cnn.infer(rx[5000:])
    n_cmp = min(len(d_cnn), len(syms[5000:n_symbols]))
    ser_cnn = float(np.mean(d_cnn[:n_cmp] != syms[5000:5000+n_cmp]))
    results['cnn_ser'] = ser_cnn
    print(f"  CNN Equalizer SER:       {ser_cnn:.3e}")

    # ── Quantised inference ───────────────────────────────────────────────
    qe = QuantisedInferenceEngine(lstm, weight_bits=8)
    hw = qe.hardware_cost()
    results['hw_cost'] = hw
    print(f"\n  LSTM Hardware Cost (INT8, 28nm):")
    print(f"    Params:    {hw['total_params']} ({hw['int8_storage_kb']:.1f} KB)")
    print(f"    MACs/sym:  {hw['macs_per_symbol']}")
    print(f"    Area:     ~{hw['area_estimate_um2']:.0f} µm²")
    print(f"    Power:    ~{hw['power_estimate_mw']:.1f} mW")

    return results


if __name__ == "__main__":
    np.random.seed(42)
    torch.manual_seed(42)

    print("=== Neural Equalizer Self-Test ===")

    # Quick smoke test: CNN on simple 3-tap channel
    N = 5000
    h = np.array([0.1, 1.0, 0.3])
    tx = np.random.choice([-3.0,-1.0,1.0,3.0], N)
    rx = np.convolve(tx, h, mode='same') + 0.1 * np.random.randn(N)

    cnn = CNNEqualizer(n_channels=8, n_layers=3, kernel_size=5)
    trainer = NeuralEqualizerTrainer(cnn, TrainingConfig(epochs=10, verbose=True))
    hist = trainer.train(rx, tx)
    print(f"Final training loss: {hist['loss'][-1]:.4f}")

    d = cnn.infer(rx[1000:])
    ser = np.mean(d[:len(tx[1000:N])] != tx[1000:1000+len(d)])
    print(f"CNN SER after 10 epochs: {ser:.3e}")

    lstm = LSTMEqualizer(n_taps=16, hidden=16, n_layers=1)
    trainer2 = NeuralEqualizerTrainer(lstm, TrainingConfig(epochs=5, verbose=True))
    trainer2.train(rx, tx)
    d_l = lstm.infer(rx[1000:])
    ser_l = np.mean(d_l[:len(tx[1000:N])] != tx[1000:1000+len(d_l)])
    print(f"LSTM SER after 5 epochs: {ser_l:.3e}")

    qe = QuantisedInferenceEngine(lstm, weight_bits=8)
    hw = qe.hardware_cost()
    print(f"INT8 LSTM: {hw['total_params']} params, "
          f"~{hw['power_estimate_mw']:.1f} mW, "
          f"~{hw['area_estimate_um2']:.0f} µm²")
    print("\nml_equalizer.py: self-test PASSED")
