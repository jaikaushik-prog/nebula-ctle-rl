"""
regressor.py
------------
Ensemble of fully-connected neural networks predicting (SNDR, SFDR) from
circuit parameters (Sec. III.C). Each base learner is a 4-layer MLP with
hidden sizes [64, 32, 16, 8] (paper Sec. V.B), two output heads (SNDR/SFDR
branches), trained with the regression focal loss (Eq. 1):

    L_focal = (1/N) * sum_i (1 - exp(-||R_i(a)-y||^2))^gamma * ||R_i(a)-y||^2

with gamma = 2. Uses PyTorch (paper used TensorFlow; architecture and loss
are identical, framework choice does not change results).
"""

from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.metrics import r2_score
from typing import List, Tuple


class BaseRegressor(nn.Module):
    """One ensemble member: 4-layer MLP [64,32,16,8] -> 2 outputs (SNDR, SFDR)."""

    def __init__(self, in_dim: int, activation: str = "relu", dropout: float = 0.1):
        super().__init__()
        act = {"relu": nn.ReLU, "tanh": nn.Tanh, "gelu": nn.GELU, "elu": nn.ELU}[activation]
        dims = [in_dim, 64, 32, 16, 8]
        layers = []
        for i in range(len(dims) - 1):
            layers += [nn.Linear(dims[i], dims[i + 1]), act(), nn.Dropout(dropout)]
        self.trunk = nn.Sequential(*layers)
        self.head = nn.Linear(dims[-1], 2)  # [SNDR, SFDR]
        # keep a handle to the FIRST layer for component-importance (Eq. 5-6)
        self.first_layer = layers[0]

    def forward(self, x):
        return self.head(self.trunk(x))


def focal_loss(pred: torch.Tensor, target: torch.Tensor, gamma: float = 2.0) -> torch.Tensor:
    """Regression focal loss, Eq. 1. pred/target: (N, 2) = [SNDR, SFDR]."""
    sq_err = (pred - target).pow(2).sum(dim=-1)  # ||R_i(a) - y||^2, summed over the 2 targets
    weight = (1 - torch.exp(-sq_err)).pow(gamma)
    return (weight * sq_err).mean()


