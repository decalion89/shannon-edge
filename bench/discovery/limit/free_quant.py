#!/usr/bin/env python3
"""Exploiting the freedom of a max-error guarantee: any reproduction within +-delta is valid, so the encoder
may choose the cheapest one. Quantisers compared (all guarantee |x - y| <= delta on every sample):
  lattice   y = centre of the cell of width 2 delta (the current protocol)
  hold(m)   fine grid of step 2 delta / m; keep the previous y if still admissible, else move to the
            admissible grid point closest to the previous y (send-on-delta on a grid)
Indices are coded by the flight profile (real bytes).
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from esa_edge_link import flight  # noqa: E402


def lattice(x, delta):
    k = np.round((x - x[0]) / (2 * delta)).astype(np.int64)
    return k - k.min(), x[0] + 2 * delta * k


def hold(x, delta, m):
    step = 2 * delta / m
    g = np.round((x - x[0]) / step).astype(np.int64)  # nearest fine-grid point to x
    r = m // 2  # admissible grid offsets: |x - (x0 + j step)| <= delta  <=>  j in [g - r', g + r'] (conservative)
    out = np.empty_like(g)
    cur = g[0]
    for t in range(len(x)):
        lo, hi = g[t] - r, g[t] + r
        # exact admissibility check on the boundaries
        while abs(x[t] - (x[0] + lo * step)) > delta + 1e-12:
            lo += 1
        while abs(x[t] - (x[0] + hi * step)) > delta + 1e-12:
            hi -= 1
        if cur < lo:
            cur = lo
        elif cur > hi:
            cur = hi
        out[t] = cur
    y = x[0] + out * step
    return out - out.min(), y


def bits_per_sample(idx):
    if idx.max() >= 65536:
        return float("nan")
    return 8 * flight(idx.astype("<u2"))[0] / len(idx)


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    n = 200000
    for name, x in (("white Gaussian noise", rng.normal(0, 1, n)),
                    ("random walk + noise", np.cumsum(rng.normal(0, 0.3, n)) + rng.normal(0, 1, n))):
        delta = 1.0
        li, y = lattice(x, delta)
        assert np.max(np.abs(x - y)) <= delta + 1e-9
        print(f"{name}: lattice {bits_per_sample(li):.3f} bit/sample", flush=True)
        for m in (2, 4, 8, 16):
            hi, yh = hold(x, delta, m)
            assert np.max(np.abs(x - yh)) <= delta + 1e-9
            print(f"   hold(m={m}) {bits_per_sample(hi):.3f} bit/sample", flush=True)
    print("theoretical limit for white Gaussian noise at delta = sigma: 1.047 bit/sample")
