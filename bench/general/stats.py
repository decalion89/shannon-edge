"""Per dataset: share of bytes equal to the byte above (previous record), and
per-field change rate. Usage: python3 -I stats.py DATA.bin"""
import json, sys, numpy as np
p = sys.argv[1]; m = json.load(open(p[:-4] + ".json")); L = m["record_len"]
a = np.fromfile(p, np.uint8).reshape(-1, L)
same = (a[1:] == a[:-1]).mean()
dt = np.dtype([(n, t) for n, t in m["fields"]]); r = np.fromfile(p, dt)
ch = {n: float((r[n][1:].view(f"u{dt[n].itemsize}") != r[n][:-1].view(f"u{dt[n].itemsize}")).mean()) for n in dt.names}
print(p.split("/")[-1], f"bytes same as above: {same:.1%};", "fields changing in >50% of records:", sum(v > 0.5 for v in ch.values()), "of", len(ch), "; never:", sum(v == 0 for v in ch.values()))
