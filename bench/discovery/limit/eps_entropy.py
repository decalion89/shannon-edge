#!/usr/bin/env python3
"""Exact epsilon-entropy (per-sample max-error guarantee) of an i.i.d. source, by Blahut-Arimoto with a
hard constraint: minimise I(X;Y) over Q(y|x) supported on |x - y| <= delta. Iteration:
Q(y|x) = q(y) 1{|x-y|<=delta} / Z(x),  q(y) = sum_x p(x) Q(y|x). Returns I in bits.
Compared with the Shannon lower bound h(X) - log2(2 delta) and with the uniform lattice of step 2 delta.
"""
import numpy as np


def eps_entropy(px, x, y, delta, iters=4000, tol=1e-12):
    A = (np.abs(x[:, None] - y[None, :]) <= delta + 1e-12).astype(float)
    q = np.full(len(y), 1.0 / len(y))
    for _ in range(iters):
        W = A * q[None, :]
        Z = W.sum(1, keepdims=True)
        Q = W / Z
        qn = px @ Q
        if np.max(np.abs(qn - q)) < tol:
            q = qn
            break
        q = qn
    W = A * q[None, :]
    Q = W / W.sum(1, keepdims=True)
    py = px @ Q
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(Q > 0, Q * np.log2(Q / py[None, :]), 0.0)
    return float(px @ t.sum(1))


def lattice_entropy(pdf, delta, lim=12.0, step=1e-4):
    """Entropy (bits) of the uniform lattice of step 2*delta, best offset over a few phases."""
    best = np.inf
    for ph in np.linspace(0, 2 * delta, 9)[:-1]:
        edges = np.arange(-lim - ph, lim + 2 * delta, 2 * delta)
        P = []
        for a, b in zip(edges[:-1], edges[1:]):
            t = np.arange(a, b, step)
            P.append(pdf(t).sum() * step)
        P = np.array(P)
        P = P[P > 0] / P.sum()
        best = min(best, float(-(P * np.log2(P)).sum()))
    return best


if __name__ == "__main__":
    gauss = lambda t: np.exp(-t * t / 2) / np.sqrt(2 * np.pi)  # noqa: E731
    lap = lambda t: np.exp(-np.abs(t) * np.sqrt(2)) / np.sqrt(2)  # unit variance Laplace  # noqa: E731
    for name, pdf, h in (("Gaussian", gauss, 0.5 * np.log2(2 * np.pi * np.e)),
                         ("Laplace", lap, np.log2(2 * np.e / np.sqrt(2)))):
        for delta in (0.5, 1.0, 2.0):
            dx = 0.01
            x = np.arange(-9, 9 + dx, dx)
            px = pdf(x) * dx
            px /= px.sum()
            y = np.arange(-9 - delta, 9 + delta + dx, dx)
            R = eps_entropy(px, x, y, delta)
            slb = max(0.0, h - np.log2(2 * delta))
            L = lattice_entropy(pdf, delta)
            print(f"{name:8s} delta = {delta:.1f} sigma: Shannon lower bound {slb:.3f} | exact eps-entropy {R:.3f} | "
                  f"uniform lattice {L:.3f} bits/sample (lattice excess {L - R:+.3f})", flush=True)
