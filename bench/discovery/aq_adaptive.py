#!/usr/bin/env python3
"""One-bit zero-error equality task where Bob's box setting depends on Alice's message (open question of
arXiv:2610.41448). Exploration.

Box: Alice settings x in [N]; Bob settings (y, c), y in [N], c in {0, 1} (2N settings); binary outcomes;
moments of the outcome-0 projectors A_x, B_{y,c} at NPA level 1+AB, symmetrised over relabelling [N].
Protocol: Alice inputs x = s, sends M = a. Bob inputs (t, M).
  M = 0: Bob says "equal" if b = 0.      Zero error: p(a=0, b=0 | x, (t,0)) = 0 for x != t.
  M = 1: Bob says "different" if b = 0.  Zero error: p(a=1, b=0 | t, (t,1)) = 0.
Worst-case success = min(q, r), q = p(0,0 | s,(s,0)), r = p(1,0 | s,(t,1)) for s != t.
Maximise min(q, r).
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
    lab, out = {}, []
    for l in a + b:
        x = l[1]
        if x not in lab:
            lab[x] = len(lab)
        out.append((l[0], lab[x]) + tuple(l[2:]))
    return tuple(out[:len(a)]), tuple(out[len(a):])


def canon(word):
    a, b = reduce_word(word)
    return min(pattern(a, b), pattern(a[::-1], b[::-1]))


def solve(N):
    A = [(("A", x),) for x in range(N)]
    B = [(("B", y, c),) for y in range(N) for c in (0, 1)]
    ops = [()] + A + B + [a + b for a in A for b in B]
    n = len(ops)
    keys, data_r, data_c = {}, [], []
    for r in range(n):
        for c in range(r, n):
            k = canon(tuple(reversed(ops[r])) + ops[c])
            if k not in keys:
                keys[k] = len(keys)
            data_r.append(r * n + c)
            data_c.append(keys[k])
            if r != c:
                data_r.append(c * n + r)
                data_c.append(keys[k])
    K = len(keys)
    Mmap = sp.csr_matrix((np.ones(len(data_r)), (data_r, data_c)), shape=(n * n, K))
    m = cp.Variable(K)
    G = cp.reshape(Mmap @ m, (n, n), order="C")
    g = lambda w: m[keys[canon(w)]]  # noqa: E731
    one = g(())
    q = g((("A", 0), ("B", 0, 0)))                     # p(0,0|s,(s,0))
    zero_eq = g((("A", 0), ("B", 1, 0)))               # p(0,0|x,(t,0)), x != t  -> 0
    b1 = g((("B", 0, 1),))                             # p_B(0|(t,1))
    ab1_same = g((("A", 0), ("B", 0, 1)))              # p(0,0|t,(t,1))
    ab1_diff = g((("A", 0), ("B", 1, 1)))              # p(0,0|s,(t,1)), s != t
    w = cp.Variable()
    cons = [G >> 0, one == 1, zero_eq == 0, b1 - ab1_same == 0, w <= q, w <= b1 - ab1_diff]
    prob = cp.Problem(cp.Maximize(w), cons)
    prob.solve(solver="SCS", eps=1e-8, max_iters=200000)
    return prob.value, prob.status, q.value, (b1 - ab1_diff).value, K, n


if __name__ == "__main__":
    for N in [int(x) for x in sys.argv[1:]]:
        t = time.time()
        v, st, qv, rv, K, n = solve(N)
        lb = N * N / (19 * N * N - 80 * N + 64) if N >= 8 else float("nan")
        print(f"N={N}: adaptive one-bit worst case = {v:.6f} (1/v = {1 / v:.3f}); q={qv:.5f} r={rv:.5f}  "
              f"[quantum 1/N={1 / N:.4f}; companion lower bound {lb:.5f}]  {st}; {K} classes, {n}x{n}; "
              f"{time.time() - t:.0f}s", flush=True)
