#!/usr/bin/env python3
"""The fully general one-way one-bit zero-error equality task over the almost-quantum set (exploration).

Without loss of generality (the AQ set is convex and closed under local post-processing):
Alice's outcome is the bit she sends, a = M in {0,1}; Bob's setting is (t, M); Bob's outcome is his answer
in {E = "equal", D = "different", abstain}. Projectors: A_x (outcome 0); B_{(t,c),E}, B_{(t,c),D}
(orthogonal; abstain = 1 - E - D). NPA level 1+AB, symmetrised over relabelling the labels [N].
Zero error:  s = t : never D;   s != t : never E.
Maximise the worst case w <= P(E | s = t), w <= P(D | s != t).
"""
import sys
import time

import cvxpy as cp
import numpy as np
import scipy.sparse as sp

ZERO = "ZERO"


def reduce_word(word):
    a = [l for l in word if l[0] == "A"]
    b = [l for l in word if l[0] == "B"]

    def merge(seq):
        out = []
        for l in seq:
            if out and out[-1][:3] == l[:3] and out[-1] != l:  # same Bob setting, different outcome
                return None
            if not out or out[-1] != l:
                out.append(l)
        return out

    ra, rb = merge(a), merge(b)
    if ra is None or rb is None:
        return None
    return ra, rb


def pattern(a, b):
    lab, out = {}, []
    for l in a + b:
        x = l[1]
        if x not in lab:
            lab[x] = len(lab)
        out.append((l[0], lab[x]) + tuple(l[2:]))
    return tuple(out[:len(a)]), tuple(out[len(a):])


def canon(word):
    red = reduce_word(word)
    if red is None:
        return ZERO
    a, b = red
    return min(pattern(a, b), pattern(a[::-1], b[::-1]))


def solve(N, solver="SCS"):
    A = [(("A", x),) for x in range(N)]
    B = [(("B", y, c, o),) for y in range(N) for c in (0, 1) for o in ("E", "D")]
    ops = [()] + A + B + [a + b for a in A for b in B]
    n = len(ops)
    keys = {ZERO: 0}
    dr, dc = [], []
    for r in range(n):
        for c in range(r, n):
            k = canon(tuple(reversed(ops[r])) + ops[c])
            if k not in keys:
                keys[k] = len(keys)
            dr.append(r * n + c)
            dc.append(keys[k])
            if r != c:
                dr.append(c * n + r)
                dc.append(keys[k])
    K = len(keys)
    Mmap = sp.csr_matrix((np.ones(len(dr)), (dr, dc)), shape=(n * n, K))
    m = cp.Variable(K)
    G = cp.reshape(Mmap @ m, (n, n), order="C")
    g = lambda w: m[keys[canon(w)]]  # noqa: E731
    Bm = lambda y, c, o: (("B", y, c, o),)  # noqa: E731
    Ax = (("A", 0),)

    def joint(s, t, c, o):  # P(M = c, Bob outcome o | s, (t, c))
        if c == 0:
            return g(Ax + Bm(t, 0, o))
        return g(Bm(t, 1, o)) - g(Ax + Bm(t, 1, o))

    w = cp.Variable()
    same = [(0, 0)]
    diff = [(0, 1)]
    cons = [G >> 0, m[0] == 0, g(()) == 1]
    for s, t in same:
        cons += [joint(s, t, 0, "D") == 0, joint(s, t, 1, "D") == 0,
                 w <= joint(s, t, 0, "E") + joint(s, t, 1, "E")]
    for s, t in diff:
        cons += [joint(s, t, 0, "E") == 0, joint(s, t, 1, "E") == 0,
                 w <= joint(s, t, 0, "D") + joint(s, t, 1, "D")]
    prob = cp.Problem(cp.Maximize(w), cons)
    if solver == "SCS":
        prob.solve(solver="SCS", eps=1e-7, max_iters=300000)
    else:
        prob.solve(solver=solver)
    return prob.value, prob.status, K, n


if __name__ == "__main__":
    for N in [int(x) for x in sys.argv[1:]]:
        t0 = time.time()
        v, st, K, n = solve(N, "CLARABEL" if N <= 5 else "SCS")
        f = N * N / (17 * N * N - 80 * N + 64) if N >= 8 else 1 / N
        print(f"N={N}: general one-bit AQ optimum = {v:.7f} | restricted-class value {f:.7f} | quantum {1 / N:.5f} "
              f"| {st}; {K} classes, {n}x{n}; {time.time() - t0:.0f}s", flush=True)
