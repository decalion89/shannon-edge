#!/usr/bin/env python3
"""Bipartite fusion of two independent sets of C7^m. For independent A, B (any automorphic image of B), conflicts in
A u tau(B) only go between A and tau(B): the conflict graph is bipartite, so (Koenig) the maximum independent subset
of the union has size |A| + |tau(B)| - nu, nu = maximum matching (exact, polynomial). Search over automorphisms tau
(coordinate permutation, signs, translation): random sampling + local moves on the translation. Any result > |A|
is verified pairwise and saved. Usage: bipartite_fusion.py A.npy B.npy seconds seed out.npy
"""
import itertools
import sys
import time
import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import maximum_bipartite_matching

A = np.load(sys.argv[1]) % 7
B = np.load(sys.argv[2]) % 7
secs, seed, out = float(sys.argv[3]), int(sys.argv[4]), sys.argv[5]
m = A.shape[1]
rng = np.random.default_rng(seed)
perms = list(itertools.permutations(range(m)))


def conflicts(Bt):
    d = (A[:, None, :] - Bt[None, :, :]) % 7
    return (np.minimum(d, 7 - d) <= 1).all(axis=2)  # |A| x |B| conflict matrix (includes equal points)


def fused_size(Bt):
    C = conflicts(Bt)
    M = sp.csr_matrix(C)
    match = maximum_bipartite_matching(M, perm_type="column")
    nu = int((match >= 0).sum())
    return len(A) + len(Bt) - nu, nu


def extract(Bt):
    """explicit maximum independent set of the bipartite union via Koenig (min vertex cover complement)."""
    import networkx as nx
    C = conflicts(Bt)
    G = nx.Graph()
    G.add_nodes_from([("a", i) for i in range(len(A))], bipartite=0)
    G.add_nodes_from([("b", j) for j in range(len(Bt))], bipartite=1)
    G.add_edges_from((("a", i), ("b", j)) for i, j in zip(*np.nonzero(C)))
    top = [("a", i) for i in range(len(A))]
    match = nx.bipartite.maximum_matching(G, top_nodes=top)
    cover = nx.bipartite.to_vertex_cover(G, match, top_nodes=top)
    keepA = [i for i in range(len(A)) if ("a", i) not in cover]
    keepB = [j for j in range(len(Bt)) if ("b", j) not in cover]
    return np.vstack([A[keepA], Bt[keepB]])


best, t0, it = 0, time.time(), 0
while time.time() - t0 < secs:
    it += 1
    P = perms[rng.integers(len(perms))]
    s = rng.choice([1, -1], size=m)
    t = rng.integers(0, 7, size=m)
    Bt = (B[:, list(P)] * s + t) % 7
    val, nu = fused_size(Bt)
    for _ in range(30):  # local moves on the translation
        t2 = t.copy(); t2[rng.integers(m)] = rng.integers(7)
        Bt2 = (B[:, list(P)] * s + t2) % 7
        v2, n2 = fused_size(Bt2)
        if v2 >= val:
            t, Bt, val, nu = t2, Bt2, v2, n2
    if val > best:
        best = val
        print(f"best fused size {best} (matching {nu}) at {time.time() - t0:.0f}s, iter {it}", flush=True)
        if best > len(A):
            S = extract(Bt)
            d = (S[:, None, :] - S[None, :, :]) % 7
            ok = (np.minimum(d, 7 - d) >= 2).any(axis=2); np.fill_diagonal(ok, True)
            print(f"  explicit set size {len(S)}, distinct {len({tuple(r) for r in S}) == len(S)}, independent {ok.all()}",
                  flush=True)
            np.save(out, S)
print(f"final best {best} after {it} automorphism trials", flush=True)
