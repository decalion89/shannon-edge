#!/usr/bin/env python3
"""Noise-robust version of the exact-zero quantum witness (exploration).

arXiv:2610.41448 shows that every commuting-operator box with p(0,0|x,y) = 0 for x != y satisfies
sum_x p(0,0|x,x) <= 1, while almost-quantum boxes reach ~N/17. Exact zeros cannot be verified in a lab.
Here the off-diagonal entries are allowed to be eps (symmetric boxes), and we compute an upper bound on
the quantum value of S = sum_x p(0,0|x,x) from NPA level 2 (which contains every quantum box), next to
the almost-quantum (1+AB) value. The quantum curve S_Q(eps) gives a witness usable with real data:
a symmetric box with off-diagonal eps and S above the level-2 curve is not quantum.
Usage: npa_robust.py N eps [eps ...]
"""
import sys
import time

import cvxpy as cp
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from aq_cert_max import canon  # noqa: E402


def solve(N, eps, level2=True):
    A = [(("A", x),) for x in range(N)]
    B = [(("B", y),) for y in range(N)]
    ops = [()] + A + B
    if level2:
        ops += [(("A", x), ("A", z)) for x in range(N) for z in range(N) if x != z]
        ops += [(("B", y), ("B", w)) for y in range(N) for w in range(N) if y != w]
    ops += [(("A", x), ("B", y)) for x in range(N) for y in range(N)]
    n = len(ops)
    keys, dr, dc = {}, [], []
    for r in range(n):
        for c in range(r, n):
            k = canon(tuple(reversed(ops[r])) + ops[c])
            keys.setdefault(k, len(keys))
            dr.append(r * n + c); dc.append(keys[k])
            if r != c:
                dr.append(c * n + r); dc.append(keys[k])
    M = sp.csr_matrix((np.ones(len(dr)), (dr, dc)), shape=(n * n, len(keys)))
    m = cp.Variable(len(keys))
    G = cp.reshape(M @ m, (n, n), order="C")
    g = lambda w: m[keys[canon(w)]]  # noqa: E731
    cons = [G >> 0, g(()) == 1, g((("A", 0), ("B", 1))) == eps]
    p = cp.Problem(cp.Maximize(N * g((("A", 0), ("B", 0)))), cons)
    p.solve(solver="SCS", eps=1e-7, max_iters=300000)
    return p.value, p.status


if __name__ == "__main__":
    N = int(sys.argv[1])
    for eps in [float(e) for e in sys.argv[2:]]:
        t = time.time()
        q, st = solve(N, eps, True)
        aq, st2 = solve(N, eps, False)
        print(f"N={N} eps={eps:g}: S <= {q:.5f} (level 2, bounds quantum) | AQ max {aq:.5f} | "
              f"slope (S_L2 - 1)/(N(N-1)eps) = {(q - 1) / (N * (N - 1) * eps) if eps else float('nan'):.4f} | "
              f"{st}/{st2} {time.time() - t:.0f}s", flush=True)
