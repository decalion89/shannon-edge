#!/usr/bin/env python3
"""Largest certification rate s allowed at the NPA "1+AB" level (the almost-quantum set) for certificate
boxes with N settings: maximise s subject to p(0,0|x,y) = 0 for x != y and p(0,0|x,x) = s for all x
(binary outcomes, moments of the outcome-0 projectors). The SDP is symmetrised over relabellings of the
settings: every moment depends only on the pattern of its indices, which is without loss of generality
because the problem is invariant under simultaneous permutations of the settings and averaging a feasible
point over the group keeps it feasible.

Context: Das Bhowmik & Banik (arXiv:2610.41444) violate information causality with an AQ box of rate
s = 1/17 for every N, needing N >= 757,692 settings. A larger AQ rate would make the violation cheaper.

Usage: aq_cert_max.py N [N ...]
"""

import sys
import time

import cvxpy as cp
import numpy as np
import scipy.sparse as sp


def reduce_word(word):
    a = [l for l in word if l[0] == "A"]
    b = [l for l in word if l[0] == "B"]

    def merge(seq):
        out = []
        for l in seq:
            if not out or out[-1] != l:
                out.append(l)
        return out

    return merge(a), merge(b)


def pattern(a, b):
    """Relabel setting indices by order of first appearance (A part then B part): invariance under S_N."""
    lab = {}
    out = []
    for p, x in a + b:
        if x not in lab:
            lab[x] = len(lab)
        out.append((p, lab[x]))
    return tuple(out[:len(a)]), tuple(out[len(a):])


def canon(word):
    a, b = reduce_word(word)
    k1 = pattern(a, b)
    k2 = pattern(a[::-1], b[::-1])
    return min(k1, k2)


def solve(N, verbose=False):
    ops = [()] + [(("A", x),) for x in range(N)] + [(("B", y),) for y in range(N)]
    ops += [(("A", x), ("B", y)) for x in range(N) for y in range(N)]
    n = len(ops)
    keys, rows, cols, var = {}, [], [], []
    for r in range(n):
        for c in range(r, n):
            k = canon(tuple(reversed(ops[r])) + ops[c])
            if k not in keys:
                keys[k] = len(keys)
            rows.append(r)
            cols.append(c)
            var.append(keys[k])
    K = len(keys)
    m = cp.Variable(K)
    # G = sum_k m_k * E_k  (symmetric), built as a sparse linear map from m to vec(G)
    data_r, data_c = [], []
    for (r, c, v) in zip(rows, cols, var):
        data_r.append(r * n + c)
        data_c.append(v)
        if r != c:
            data_r.append(c * n + r)
            data_c.append(v)
    Mmap = sp.csr_matrix((np.ones(len(data_r)), (data_r, data_c)), shape=(n * n, K))
    G = cp.reshape(Mmap @ m, (n, n), order="C")
    k1 = keys[canon(())]
    kA = keys[canon((("A", 0),))]
    kB = keys[canon((("B", 0),))]
    kdiag = keys[canon((("A", 0), ("B", 0)))]
    koff = keys[canon((("A", 0), ("B", 1)))] if N > 1 else None
    cons = [G >> 0, m[k1] == 1]
    if koff is not None:
        cons.append(m[koff] == 0)
    prob = cp.Problem(cp.Maximize(m[kdiag]), cons)
    prob.solve(solver=("SCS" if N > 10 else "CLARABEL"), verbose=verbose, **({"eps": 1e-7, "max_iters": 200000} if N > 10 else {}))
    return prob.value, prob.status, K, n, m.value[kA], m.value[kB]


def main():
    for N in [int(a) for a in sys.argv[1:]]:
        t = time.time()
        s, st, K, n, pa, pb = solve(N)
        print(f"N={N:3d}: max s = {s:.6f} (1/s = {1 / s:.3f}); N*s = {N * s:.4f}; marginals {pa:.4f}/{pb:.4f}; "
              f"{st}; {K} moment classes, matrix {n}x{n}; {time.time() - t:.0f} s", flush=True)


if __name__ == "__main__":
    main()
