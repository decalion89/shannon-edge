#!/usr/bin/env python3
"""Atlas of one-bit zero-error one-way communication tasks across theories (see PREREGISTRATION.md).

Task: f: [N]x[N] -> {0,1}. Alice (setting s, binary outcome = message M), Bob (setting (t, M), outcome
0, 1 or abstain). Zero error, maximise the worst-case conclusive probability.
Values: classical (LP), nonsignalling (LP), NPA level 1, 1+AB (almost quantum), level 2 (SDP).
Usage: atlas.py N [prune] [start=K]  -> one line per function class, JSON lines to stdout
       atlas.py N check      -> equality sanity check only
"""
import itertools
import json
import sys
import time

import cvxpy as cp
import numpy as np
import scipy.sparse as sp

ZERO = "ZERO"
TOL = 1e-4


# ---------------------------------------------------------------- task classes
def canon_f(F):
    N = F.shape[0]
    best = None
    for G in (F, 1 - F):
        for pr in itertools.permutations(range(N)):
            H = G[list(pr)]
            # sort columns lexicographically = canonical under column permutations
            cols = sorted(tuple(H[:, j]) for j in range(N))
            key = tuple(tuple(c) for c in cols)
            if best is None or key < best:
                best = key
    return best


def function_classes(N):
    seen = {}
    for bits in itertools.product((0, 1), repeat=N * N):
        F = np.array(bits).reshape(N, N)
        k = canon_f(F)
        if k not in seen:
            seen[k] = np.array(k).T  # columns back to matrix
    return list(seen.values())


# ---------------------------------------------------------------- classical
def classical(F):
    N = F.shape[0]
    cols = []
    for alpha in itertools.product((0, 1), repeat=N):
        C = np.zeros((N, N))
        for s in range(N):
            same = [u for u in range(N) if alpha[u] == alpha[s]]
            for t in range(N):
                C[s, t] = 1.0 if len({F[u, t] for u in same}) == 1 else 0.0
        cols.append(C.ravel())
    Cm = np.array(cols).T
    lam, w = cp.Variable(Cm.shape[1], nonneg=True), cp.Variable()
    p = cp.Problem(cp.Maximize(w), [cp.sum(lam) == 1, Cm @ lam >= w])
    p.solve(solver="CLARABEL")
    return p.value


# ---------------------------------------------------------------- nonsignalling
def nonsignalling(F):
    N = F.shape[0]
    # p[s, a, t, m, o], o in {0, 1, 2=abstain}
    P = cp.Variable((N * 2, N * 2 * 3), nonneg=True)
    idx = lambda s, a: s * 2 + a  # noqa: E731
    jdx = lambda t, m, o: (t * 2 + m) * 3 + o  # noqa: E731
    cons = []
    for s in range(N):
        for t in range(N):
            for m in range(2):
                cons.append(sum(P[idx(s, a), jdx(t, m, o)] for a in range(2) for o in range(3)) == 1)
    for s in range(N):  # Alice marginal independent of Bob's setting
        for a in range(2):
            ref = sum(P[idx(s, a), jdx(0, 0, o)] for o in range(3))
            for t in range(N):
                for m in range(2):
                    cons.append(sum(P[idx(s, a), jdx(t, m, o)] for o in range(3)) == ref)
    for t in range(N):
        for m in range(2):
            for o in range(3):
                ref = sum(P[idx(0, a), jdx(t, m, o)] for a in range(2))
                for s in range(1, N):
                    cons.append(sum(P[idx(s, a), jdx(t, m, o)] for a in range(2)) == ref)
    w = cp.Variable()
    for s in range(N):
        for t in range(N):
            f = F[s, t]
            cons.append(sum(P[idx(s, a), jdx(t, a, 1 - f)] for a in range(2)) == 0)
            cons.append(w <= sum(P[idx(s, a), jdx(t, a, f)] for a in range(2)))
    p = cp.Problem(cp.Maximize(w), cons)
    p.solve(solver="CLARABEL")
    return p.value


# ---------------------------------------------------------------- NPA
def reduce_word(word):
    a = [l for l in word if l[0] == "A"]
    b = [l for l in word if l[0] == "B"]

    def merge(seq):
        out = []
        for l in seq:
            if out and out[-1][:-1] == l[:-1] and out[-1] != l:
                return None  # same setting, different outcome: orthogonal
            if not out or out[-1] != l:
                out.append(l)
        return out

    ra, rb = merge(a), merge(b)
    if ra is None or rb is None:
        return ZERO
    return min((tuple(ra), tuple(rb)), (tuple(ra[::-1]), tuple(rb[::-1])))


