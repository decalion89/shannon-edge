#!/usr/bin/env python3
"""SAT version of 'is alpha(C7^4) >= 115?' (see alpha115_feasibility.py for the forced layer pattern).
Variables x_v (v in Z_7^4). Clauses: no edge inside the set (strong-product adjacency); for every coordinate c and
layer x: exactly pattern[x] chosen points with v_c = x; at most 10 points in each block {a,a+1}^2 x C7^2 and at most
3 in each {a,a+1}^3 x C7 (implied, added to help propagation). Solver: CaDiCaL 1.9.5 via PySAT.
UNSAT => alpha(C7^4) <= 114. Usage: alpha115_sat.py seconds
"""
import itertools
import sys
import threading
import time
from pysat.card import CardEnc, EncType
from pysat.formula import CNF, IDPool
from pysat.solvers import Solver

secs = float(sys.argv[1])
m = 4
pattern = [16, 16, 17, 16, 17, 16, 17]
V = list(itertools.product(range(7), repeat=m))
pool = IDPool()
var = {v: pool.id(("x", v)) for v in V}
cnf = CNF()
close1 = lambda a, b: min((a - b) % 7, (b - a) % 7) <= 1  # noqa: E731
for i, v in enumerate(V):
    for w in V[i + 1:]:
        if all(close1(a, b) for a, b in zip(v, w)):
            cnf.append([-var[v], -var[w]])
n_edges = len(cnf.clauses)
for c in range(m):
    for x in range(7):
        lits = [var[v] for v in V if v[c] == x]
        cnf.extend(CardEnc.equals(lits=lits, bound=pattern[x], vpool=pool, encoding=EncType.seqcounter).clauses)
for s, cap in ((2, 10), (3, 3)):
    for S in itertools.combinations(range(m), s):
        for base in itertools.product(range(7), repeat=s):
            lits = [var[v] for v in V if all((v[S[j]] - base[j]) % 7 in (0, 1) for j in range(s))]
            cnf.extend(CardEnc.atmost(lits=lits, bound=cap, vpool=pool, encoding=EncType.seqcounter).clauses)
print(f"CNF: {pool.top} variables, {len(cnf.clauses)} clauses ({n_edges} edge clauses)", flush=True)
t0 = time.time()
with Solver(name="cadical195", bootstrap_with=cnf.clauses) as s:
    timer = threading.Timer(secs, s.interrupt)
    timer.start()
    res = s.solve_limited(expect_interrupt=True)
    timer.cancel()
    verdict = {True: "SAT (a 115-set exists!)", False: "UNSAT => alpha(C7^4) <= 114", None: "unknown (time limit)"}[res]
    print(f"RESULT: {verdict}  [{time.time() - t0:.0f}s]", flush=True)
    if res:
        model = set(l for l in s.get_model() if l > 0)
        chosen = [v for v in V if var[v] in model]
        import numpy as np
        np.save("/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/sat115.npy", np.array(chosen))
        print("size", len(chosen))
