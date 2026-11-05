#!/usr/bin/env python3
"""Rigorous certificate for a given N: an explicit rational NPA-1+AB moment assignment for the adaptive
one-bit protocol (aq_adaptive.py) with exact zero-error constraints, worst-case success >= q0, and a
moment matrix whose smallest eigenvalue exceeds a margin that dominates floating-point error.

Method: maximise the smallest eigenvalue lambda of G subject to q >= q0, r >= q0 and the exact
equalities; round every free moment class to a rational with denominator 10^9 (keeping the zero-error
classes exactly 0 / exactly equal); recompute G and its smallest eigenvalue. Rounding changes each entry
by <= 5e-10, so the eigenvalue moves by at most n * 5e-10 (Weyl); if lambda_min > that bound plus
float64 eigen-solver error (~ n * 1e-15 * ||G||), G is PSD exactly.

Usage: aq_adaptive_cert.py N q0
"""
import sys
from fractions import Fraction

import cvxpy as cp
import numpy as np
import scipy.sparse as sps

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import aq_adaptive as A  # noqa: E402


def main():
    N, q0 = int(sys.argv[1]), float(sys.argv[2])
    Aop = [(("A", x),) for x in range(N)]
    Bop = [(("B", y, c),) for y in range(N) for c in (0, 1)]
    ops = [()] + Aop + Bop + [a + b for a in Aop for b in Bop]
    n = len(ops)
    keys, cls = {}, np.empty((n, n), dtype=np.int64)
    for r in range(n):
        for c in range(r, n):
            k = A.canon(tuple(reversed(ops[r])) + ops[c])
            if k not in keys:
                keys[k] = len(keys)
            cls[r, c] = cls[c, r] = keys[k]
    K = len(keys)
    rows, cols = np.nonzero(np.ones((n, n)))
    Mmap = sps.csr_matrix((np.ones(n * n), (np.arange(n * n), cls.ravel())), shape=(n * n, K))
    m = cp.Variable(K)
    G = cp.reshape(Mmap @ m, (n, n), order="C")
    g = lambda w: keys[A.canon(w)]  # noqa: E731
    one, q = g(()), g((("A", 0), ("B", 0, 0)))
    zero_eq, b1 = g((("A", 0), ("B", 1, 0))), g((("B", 0, 1),))
    ab1s, ab1d = g((("A", 0), ("B", 0, 1))), g((("A", 0), ("B", 1, 1)))
    lam = cp.Variable()
    cons = [G - lam * np.eye(n) >> 0, m[one] == 1, m[zero_eq] == 0, m[b1] == m[ab1s],
            m[q] >= q0, m[b1] - m[ab1d] >= q0]
    cp.Problem(cp.Maximize(lam), cons).solve(solver="SCS", eps=1e-9, max_iters=500000)
    mv = [Fraction(round(float(v) * 10**9), 10**9) for v in m.value]
    mv[one], mv[zero_eq] = Fraction(1), Fraction(0)
    mv[ab1s] = mv[b1]
    worst = min(mv[q], mv[b1] - mv[ab1d])
    Gr = np.array([[float(mv[cls[r, c]]) for c in range(n)] for r in range(n)])
    lmin = np.linalg.eigvalsh(Gr).min()
    bound = n * 5e-10 + n * 1e-15 * np.abs(Gr).sum(1).max()
    print(f"N={N}: rational moments, exact zero-error constraints; worst-case success = {float(worst):.9f} "
          f"(exact {worst}); min eigenvalue {lmin:.3e} vs rounding/solver bound {bound:.3e} -> "
          f"{'CERTIFIED PSD' if lmin > bound else 'not certified'}")
    lb = N * N / (19 * N * N - 80 * N + 64)
    print(f"  published one-bit lower bound {lb:.6f}; quantum optimum {1 / N:.6f}")


if __name__ == "__main__":
    main()
