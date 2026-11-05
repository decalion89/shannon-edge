#!/usr/bin/env python3
"""Large-neighbourhood search with exact sub-solves for independent sets in C7^m.
Start from a verified independent set (npy of points). Repeat: pick a random region R (points whose
coordinates lie in random windows on a random subset of coordinates), remove the current points in R, and
solve EXACTLY (MILP, clique constraints) the maximum independent set inside R compatible with the points kept
outside. Accept if not smaller (plateau moves allowed). Usage: lns.py m start.npy seconds seed out.npy [max_region]
"""
import itertools
import sys
import time
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

m, start, secs, seed, out = int(sys.argv[1]), sys.argv[2], float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
rng = np.random.default_rng(seed)
V = np.array(list(itertools.product(range(7), repeat=m)))
w7 = 7 ** np.arange(m)[::-1]
code = lambda X: (np.asarray(X) % 7) @ w7  # noqa: E731
n = len(V)
offs = np.array(list(itertools.product((-1, 0, 1), repeat=m)))
NBR = np.array([code(V[i] + offs) for i in range(n)])          # closed neighbourhoods (3^m each)
cliques = np.array([code(V[i] + np.array(list(itertools.product((0, 1), repeat=m)))) for i in range(n)])
cur = np.zeros(n, bool)
cur[code(np.load(start))] = True


def verify(sel):
    for i in np.nonzero(sel)[0]:
        if sel[NBR[i]].sum() != 1:
            return False
    return True


assert verify(cur)
best = cur.sum()
print(f"m={m} start {best}", flush=True)
t0, it = time.time(), 0
while time.time() - t0 < secs:
    it += 1
    k = rng.integers(1, m + 1)
    coords = rng.choice(m, size=k, replace=False)
    width = rng.integers(2, 6)
    lo = rng.integers(0, 7, size=k)
    inR = np.ones(n, bool)
    for c, l in zip(coords, lo):
        inR &= ((V[:, c] - l) % 7) < width
    if inR.sum() > int(sys.argv[6] if len(sys.argv) > 6 else 900):
        continue
    keep = cur & ~inR
    blocked = np.zeros(n, bool)
    blocked[NBR[np.nonzero(keep)[0]].ravel()] = True
    free = np.nonzero(inR & ~blocked)[0]
    if len(free) == 0:
        continue
    pos = -np.ones(n, int); pos[free] = np.arange(len(free))
    rows = []
    for q in cliques:
        f = pos[q]; f = f[f >= 0]
        if len(f) > 1:
            rows.append(f)
    if rows:
        r = np.concatenate([np.full(len(f), i) for i, f in enumerate(rows)])
        A = sp.csr_matrix((np.ones(len(r)), (r, np.concatenate(rows))), shape=(len(rows), len(free)))
        cons = [LinearConstraint(A, -np.inf, 1)]
    else:
        cons = []
    res = milp(c=-np.ones(len(free)), constraints=cons, integrality=np.ones(len(free)), bounds=Bounds(0, 1),
               options={"time_limit": 60})
    if res.x is None:
        continue
    new = keep.copy(); new[free[res.x > 0.5]] = True
    if new.sum() >= cur.sum() and verify(new):
        if new.sum() > best:
            best = new.sum()
            np.save(out, V[new])
            print(f"m={m} seed={seed}: {best} at {time.time() - t0:.0f}s (iter {it}), verified", flush=True)
        cur = new
print(f"m={m} seed={seed}: final best {best} after {it} iterations", flush=True)
