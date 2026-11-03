#!/usr/bin/env python3
"""Enumerate copy strategies (up to symmetry of A, B, C, D), project each, and collect every
4-variable inequality found, then reduce the collection to the ones not implied by the others.

Usage: search.py MAX_NEW_VARS OUT.json
"""

import json
import sys
import time
from itertools import combinations, permutations

import numpy as np

import known as K
import project as P


def strategies(max_new):
    """Sequences of copy steps (src, over, dst) on growing variable sets, total new variables <= max_new."""
    out = []

    def rec(nvars, steps, new):
        if steps:
            out.append(list(steps))
        if new == max_new:
            return
        cur = list(range(nvars))
        for k in range(1, max_new - new + 1):
            for src in combinations(cur, k):
                rest = [v for v in cur if v not in src]
                for r in range(1, len(rest) + 1):
                    for over in combinations(rest, r):
                        if len(over) == len(rest):
                            continue  # copying over everything else gives nothing new
                        dst = list(range(nvars, nvars + k))
                        rec(nvars + k, steps + [(list(src), list(over), dst)], new + k)

    rec(4, [], 0)
    return out


def canonical(steps):
    """Canonical form under relabelling of the 4 base variables (new variables keep their order)."""
    best = None
    for p in permutations(range(4)):
        m = lambda v: p[v] if v < 4 else v  # noqa: E731
        key = tuple((tuple(sorted(m(v) for v in s)), tuple(sorted(m(v) for v in o)), tuple(d)) for s, o, d in steps)
        if best is None or key < best:
            best = key
    return best


def main():
    max_new = int(sys.argv[1])
    out = sys.argv[2]
    seen, todo = set(), []
    for st in strategies(max_new):
        c = canonical(st)
        if c not in seen:
            seen.add(c)
            todo.append(st)
    print(f"{len(todo)} copy strategies (up to symmetry), max {max_new} new variables", flush=True)
    found = []
    t0 = time.time()
    for i, st in enumerate(todo):
        n = 4 + sum(len(s) for s, _, _ in st)
        pr = P.Projection(n, st)
        f, done = P.run(pr, max_rounds=60, log=lambda *a: None)
        new = 0
        for ci in f:
            if not any(np.array_equal(ci, g) for g in found):
                found.append(ci)
                new += 1
        print(f"[{i + 1}/{len(todo)}] {st}: {len(f)} inequalities ({'complete' if done else 'partial'}), "
              f"{new} not seen before; total {len(found)}; {time.time() - t0:.0f} s", flush=True)
    # keep only inequalities not implied by Shannon + the others (all relabellings)
    keep = list(found)
    changed = True
    while changed:
        changed = False
        for ci in list(keep):
            others = [g for g in keep if g is not ci]
            if K.implied(ci, others):
                keep = others
                changed = True
                break
    # one representative per relabelling class
    reps = []
    for ci in keep:
        if not any(any(np.array_equal(K.permute(ci, p), r) for p in permutations(range(4))) for r in reps):
            reps.append(ci)
    print(f"\nIrredundant inequalities (up to relabelling): {len(reps)}")
    for r in reps:
        print("  " + P.show(r))
    json.dump([list(map(int, r)) for r in reps], open(out, "w"))


if __name__ == "__main__":
    main()
