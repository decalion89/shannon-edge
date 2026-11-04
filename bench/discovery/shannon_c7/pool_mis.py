#!/usr/bin/env python3
"""Pool-and-solve: put several good independent sets of C7^m (and random automorphic images of them) into one pool,
then solve the maximum independent set INSIDE the pool exactly (HiGHS MILP with clique constraints of the 2^m boxes),
warm-started from the best input set. Mixtures of fragments of different near-optimal sets can escape the local
optimum of each. Usage: pool_mis.py seconds seed images_per_set out.npy set1.npy [set2.npy ...]
"""
import itertools
import sys
import numpy as np
import highspy

secs, seed, k, out = float(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
sets = [np.load(f) % 7 for f in sys.argv[5:]]
m = sets[0].shape[1]
rng = np.random.default_rng(seed)
perms = list(itertools.permutations(range(m)))
pool = [sets[0]]
for S in sets:
    pool.append(S)
    for _ in range(k):
        P = perms[rng.integers(len(perms))]
        s = rng.choice([1, -1], size=m)
        t = rng.integers(0, 7, size=m)
        pool.append((S[:, list(P)] * s + t) % 7)
w = 7 ** np.arange(m)[::-1]
codes = np.unique(np.concatenate([(p % 7) @ w for p in pool]))
pos = {c: i for i, c in enumerate(codes)}
V = np.array([[(c // 7 ** (m - 1 - j)) % 7 for j in range(m)] for c in codes])
n = len(V)
E = np.array(list(itertools.product((0, 1), repeat=m)))
rows = []
for a in itertools.product(range(7), repeat=m):
    box = ((np.array(a) + E) % 7) @ w
    mem = [pos[c] for c in box if c in pos]
    if len(mem) > 1:
        rows.append(mem)
print(f"pool: {n} distinct points from {len(pool)} sets; {len(rows)} box constraints", flush=True)
h = highspy.Highs()
h.setOptionValue("output_flag", False)
h.setOptionValue("time_limit", secs)
lp = highspy.HighsLp()
lp.num_col_, lp.num_row_ = n, len(rows)
lp.col_cost_ = np.full(n, -1.0)
lp.col_lower_, lp.col_upper_ = np.zeros(n), np.ones(n)
lp.row_lower_ = np.full(len(rows), -highspy.kHighsInf)
lp.row_upper_ = np.ones(len(rows))
st, ix = [0], []
for r in rows:
    ix += r; st.append(len(ix))
lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
lp.a_matrix_.start_, lp.a_matrix_.index_ = np.array(st), np.array(ix)
lp.a_matrix_.value_ = np.ones(len(ix))
lp.integrality_ = [highspy.HighsVarType.kInteger] * n
h.passModel(lp)
warm = np.zeros(n)
warm[[pos[c] for c in (sets[0] @ w)]] = 1
sol = highspy.HighsSolution(); sol.col_value = list(warm); h.setSolution(sol)
h.run()
x = np.array(h.getSolution().col_value) > 0.5
S = V[x]
d = (S[:, None, :] - S[None, :, :]) % 7
ok = (np.minimum(d, 7 - d) >= 2).any(axis=2); np.fill_diagonal(ok, True)
info = h.getInfo()
print(f"RESULT pool optimum found {len(S)} (independent {ok.all()}), dual bound {-info.mip_dual_bound:.1f}, "
      f"status {h.modelStatusToString(h.getModelStatus())}", flush=True)
if len(S) > len(sets[0]) and ok.all():
    np.save(out, S)
