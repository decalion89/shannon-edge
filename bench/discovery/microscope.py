#!/usr/bin/env python3
"""Compression-gap microscope, phase 1: positive and negative controls on synthetic data.

Question: can an instrument with no prior knowledge (1) detect that one channel carries information
about another, (2) find the lag, (3) find the regime where the coupling acts, and (4) write the law
as an equation, while (5) finding nothing in a control where no law exists?

Method:
* The gap is the code length of y_t under an adaptive context model that knows y's own past,
  minus the code length under one that also knows x_{t-lag}, in bits per sample (Krichevsky-Trofimov
  counts, online, no training). Summed, it estimates the conditional mutual information
  I(y_t; x_{t-lag} | y_{t-1}), i.e. transfer entropy (Schreiber 2000). The concept is not new; what
  is tested is whether the instrument localises and writes the law unaided.
* (1)-(2): scan lags 0..MAXLAG; the gap is compared with a time-shifted surrogate of x, which
  destroys any lagged relation (null distribution, 20 random circular shifts).
* (3): the gap per bin of x_{t-lag} shows where the coupling acts: by MDL, where knowing x pays for
  its own learning cost (net gain > 0 bits). The richer model's learning cost makes the mean gap
  negative overall; the comparison with the null, not the sign, decides (1)-(2).
* (4): in the regime found, sparse regression (sequentially thresholded least squares, as in SINDy)
  over a fixed library [1, y_{t-1}, x_{t-lag}, x_{t-lag}^2, x_{t-lag}^3] writes the law.

Usage: microscope.py [--seed 0]
"""

import argparse

import numpy as np

QY, QX, MAXLAG, N = 32, 8, 20, 60000


def quant(v, q, lo, hi):
    return np.clip(((v - lo) / (hi - lo) * q).astype(int), 0, q - 1)


def code_lengths(y, ctx, ny, nctx):
    """Online KT code length of each y_t given its context id ctx_t (ints)."""
    counts = np.zeros((nctx, ny))
    tot = np.zeros(nctx)
    out = np.empty(len(y))
    for t in range(len(y)):
        c, s = ctx[t], y[t]
        out[t] = -np.log2((counts[c, s] + 0.5) / (tot[c] + 0.5 * ny))
        counts[c, s] += 1
        tot[c] += 1
    return out


def gap(yq, xq, lag):
    y = yq[MAXLAG:]
    yp = yq[MAXLAG - 1:-1]
    xl = xq[MAXLAG - lag:len(xq) - lag]
    c0 = code_lengths(y, yp, QY, QY)
    c1 = code_lengths(y, yp * QX + xl, QY, QY * QX)
    return c0 - c1, xl


def make(seed, law):
    rng = np.random.default_rng(seed)
    x = np.zeros(N)
    y = np.zeros(N)
    e = rng.normal(0, 1, N)
    for t in range(1, N):
        x[t] = 0.95 * x[t - 1] + rng.normal(0, 0.3)
    for t in range(1, N):
        y[t] = 0.6 * y[t - 1] + 0.4 * e[t]
        # The hidden law: y responds to x seven samples earlier, only when that x is above 0.5.
        if law and t >= 7 and x[t - 7] > 0.5:
            y[t] += 0.5 * (x[t - 7] - 0.5)
    return x, y


def stls(X, yv, thr=0.05, it=10):
    w = np.linalg.lstsq(X, yv, rcond=None)[0]
    for _ in range(it):
        small = np.abs(w) < thr
        w[small] = 0
        big = ~small
        if big.any():
            w[big] = np.linalg.lstsq(X[:, big], yv, rcond=None)[0]
    return w


def run(seed, law):
    x, y = make(seed, law)
    xq = quant(x, QX, np.quantile(x, 0.01), np.quantile(x, 0.99))
    yq = quant(y, QY, np.quantile(y, 0.01), np.quantile(y, 0.99))
    gains = np.array([gap(yq, xq, L)[0].mean() for L in range(MAXLAG + 1)])
    rng = np.random.default_rng(seed + 1000)
    null = []
    for _ in range(20):
        xs = np.roll(xq, rng.integers(N // 10, N - N // 10))
        null.append(max(gap(yq, xs, L)[0].mean() for L in range(0, MAXLAG + 1, 4)))
    best = int(np.argmax(gains))
    found = gains[best] > max(null)
    print(f"{'law present' if law else 'NO law (negative control)'}: best lag {best}, gain {gains[best]*1000:.2f} "
          f"mbit/sample; null max over 20 shifts {max(null)*1000:.2f} -> {'FOUND' if found else 'nothing found'}")
    print("   gain by lag (mbit/sample):", " ".join(f"{L}:{g*1000:.1f}" for L, g in enumerate(gains)))
    if not found:
        return
    g, xl = gap(yq, xq, best)
    per_bin = [g[xl == b].mean() if (xl == b).any() else np.nan for b in range(QX)]
    edges = np.quantile(x, 0.01) + (np.quantile(x, 0.99) - np.quantile(x, 0.01)) * np.arange(QX + 1) / QX
    print("   gain by bin of x_{t-lag} (mbit/sample):",
          " ".join(f"[{edges[b]:.2f},{edges[b+1]:.2f}):{v*1000:.1f}" for b, v in enumerate(per_bin)))
    # MDL rule: the coupling is "active" where knowing x pays for its own learning cost (net gain > 0).
    active = [b for b, v in enumerate(per_bin) if v > 0]
    lo_edge = edges[min(active)] if active else -np.inf
    xs_ = x[MAXLAG - best:len(x) - best]
    ys_ = y[MAXLAG:]
    yp_ = y[MAXLAG - 1:-1]
    m = xs_ >= lo_edge
    X = np.column_stack([np.ones(m.sum()), yp_[m], xs_[m], xs_[m] ** 2, xs_[m] ** 3])
    w = stls(X, ys_[m])
    names = ["1", "y[t-1]", f"x[t-{best}]", f"x[t-{best}]^2", f"x[t-{best}]^3"]
    law_txt = " + ".join(f"{c:.3f}*{nm}" for c, nm in zip(w, names) if c != 0)
    print(f"   regime found: x[t-{best}] >= {lo_edge:.2f};  law written: y[t] = {law_txt}")
    print("   truth:        x[t-7] > 0.50;            y[t] = 0.6*y[t-1] + 0.5*x[t-7] - 0.25 (+ noise)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    run(a.seed, True)
    run(a.seed, False)


if __name__ == "__main__":
    main()
