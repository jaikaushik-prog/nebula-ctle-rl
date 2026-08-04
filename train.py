"""
discriminator.py
-----------------
Discriminator-based critic (Sec. III.F) that separates real (SPICE-verified)
parameter vectors from policy-generated ("fake") ones via a standard BCE
GAN-style objective (Eq. 3):

    L_disc = -E_{x~D_real}[log D(x)] - E_{x~D_fake}[log(1 - D(x))]

Its output is folded into the reward as a penalty on confidence away from
the decision boundary 0.5 (Eq. 4):

    R_dis = -lambda * (D(a) - 0.5)^2

which discourages the policy from drifting either strongly in- or
out-of-distribution relative to the discriminator's current boundary,
matching the paper's framing ("penalizing confidence away from 0.5").
"""

from __future__ import annotations
import numpy as np
import torch
import torch.nn as nn


class Discriminator(nn.Module):
    def __init__(self, in_dim: int, hidden=(64, 32)):
        super().__init__()
        dims = [in_dim, *hidden]
        layers = []
        for i in range(len(dims) - 1):
            layers += [nn.Linear(dims[i], dims[i + 1]), nn.LeakyReLU(0.1)]
        layers += [nn.Linear(dims[-1], 1), nn.Sigmoid()]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(-1)


class DiscriminatorTrainer:
    def __init__(self, in_dim: int, lr: float = 1e-3, device: str = "cpu", seed: int = 0):
        torch.manual_seed(seed)
        self.device = device
        self.model = Discriminator(in_dim).to(device)
        self.opt = torch.optim.Adam(self.model.parameters(), lr=lr)
        self.x_mean = np.zeros(in_dim)
        self.x_std = np.ones(in_dim)

    def set_norm(self, X_real: np.ndarray):
        self.x_mean = X_real.mean(0)
        self.x_std = X_real.std(0) + 1e-8

    def _norm(self, X):
        return (X - self.x_mean) / self.x_std

    def train_step(self, X_real: np.ndarray, X_fake: np.ndarray) -> float:
        """One BCE update given a batch of real (SPICE) and fake (policy) params.
        Batch size follows the paper's convention: discriminator trained every
        K steps with batch size 2K (Sec. V.B)."""
        self.model.train()
        Xr = torch.tensor(self._norm(X_real), dtype=torch.float32, device=self.device)
        Xf = torch.tensor(self._norm(X_fake), dtype=torch.float32, device=self.device)
        self.opt.zero_grad()
        d_real = self.model(Xr).clamp(1e-6, 1 - 1e-6)
        d_fake = self.model(Xf).clamp(1e-6, 1 - 1e-6)
        loss = -(torch.log(d_real).mean() + torch.log(1 - d_fake).mean())
        loss.backward()
        self.opt.step()
        return loss.item()

    def score(self, X: np.ndarray) -> np.ndarray:
        """D(x) in [0,1]; used by reward.py to compute R_dis (Eq. 4)."""
        self.model.eval()
        Xt = torch.tensor(self._norm(X), dtype=torch.float32, device=self.device)
        with torch.no_grad():
            return self.model(Xt).cpu().numpy()


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    disc = DiscriminatorTrainer(in_dim=10)
    real = rng.normal(0, 1, size=(64, 10))
    disc.set_norm(real)
    fake = rng.normal(3, 1, size=(64, 10))  # shifted -> should be "OOD"
    for _ in range(200):
        loss = disc.train_step(real, fake)
    print("final disc loss:", loss)
    print("D(real) mean:", disc.score(real).mean(), " D(fake) mean:", disc.score(fake).mean())