def npa(F, level):
    """level in {'1', '1+AB', '2'}; Alice projector ('A', s, 0); Bob ('B', t, m, o), o in {0, 1}."""
    N = F.shape[0]
    A = [(("A", s, 0),) for s in range(N)]
    B = [(("B", t, m, o),) for t in range(N) for m in range(2) for o in range(2)]
    ops = [()] + A + B
    if level in ("1+AB", "2"):
        ops += [a + b for a in A for b in B]
    if level == "2":
        ops += [a1 + a2 for a1 in A for a2 in A if a1 != a2]
        ops += [b1 + b2 for b1 in B for b2 in B if b1[0][1:3] != b2[0][1:3]]
    n = len(ops)
    keys, dr, dc = {ZERO: 0}, [], []
    for r in range(n):
        for c in range(r, n):
            k = reduce_word(tuple(reversed(ops[r])) + ops[c])
            keys.setdefault(k, len(keys))
            dr.append(r * n + c); dc.append(keys[k])
            if r != c:
                dr.append(c * n + r); dc.append(keys[k])
    M = sp.csr_matrix((np.ones(len(dr)), (dr, dc)), shape=(n * n, len(keys)))
    mv = cp.Variable(len(keys))
    G = cp.reshape(M @ mv, (n, n), order="C")
    g = lambda w: mv[keys[reduce_word(w)]]  # noqa: E731

    def joint(s, a, t, o):  # P(Alice outcome a, Bob outcome o | s, (t, a)), o in {0,1}
        Bw = (("B", t, a, o),)
        if a == 0:
            return g((("A", s, 0),) + Bw)
        return g(Bw) - g((("A", s, 0),) + Bw)

    w = cp.Variable()
    cons = [G >> 0, mv[0] == 0, g(()) == 1]
    # nonnegativity of every joint probability (not implied at level 1)
    for s in range(N):
        for t in range(N):
            for m in range(2):
                As, B0, B1 = (("A", s, 0),), (("B", t, m, 0),), (("B", t, m, 1),)
                for o_w in (B0, B1):
                    cons += [g(As + o_w) >= 0, g(o_w) - g(As + o_w) >= 0]
                cons += [g(As) - g(As + B0) - g(As + B1) >= 0,
                         1 - g(As) - g(B0) - g(B1) + g(As + B0) + g(As + B1) >= 0]
    for s in range(N):
        for t in range(N):
            f = int(F[s, t])
            cons.append(joint(s, 0, t, 1 - f) + joint(s, 1, t, 1 - f) == 0)
            cons.append(w <= joint(s, 0, t, f) + joint(s, 1, t, f))
    p = cp.Problem(cp.Maximize(w), cons)
    p.solve(solver="SCS", eps=1e-8, max_iters=200000)
    return p.value


def analyse(F, prune=False):
    """prune: skip SDPs that cannot produce an anomaly. If classical = 1 every theory gives 1; if
    AQ <= classical then classical <= quantum <= L2 <= AQ forces L2 = classical."""
    r = {"f": F.tolist()}
    r["classical"] = classical(F)
    if prune and r["classical"] > 1 - TOL:
        r["skipped"] = "classical=1"
        return r
    r["ns"] = nonsignalling(F)
    r["L1+AB"] = npa(F, "1+AB")
    if prune and r["L1+AB"] <= r["classical"] + TOL:
        r["skipped"] = "AQ=classical, so L2=classical"
        return r
    r["L2"] = npa(F, "2")
    if not prune:
        r["L1"] = npa(F, "1")
    return r


if __name__ == "__main__":
    N = int(sys.argv[1])
    if len(sys.argv) > 2 and sys.argv[2] == "check":
        r = analyse(np.eye(N, dtype=int))
        print(json.dumps(r), flush=True)
        sys.exit(0)
    prune = "prune" in sys.argv[2:]
    start = next((int(a[6:]) for a in sys.argv[2:] if a.startswith("start=")), 0)
    classes = function_classes(N)
    print(f"# N={N}: {len(classes)} function classes", file=sys.stderr, flush=True)
    for F in classes[start:]:
        t0 = time.time()
        r = analyse(F, prune)
        r["sec"] = round(time.time() - t0, 2)
        print(json.dumps(r), flush=True)
