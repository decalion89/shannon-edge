#!/usr/bin/env python3
"""Domain-wall construction test for C7^5: does an independent set of size 368 exist whose layer sizes along EVERY
coordinate follow the one-wall pattern (53,52,53,52,53,52,53) (pairs 105 x6 and one 106)? (Fixing the pattern in all
5 coordinates simultaneously is a restriction motivated by the rigidity / frustration picture, not a WLOG.)
SAT (CaDiCaL via PySAT): edge clauses of the strong product + exact layer cardinalities. A model = new record.
Usage: domainwall_sat.py  (run under an external `timeout`)"""
import itertools
import sys
import numpy as np
from pysat.card import CardEnc, EncType
from pysat.formula import IDPool
from pysat.solvers import Solver

m = 5
pattern = [53, 52, 53, 52, 53, 52, 53]
V = list(itertools.product(range(7), repeat=m))
idx = {v: i + 1 for i, v in enumerate(V)}
pool = IDPool(start_from=len(V) + 1)
s = Solver(name="cadical195")
offs = [e for e in itertools.product((-1, 0, 1), repeat=m) if any(e)]
ne = 0
for v in V:
    for e in offs:
        w = tuple((v[i] + e[i]) % 7 for i in range(m))
        if idx[w] > idx[v]:
            s.add_clause([-idx[v], -idx[w]]); ne += 1
for c in range(m):
    for x in range(7):
        lits = [idx[v] for v in V if v[c] == x]
        for cl in CardEnc.equals(lits=lits, bound=pattern[x], vpool=pool, encoding=EncType.totalizer).clauses:
            s.add_clause(cl)
print(f"encoded: {ne} edge clauses, aux vars up to {pool.top}", flush=True)
res = s.solve()
print("RESULT:", "SAT -> independent 368-set found!" if res else "UNSAT (no 368-set with this exact one-wall pattern)",
      flush=True)
if res:
    model = set(l for l in s.get_model() if l > 0)
    A = np.array([v for v in V if idx[v] in model])
    np.save("/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/domainwall368.npy", A)
    d = (A[:, None, :] - A[None, :, :]) % 7
    ok = (np.minimum(d, 7 - d) >= 2).any(axis=2); np.fill_diagonal(ok, True)
    print("size", len(A), "independent", ok.all(), flush=True)
