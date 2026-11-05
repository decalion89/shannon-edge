#!/usr/bin/env python3
"""m = 6 over-pack + exact repair with uniform cuts, g = powers of a. Prints repaired sizes for given n, a list.
Usage: scan_m6.py a n1 n2 ..."""
import sys
import time
import numpy as np
from overpack_repair import conflict_edges, mis

m = 6
a = int(sys.argv[1])
for n in [int(x) for x in sys.argv[2:]]:
    t0 = time.time()
    g = np.array([pow(a, i, n) for i in range(m)])
    W = (np.arange(n)[:, None] * g[None, :]) % n
    img = (7 * W) // n
    E = conflict_edges(img)
    s, _ = mis(n, E, time_limit=120)
    print(f"m=6 n={n} a={a}: conflicts {len(E)}, repaired {s}  (2s/7 slice avg {2 * s / 7:.1f}; need pairs >= 368) "
          f"[{time.time() - t0:.0f}s]", flush=True)
