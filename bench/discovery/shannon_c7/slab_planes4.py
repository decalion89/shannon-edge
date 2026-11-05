#!/usr/bin/env python3
"""Plane structure of 4-plane slabs in C7^4 for several direction classes: in-plane degree, components, exact alpha
of one plane (MILP), and number of conflicts between consecutive planes."""
import itertools
import numpy as np
import networkx as nx
from scipy.optimize import milp, LinearConstraint, Bounds
import scipy.sparse as sp

V = np.array(list(itertools.product(range(7), repeat=4)))


def close(A, B):
    d = (A[:, None, :] - B[None, :, :]) % 7
    return (np.minimum(d, 7 - d) <= 1).all(axis=2)


for u in [(0, 1, 1, 3), (1, 1, 1, 3), (0, 0, 1, 3), (1, 1, 2, 3), (0, 0, 0, 1)]:
    uu = np.array(u)
    P0 = V[(V @ uu) % 7 == 0]
    P1 = V[(V @ uu) % 7 == 1]
    C = close(P0, P0); np.fill_diagonal(C, False)
    G = nx.from_numpy_array(C.astype(int))
    comps = sorted(len(c) for c in nx.connected_components(G))
    deg = sorted(set(int(x) for x in C.sum(1)))
    I, J = np.nonzero(np.triu(C))
    A = sp.csr_matrix((np.ones(2 * len(I)), (np.repeat(np.arange(len(I)), 2), np.ravel(np.column_stack([I, J])))),
                      shape=(len(I), len(P0)))
    res = milp(c=-np.ones(len(P0)), constraints=[LinearConstraint(A, -np.inf, 1)], integrality=np.ones(len(P0)),
               bounds=Bounds(0, 1), options={"time_limit": 120})
    cross = int(close(P0, P1).sum())
    print(f"u={u}: in-plane degree {deg}, {len(comps)} components of sizes {sorted(set(comps))}, "
          f"alpha(plane) = {int(round(-res.fun))} ({'exact' if res.status == 0 else 'tl'}), cross edges {cross}", flush=True)
