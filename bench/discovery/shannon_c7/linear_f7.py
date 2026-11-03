#!/usr/bin/env python3
"""Linear codes over F7 avoiding nonzero vectors in {-1,0,1}^m (=> independent set of size 7^r in C7^m).
Parametrise by a parity-check matrix H ((m-r) x m); violations = nonzero ternary v with H v = 0 mod 7.
Annealing on H with incremental syndrome updates. Usage: linear_f7.py m r seconds seed
"""
import itertools
import sys
import time
import numpy as np

m, r, secs, seed = int(sys.argv[1]), int(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
rng = np.random.default_rng(seed)
h = m - r
V = np.array(list(itertools.product((-1, 0, 1), repeat=m)), dtype=np.int8)
V = V[np.abs(V).sum(axis=1) > 0]
V = V[[next(x for x in row if x != 0) > 0 for row in V]] if len(V) < 200000 else V[(V != 0).argmax(axis=1).choose(V.T) > 0]
H = rng.integers(0, 7, size=(h, m)).astype(np.int64)
Syn = (V.astype(np.int64) @ H.T) % 7        # one representative per +-pair
viol = int((Syn == 0).all(axis=1).sum())
best = viol
t0 = time.time()
it = 0
while time.time() - t0 < secs and best > 0:
    it += 1
    i, j = rng.integers(h), rng.integers(m)
    new = rng.integers(7)
    delta = (new - H[i, j]) % 7
    if delta == 0:
        continue
    col = (Syn[:, i] + delta * V[:, j]) % 7
    others = np.delete(Syn, i, axis=1)
    nz = (col == 0) & (others == 0).all(axis=1)
    nv = int(nz.sum())
    temp = 3 * (1 - (time.time() - t0) / secs) + 0.05
    if nv <= viol or rng.random() < np.exp((viol - nv) / temp):
        H[i, j], Syn[:, i], viol = new, col, nv
        best = min(best, viol)
rank_ok = np.linalg.matrix_rank(H.astype(float)) == h  # crude (over R) sanity only
print(f"m={m} r={r} seed={seed}: min #(+- pairs of nonzero ternary codewords) = {best} after {it} moves "
      f"(0 would give alpha >= 7^{r} = {7 ** r}, Theta >= {7 ** (r / m):.5f})", flush=True)
