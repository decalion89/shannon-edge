#!/usr/bin/env python3
"""Systematic numerical exploration of the Maximum Entropy Method on four variables (open problem in
Csirmaz, arXiv:2509.12439): random MEM instances with K duplicates and up to M extra maximal sets.
Inequalities not implied by Shannon + Zhang-Yeung + the 214 DFZ inequalities (all relabellings) are
written as candidates.

Usage: memsearch.py K M SEED HOURS OUT.jsonl
"""

import json
import sys
import time

import numpy as np

import dfz
import known as K
import mem
import project as P


def main():
    k, m, seed, hours, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5]
    rng = np.random.default_rng(seed)
    n = 4 + k
    pool = [S for S in range(1, 1 << n) if S >> 4 and S != (1 << n) - 1]
    known = dfz.final_list() + [K.zy_vec()]
    t0, tried, cands, seen = time.time(), 0, [], set()
    stats = {"multi": 0, "single": 0}
    while time.time() - t0 < hours * 3600:
        dup = sorted(int(x) for x in rng.choice(4, k, replace=True))
        r = int(rng.integers(1, m + 1))
        ms = sorted(int(x) for x in rng.choice(pool, r, replace=False))
        key = (tuple(dup), tuple(ms))
        if key in seen:
            continue
        seen.add(key)
        try:
            pr = mem.MEMProjection(dup, [15] + ms)
        except Exception as e:  # noqa: BLE001
            print("build error", e, flush=True)
            continue
        if not pr.parts:
            continue
        stats["multi" if len(pr.parts) > 1 else "single"] += 1
        tried += 1
        try:
            found, done = P.run(pr, max_rounds=40, log=lambda *a: None)
        except Exception as e:  # noqa: BLE001
            print("run error", key, e, flush=True)
            continue
        for ci in found:
            if K.implied(ci, []) or K.implied(ci, known + [np.array(c) for c in cands]):
                continue
            cands.append(ci)
            with open(out, "a") as f:
                f.write(json.dumps(dict(ineq=[int(x) for x in ci], dup=dup, maxsets=ms, parts=len(pr.parts),
                                        complete=done)) + "\n")
            print(f"CANDIDATE: {P.show(ci)}  dup={dup} maxsets={ms} ({len(pr.parts)} CI statements)", flush=True)
        if tried % 25 == 0:
            print(f"{tried} MEM instances ({stats}), {len(cands)} candidates, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
