#!/usr/bin/env python3
"""Random search beyond the Dougherty-Freiling-Zeger frontier: copy strategies with four auxiliary
variables and four copy steps (DFZ exhausted four auxiliaries only up to three steps, arXiv:1104.3602).
Every inequality found is tested against Shannon + the 214 DFZ inequalities under all relabellings;
survivors are candidates for new non-Shannon inequalities.

Usage: frontier.py SEED HOURS OUT.jsonl
"""

import json
import sys
import time

import numpy as np

import dfz
import known as K
import project as P


def random_strategy(rng, steps=4):
    n, st = 4, []
    for _ in range(steps):
        cur = list(range(n))
        src = [int(rng.choice(cur))]
        rest = [v for v in cur if v not in src]
        k = int(rng.integers(1, len(rest)))  # strictly fewer than all others
        over = sorted(int(x) for x in rng.choice(rest, k, replace=False))
        st.append((src, over, [n]))
        n += 1
    return st


def main():
    seed, hours, out = int(sys.argv[1]), float(sys.argv[2]), sys.argv[3]
    rng = np.random.default_rng(seed)
    known = dfz.final_list()
    t0, tried, cands = time.time(), 0, []
    while time.time() - t0 < hours * 3600:
        st = random_strategy(rng)
        tried += 1
        try:
            pr = P.Projection(8, st)
            found, done = P.run(pr, max_rounds=40, log=lambda *a: None)
        except Exception as e:  # numerical trouble in one strategy should not stop the search
            print(f"strategy {st}: error {e}", flush=True)
            continue
        for ci in found:
            if K.implied(ci, []):
                continue
            if not K.implied(ci, known + [np.array(c) for c in cands]):
                cands.append(ci)
                rec = dict(ineq=[int(x) for x in ci], strategy=st, complete=done)
                with open(out, "a") as f:
                    f.write(json.dumps(rec) + "\n")
                print(f"CANDIDATE after {tried} strategies: {P.show(ci)}  via {st}", flush=True)
        if tried % 10 == 0:
            print(f"{tried} strategies, {len(cands)} candidates, {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
