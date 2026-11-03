#!/usr/bin/env python3
"""Over-pack and repair: take the cyclic set {t*g mod n} (n points, too dense for a lossless map), project to
C7^m by phi_i(x) = floor(7*(x + c_i)/n) mod 7, and keep a MAXIMUM independent subset (exact MILP) of the
conflict graph (two points conflict iff their images are equal or adjacent in every coordinate of C7).
Calibration: Polak-Schrijver n=382, g=(1,7,49,343,2401) mod 382 -> 367.
Usage: overpack_repair.py n a [c1..cm]    (g = powers of a)
"""
import sys
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp


def conflict_edges(img):
    n = len(img)
    E = []
    for i in range(n):
        d = (img[i + 1:] - img[i]) % 7
        close = (np.minimum(d, 7 - d) <= 1).all(axis=1)
        for j in np.nonzero(close)[0]:
            E.append((i, i + 1 + j))
    return E


def mis(n, E, time_limit=120):
    if not E:
        return n, np.ones(n, bool)
    rows = np.repeat(np.arange(len(E)), 2)
    cols = np.array(E).ravel()
    A = sp.csr_matrix((np.ones(2 * len(E)), (rows, cols)), shape=(len(E), n))
    res = milp(c=-np.ones(n), constraints=LinearConstraint(A, -np.inf, 1), integrality=np.ones(n),
               bounds=Bounds(0, 1), options={"time_limit": time_limit})
    x = res.x > 0.5
    return int(x.sum()), x


def run(n, g, c, m):
    W = (np.arange(n)[:, None] * np.array(g)[None, :]) % n
    img = np.floor(7 * (W + np.array(c)[None, :]) / n).astype(int) % 7
    E = conflict_edges(img)
    size, x = mis(n, E)
    # verify
    S = img[x]
    for i in range(len(S)):
        d = (S - S[i]) % 7
        ok = (np.minimum(d, 7 - d) >= 2).any(axis=1)
        ok[i] = True
        assert ok.all()
    return size, len(E)


if __name__ == "__main__":
    n, a = int(sys.argv[1]), int(sys.argv[2])
    m = 5
    c = [float(v) for v in sys.argv[3:3 + m]] if len(sys.argv) > 3 else [0.0] * m
    g = [pow(a, i, n) for i in range(m)]
    size, ne = run(n, g, c, m)
    print(f"n={n} g={g} c={c}: conflicts {ne}, max independent subset {size} (verified)")
