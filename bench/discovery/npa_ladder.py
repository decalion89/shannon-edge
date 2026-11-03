#!/usr/bin/env python3
"""The NPA ladder for zero-error equality certification: maximum certification rate s at NPA level 2
(all words of length <= 2: 1, A_x, B_y, A_x A_z, B_y B_w, A_x B_y), symmetrised over relabelling the
settings, for binary-outcome certificate boxes (p(0,0|x,y) = 0 for x != y, p(0,0|x,x) = s).
Level 1 -> 1/8 and level 1+AB -> 1/17 are known (arXiv:2610.41448); quantum is 1/N.
Usage: npa_ladder.py N [N ...]
"""
import sys
import time

import cvxpy as cp
import numpy as np
import scipy.sparse as sp

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from aq_cert_max import canon  # noqa: E402


def solve(N):
    A = [(("A", x),) for x in range(N)]
    B = [(("B", y),) for y in range(N)]
    ops = [()] + A + B
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
    K = len(keys)
    M = sp.csr_matrix((np.ones(len(dr)), (dr, dc)), shape=(n * n, K))
    m = cp.Variable(K)
    G = cp.reshape(M @ m, (n, n), order="C")
    g = lambda w: m[keys[canon(w)]]  # noqa: E731
    cons = [G >> 0, g(()) == 1, g((("A", 0), ("B", 1))) == 0]
    p = cp.Problem(cp.Maximize(g((("A", 0), ("B", 0)))), cons)
    p.solve(solver="SCS", eps=1e-7, max_iters=300000)
    return p.value, p.status, K, n


if __name__ == "__main__":
    for N in [int(x) for x in sys.argv[1:]]:
        t = time.time()
        s, st, K, n = solve(N)
        aq = N * N / (17 * N * N - 80 * N + 64) if N >= 8 else 1 / N
        print(f"N={N}: level-2 max s = {s:.7f} (1/s = {1 / s:.4f}); N*s = {N * s:.5f}; AQ (1+AB) {aq:.7f}; "
              f"quantum {1 / N:.5f}; {st}; {K} classes, {n}x{n}; {time.time() - t:.0f}s", flush=True)
