#!/usr/bin/env python3
"""Pre-registered test (bench/results/nab_preregistration.md): detector
combination by training margin on NAB.

    python3 bench/nab_combination.py NAB_DATA_DIR LABELS_JSON
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ucr_anomaly import costs, period  # noqa: E402

data_dir, labels = Path(sys.argv[1]), json.load(open(sys.argv[2]))
res = {"surprise": 0, "mp": 0, "combined": 0, "either": 0}
n = 0
for name, wins in sorted(labels.items()):
    if not wins:
        continue
    df = pd.read_csv(data_dir / name)
    ts = pd.to_datetime(df["timestamp"]).values
    x = df["value"].to_numpy(np.float64)
    tr = int(0.15 * len(x))
    w = [(np.datetime64(pd.Timestamp(a)), np.datetime64(pd.Timestamp(b))) for a, b in wins]
    w = [(a, b) for a, b in w if b >= ts[tr]]
    if not w:
        continue
    n += 1
    m = period(x[:tr])

    def correct(i):
        return any(a <= ts[i] <= b for a, b in w)

    c = costs(x)
    skip = tr // 10
    i_s = tr + int(np.argmax(c[tr:]))
    marg_s = float(c[tr:].max() / (c[skip:tr].max() + 1e-12))
    import stumpy
    mp = stumpy.stump(x, m)[:, 0].astype(np.float64)
    mp[~np.isfinite(mp)] = -1
    top = tr + int(np.argmax(mp[tr:len(x) - m + 1]))
    i_m = min(top + m // 2, len(x) - 1)
    marg_m = float(mp[tr:len(x) - m + 1].max() / (mp[:max(1, tr - m)].max() + 1e-12))
    cs, cm = correct(i_s), correct(i_m)
    cc = cs if marg_s > marg_m else cm
    res["surprise"] += cs
    res["mp"] += cm
    res["combined"] += cc
    res["either"] += cs or cm
    print(f"{name}: surprise {int(cs)} (margin {marg_s:.2f}), mp {int(cm)} (margin {marg_m:.2f}) -> combined {int(cc)}",
          file=sys.stderr, flush=True)
print(f"NAB, {n} files with a labelled window after the 15% prefix:")
for k, v in res.items():
    print(f"  {k}: {v}/{n} ({v / n:.3f})" + ("  (oracle, not a method)" if k == "either" else ""))