class EnsembleRegressor:
    """Ensemble of M BaseRegressors, as in Sec. III.C / V.B ("ensemble means
    are averaged for robustness")."""

    def __init__(self, in_dim: int, n_models: int = 5, lr: float = 1e-3,
                 device: str = "cpu", seed: int = 0):
        torch.manual_seed(seed)
        activations = ["relu", "tanh", "gelu", "elu", "relu"]
        self.models: List[BaseRegressor] = [
            BaseRegressor(in_dim, activation=activations[i % len(activations)])
            for i in range(n_models)
        ]
        self.device = device
        for m in self.models:
            m.to(device)
        self.opts = [torch.optim.Adam(m.parameters(), lr=lr) for m in self.models]
        # normalization stats, fit on training data
        self.x_mean = np.zeros(in_dim)
        self.x_std = np.ones(in_dim)
        self.y_mean = np.zeros(2)
        self.y_std = np.ones(2)

    def _fit_norm(self, X: np.ndarray, y: np.ndarray):
        self.x_mean, self.x_std = X.mean(0), X.std(0) + 1e-8
        self.y_mean, self.y_std = y.mean(0), y.std(0) + 1e-8

    def _norm_x(self, X): return (X - self.x_mean) / self.x_std
    def _norm_y(self, y): return (y - self.y_mean) / self.y_std
    def _denorm_y(self, y): return y * self.y_std + self.y_mean

    def fit(self, X: np.ndarray, y: np.ndarray, epochs: int = 60, batch_size: int = 64,
            val_split: float = 0.15, bootstrap: bool = True, verbose: bool = False):
        n = len(X)
        n_val = max(1, int(n * val_split))
        perm = np.random.default_rng(0).permutation(n)
        val_idx, train_idx = perm[:n_val], perm[n_val:]
        self._fit_norm(X[train_idx], y[train_idx])
        Xtr, ytr = self._norm_x(X[train_idx]), self._norm_y(y[train_idx])
        Xval, yval = self._norm_x(X[val_idx]), self._norm_y(y[val_idx])
        Xval_t = torch.tensor(Xval, dtype=torch.float32, device=self.device)
        yval_t = torch.tensor(yval, dtype=torch.float32, device=self.device)

        history = []
        for m_i, (model, opt) in enumerate(zip(self.models, self.opts)):
            idx = np.arange(len(Xtr))
            if bootstrap:
                idx = np.random.default_rng(m_i).choice(len(Xtr), len(Xtr), replace=True)
            ds = TensorDataset(
                torch.tensor(Xtr[idx], dtype=torch.float32),
                torch.tensor(ytr[idx], dtype=torch.float32),
            )
            dl = DataLoader(ds, batch_size=batch_size, shuffle=True)
            for ep in range(epochs):
                model.train()
                for xb, yb in dl:
                    xb, yb = xb.to(self.device), yb.to(self.device)
                    opt.zero_grad()
                    pred = model(xb)
                    loss = focal_loss(pred, yb, gamma=2.0)
                    loss.backward()
                    opt.step()
            model.eval()
            with torch.no_grad():
                val_pred = model(Xval_t)
                val_loss = focal_loss(val_pred, yval_t).item()
            history.append(val_loss)
            if verbose:
                print(f"  member {m_i} ({model.trunk[1].__class__.__name__}): val focal loss={val_loss:.4f}")

        r2 = self.r_squared(X[val_idx], y[val_idx])
        return {"val_focal_loss_per_member": history, "val_r2": r2}

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Returns ensemble-mean (N,2) = [SNDR_hat, SFDR_hat] in physical units (dB)."""
        Xn = self._norm_x(X)
        Xt = torch.tensor(Xn, dtype=torch.float32, device=self.device)
        preds = []
        with torch.no_grad():
            for m in self.models:
                m.eval()
                preds.append(m(Xt).cpu().numpy())
        mean_pred_n = np.mean(preds, axis=0)
        return self._denorm_y(mean_pred_n)

    def predict_with_std(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        Xn = self._norm_x(X)
        Xt = torch.tensor(Xn, dtype=torch.float32, device=self.device)
        preds = []
        with torch.no_grad():
            for m in self.models:
                m.eval()
                preds.append(m(Xt).cpu().numpy())
        preds = np.stack(preds, axis=0)  # (M, N, 2)
        mean_n = preds.mean(0)
        std_n = preds.std(0) * self.y_std  # approx de-normalized std
        return self._denorm_y(mean_n), std_n

    def r_squared(self, X: np.ndarray, y: np.ndarray) -> dict:
        pred = self.predict(X)
        return {
            "SNDR": r2_score(y[:, 0], pred[:, 0]),
            "SFDR": r2_score(y[:, 1], pred[:, 1]),
            "overall": r2_score(y.ravel(), pred.ravel()),
        }

    def partial_fit(self, X_new: np.ndarray, y_new: np.ndarray, epochs: int = 10,
                     batch_size: int = 32):
        """Incremental retraining used in Online/Blend modes (Sec. III.E):
        'regressors are incrementally retrained using new SPICE data'."""
        Xn = self._norm_x(X_new)
        yn = self._norm_y(y_new)
        Xt = torch.tensor(Xn, dtype=torch.float32, device=self.device)
        yt = torch.tensor(yn, dtype=torch.float32, device=self.device)
        for model, opt in zip(self.models, self.opts):
            model.train()
            ds = TensorDataset(Xt, yt)
            dl = DataLoader(ds, batch_size=min(batch_size, len(Xt)), shuffle=True)
            for _ in range(epochs):
                for xb, yb in dl:
                    opt.zero_grad()
                    loss = focal_loss(model(xb), yb, gamma=2.0)
                    loss.backward()
                    opt.step()
            model.eval()

    def first_layer_weights(self) -> List[np.ndarray]:
        """|W^(m)| for the first Linear layer of each ensemble member, used by
        component_importance.py to reproduce Eq. 5-6."""
        return [m.first_layer.weight.detach().cpu().numpy() for m in self.models]


if __name__ == "__main__":
    # tiny smoke test
    from circuits import denormalize
    from simulator import SyntheticSpiceEnv
    rng = np.random.default_rng(0)
    env = SyntheticSpiceEnv("buffer_switch", seed=0)
    A = rng.uniform(0, 1, size=(200, 38))
    X = np.array([denormalize(a, "buffer_switch") for a in A])
    y = np.array([env.evaluate(x)[:2] for x in X])
    ens = EnsembleRegressor(in_dim=38, n_models=3)
    stats = ens.fit(X, y, epochs=15, verbose=True)
    print("val R2:", stats["val_r2"])
