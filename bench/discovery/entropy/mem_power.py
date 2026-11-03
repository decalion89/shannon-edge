#!/usr/bin/env python3
"""How strong is a single Maximum Entropy Method instance compared with iterated copies?

Samples MEM instances, keeps every non-Shannon 4-variable inequality they imply, and reports:
* how many are beyond one copy step (not implied by Zhang-Yeung),
* how many are beyond two copy steps (not implied by the exhaustive two-copy set),
* how many of the 214 DFZ inequalities (up to 4 auxiliaries, 3 copy steps) a pool of MEM instances
  implies.

Usage: mem_power.py K NINST SEED TWO_COPY.json OUT.json
"""

import json
import sys

import numpy as np

import dfz
import known as K
import mem
import project as P


def main():
    k, ninst, seed, two, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], sys.argv[5]
    rng = np.random.default_rng(seed)
    n = 4 + k
    pool = [S for S in range(1, 1 << n) if S >> 4 and S != (1 << n) - 1]
    zy = [K.zy_vec()]
    two_copy = [np.array(x) for x in json.load(open(two))]
    found, recs, done_inst = [], [], 0
    while done_inst < ninst:
        dup = sorted(int(x) for x in rng.choice(4, k, replace=True))
        ms = sorted(int(x) for x in rng.choice(pool, int(rng.integers(1, 4)), replace=False))
        pr = mem.MEMProjection(dup, [15] + ms)
        if len(pr.parts) < 2:
            continue
        done_inst += 1
        f, _ = P.run(pr, max_rounds=40, log=lambda *a: None)
        for ci in f:
            if K.implied(ci, []) or any(np.array_equal(ci, g) for g in found):
                continue
            found.append(ci)
            beyond1 = not K.implied(ci, zy)
            beyond2 = not K.implied(ci, two_copy)
            recs.append(dict(ineq=[int(x) for x in ci], dup=dup, maxsets=ms, parts=len(pr.parts),
                             beyond_one_copy=beyond1, beyond_two_copies=beyond2))
            if beyond2:
                print(f"beyond two copy steps: {P.show(ci)} dup={dup} maxsets={ms} ({len(pr.parts)} CI)", flush=True)
        if done_inst % 50 == 0:
            print(f"{done_inst} instances, {len(found)} non-Shannon inequalities, "
                  f"{sum(r['beyond_one_copy'] for r in recs)} beyond one copy, "
                  f"{sum(r['beyond_two_copies'] for r in recs)} beyond two", flush=True)
    L = dfz.final_list()
    covered = sum(K.implied(v, found) for v in L) if found else 0
    print(f"\n{ninst} multi-statement MEM instances: {len(found)} distinct non-Shannon inequalities; "
          f"{sum(r['beyond_one_copy'] for r in recs)} beyond one copy step, "
          f"{sum(r['beyond_two_copies'] for r in recs)} beyond two copy steps; "
          f"they imply {covered} of the 214 DFZ inequalities")
    json.dump(recs, open(out, "w"))


if __name__ == "__main__":
    main()
