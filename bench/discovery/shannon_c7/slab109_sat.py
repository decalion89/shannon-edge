#!/usr/bin/env python3
"""Independent certification of the slab result: is there an independent set of size 109 inside the (0,1,1,3)-slab of
C7^4 (u = (3,0,1,1), planes {0,1,2,3}, 1372 points)? SAT with a proof-producing solver (Glucose 4 via PySAT, DRAT proof
written to disk). UNSAT + proof => certified 'max in slab <= 108'. Run under an external `timeout`.
Usage: slab109_sat.py proof_path"""
import itertools
import sys
import numpy as np
from pysat.card import CardEnc, EncType
from pysat.formula import IDPool
from pysat.solvers import Solver

proof_path = sys.argv[1]
m, u = 4, np.array([3, 0, 1, 1])
V = np.array(list(itertools.product(range(7), repeat=m)))
S = [tuple(v) for v in V if (v @ u) % 7 <= 3]
var = {v: i + 1 for i, v in enumerate(S)}
pool = IDPool(start_from=len(S) + 1)
clauses = []
for i, v in enumerate(S):
    for w in S[i + 1:]:
        if all(min((a - b) % 7, (b - a) % 7) <= 1 for a, b in zip(v, w)):
            clauses.append([-var[v], -var[w]])
ne = len(clauses)
clauses += CardEnc.atleast(lits=list(var.values()), bound=109, vpool=pool, encoding=EncType.seqcounter).clauses
print(f"slab points {len(S)}, edge clauses {ne}, total clauses {len(clauses)}", flush=True)
with Solver(name="glucose4", bootstrap_with=clauses, with_proof=True) as s:
    res = s.solve()
    print("RESULT:", "SAT (109 inside the slab!)" if res else "UNSAT: no 109 in the slab", flush=True)
    if not res:
        proof = s.get_proof()
        with open(proof_path, "w") as f:
            f.write("\n".join(proof) + "\n")
        print(f"DRAT proof written: {len(proof)} lines -> {proof_path}", flush=True)
        with open(proof_path.replace(".drat", ".cnf"), "w") as f:
            f.write(f"p cnf {pool.top} {len(clauses)}\n")
            for c in clauses:
                f.write(" ".join(map(str, c)) + " 0\n")
