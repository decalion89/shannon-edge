#!/usr/bin/env python3
"""Second post-quantum window (atlas N=4): extract the optimal almost-quantum (NPA 1+AB) strategy for
f = [[0,0,0,0],[0,0,1,1],[0,1,0,1],[1,1,1,0]] and test whether it violates some member of the coincidence
family  (sum_k p(a_k b_k|x_k y_k))^2 <= sum_{k,l} p(a_k b_l|x_k y_l)  (valid for all quantum boxes).
Box: Alice setting s, outcome a = message; Bob setting (t, m), outcome o in {0, 1, abstain}.
Search: local search over lists (with repetition) of (s, a; (t,m), o) pairs maximising S^2 - T.
"""
import itertools
import sys
import numpy as np
import cvxpy as cp

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from atlas import reduce_word, ZERO  # noqa: E402
import scipy.sparse as sp  # noqa: E402

F = np.array([[0, 0, 0, 0], [0, 0, 1, 1], [0, 1, 0, 1], [1, 1, 1, 0]])
N = 4
A = [(("A", s, 0),) for s in range(N)]
B = [(("B", t, m, o),) for t in range(N) for m in range(2) for o in range(2)]
ops = [()] + A + B + [a + b for a in A for b in B]
n = len(ops)
keys, dr, dc = {ZERO: 0}, [], []
for r in range(n):
    for c in range(r, n):
        k = reduce_word(tuple(reversed(ops[r])) + ops[c])
        keys.setdefault(k, len(keys))
        dr.append(r * n + c); dc.append(keys[k])
        if r != c:
            dr.append(c * n + r); dc.append(keys[k])
M = sp.csr_matrix((np.ones(len(dr)), (dr, dc)), shape=(n * n, len(keys)))
mv = cp.Variable(len(keys))
G = cp.reshape(M @ mv, (n, n), order="C")
g = lambda w: mv[keys[reduce_word(w)]]  # noqa: E731


def P(s, a, t, m, o):  # p(a, o | s, (t, m)), o in {0,1,2(abstain)}
    As = (("A", s, 0),)
    if o == 2:
        tot = 1 if a == 0 else 1
        pa = g(As) if a == 0 else 1 - g(As)
        return pa - P(s, a, t, m, 0) - P(s, a, t, m, 1)
    Bw = (("B", t, m, o),)
    return g(As + Bw) if a == 0 else g(Bw) - g(As + Bw)


w = cp.Variable()
cons = [G >> 0, mv[0] == 0, g(()) == 1]
for s, t, m in itertools.product(range(N), range(N), range(2)):
    for a in range(2):
        for o in range(3):
            cons.append(P(s, a, t, m, o) >= 0)
for s, t in itertools.product(range(N), range(N)):
    f = int(F[s, t])
    cons.append(P(s, 0, t, 0, 1 - f) + P(s, 1, t, 1, 1 - f) == 0)
    cons.append(w <= P(s, 0, t, 0, f) + P(s, 1, t, 1, f))
cp.Problem(cp.Maximize(w), cons).solve(solver="SCS", eps=1e-9, max_iters=500000)
print(f"AQ optimum {w.value:.6f}", flush=True)
box = {}
for s, a, t, m, o in itertools.product(range(N), range(2), range(N), range(2), range(3)):
    box[(s, a, t, m, o)] = float(P(s, a, t, m, o).value)
items = list(box.keys())
rng = np.random.default_rng(0)


def ST(lst):
    S = sum(box[(s, a, t, m, o)] for (s, a, t, m, o) in lst)
    T = sum(box[(k[0], k[1], l[2], l[3], l[4])] for k in lst for l in lst)
    return S * S - T


best, bestl = -np.inf, None
for restart in range(300):
    lst = [items[i] for i in rng.integers(len(items), size=rng.integers(2, 10))]
    val = ST(lst)
    for step in range(3000):
        cand = list(lst)
        r = rng.random()
        if r < 0.4 and len(cand) > 1:
            cand.pop(rng.integers(len(cand)))
        elif r < 0.8:
            cand.append(items[rng.integers(len(items))])
        else:
            cand[rng.integers(len(cand))] = items[rng.integers(len(items))]
        v = ST(cand)
        if v >= val:
            lst, val = cand, v
    if val > best:
        best, bestl = val, lst
print(f"max over searched lists of S^2 - T = {best:.6f}  ({'VIOLATION: the family detects this window' if best > 1e-6 else 'no violation found'})")
if best > 1e-6:
    print("list (s,a,t,m,o):", sorted(bestl))
