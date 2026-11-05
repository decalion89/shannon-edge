#!/usr/bin/env python3
"""Slab law test: every known 108-set of C7^4 lies entirely in a 'slab' {x : <u,x> mod 7 in {a,...,a+3}} for some
direction u (3 of the 7 parallel planes empty). By translation symmetry a = 0 WLOG. Exact MILP (HiGHS) for the maximum
independent set INSIDE the slab (4*7^(m-1) points), box/clique constraints, warm start from a known set that fits.
Proven optimum 108 => no 109 lives in this slab family; a 109 => new record.
Usage: slab_mip.py seconds u1 u2 ... um [warm.npy]"""
import itertools
import sys
import numpy as np
import highspy

secs = float(sys.argv[1])
args = sys.argv[2:]
warm_file = args[-1] if args[-1].endswith(".npy") else None
u = np.array([int(x) for x in (args[:-1] if warm_file else args)])
m = len(u)
V = np.array(list(itertools.product(range(7), repeat=m)))
inslab = ((V @ u) % 7) <= 3
S = V[inslab]
w = 7 ** np.arange(m)[::-1]
pos = {c: i for i, c in enumerate(S @ w)}
n = len(S)
E = np.array(list(itertools.product((0, 1), repeat=m)))
rows = []
for a in V:
    mem = [pos[c] for c in ((a + E) % 7) @ w if c in pos]
    if len(mem) > 1:
        rows.append(mem)
h = highspy.Highs()
h.setOptionValue("output_flag", False)
h.setOptionValue("time_limit", secs)
h.setOptionValue("threads", 2)
lp = highspy.HighsLp()
lp.num_col_, lp.num_row_ = n, len(rows)
lp.col_cost_ = np.full(n, -1.0)
lp.col_lower_, lp.col_upper_ = np.zeros(n), np.ones(n)
lp.row_lower_, lp.row_upper_ = np.full(len(rows), -highspy.kHighsInf), np.ones(len(rows))
st, ix = [0], []
for r in rows:
    ix += r; st.append(len(ix))
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_, lp.a_matrix_.index_ = np.array(st), np.array(ix)
lp.a_matrix_.value_ = np.ones(len(ix))
lp.integrality_ = [highspy.HighsVarType.kInteger] * n
h.passModel(lp)
if warm_file:
    A = np.load(warm_file) % 7
    x0 = np.zeros(n)
    for c in A @ w:
        if c in pos:
            x0[pos[c]] = 1
    sol = highspy.HighsSolution(); sol.col_value = list(x0); h.setSolution(sol)
    print(f"warm start: {int(x0.sum())} of {len(A)} points fit in the slab", flush=True)
h.run()
x = np.array(h.getSolution().col_value) > 0.5
B = S[x]
d = (B[:, None, :] - B[None, :, :]) % 7
ok = (np.minimum(d, 7 - d) >= 2).any(axis=2); np.fill_diagonal(ok, True)
info = h.getInfo()
print(f"RESULT u={u.tolist()} slab size {n}: best {len(B)} (independent {ok.all()}), proven bound {-info.mip_dual_bound:.2f}, "
      f"status {h.modelStatusToString(h.getModelStatus())}", flush=True)
if len(B) > 108 and ok.all():
    np.save("/tmp/claude-0/-home-user/f5214594-0f71-5d98-9550-f6c6aba4b49e/scratchpad/slab_record.npy", B)
