#!/usr/bin/env python3
"""General form of the coincidence inequality: for any list of K pairs (outcome a_k of setting x_k for
Alice, outcome b_k of setting y_k for Bob), with repetition allowed,

    ( sum_k p(a_k b_k | x_k y_k) )^2  <=  sum_{k,l} p(a_k b_l | x_k y_l).

Proof: as in welch_witness.md with A_k = effect (a_k|x_k), B_k = effect (b_k|y_k) (repeats allowed).
Random check on quantum strategies with 3-outcome measurements and random pair lists.
"""
import numpy as np

rng = np.random.default_rng(11)


def povm(d, n):  # random rank-structured projective measurement with n outcomes
    U, _ = np.linalg.qr(rng.normal(size=(d, d)) + 1j * rng.normal(size=(d, d)))
    lab = rng.integers(0, n, size=d)
    return [U[:, lab == o] @ U[:, lab == o].conj().T for o in range(n)]


worst = -np.inf
for trial in range(3000):
    X, n, dA, dB = rng.integers(2, 5), 3, rng.integers(2, 5), rng.integers(2, 5)
    MA = [povm(dA, n) for _ in range(X)]
    MB = [povm(dB, n) for _ in range(X)]
    psi = rng.normal(size=dA * dB) + 1j * rng.normal(size=dA * dB)
    psi /= np.linalg.norm(psi)
    K = rng.integers(1, 9)
    pairs = [(rng.integers(X), rng.integers(n), rng.integers(X), rng.integers(n)) for _ in range(K)]
    p = lambda k, l: np.real(psi.conj() @ np.kron(MA[pairs[k][0]][pairs[k][1]], MB[pairs[l][2]][pairs[l][3]]) @ psi)  # noqa
    S = sum(p(k, k) for k in range(K))
    T = sum(p(k, l) for k in range(K) for l in range(K))
    worst = max(worst, S * S - T)
print(f"max over 3000 random quantum strategies / pair lists of S^2 - T = {worst:.2e}")
