"""Are unlabelled single-sample spikes single-bit flips of the raw ADC code?
For each unlabelled detection in a --report file: take the flagged sample,
its neighbours, estimate the local quantisation step (smallest positive gap
between distinct values within +-1 day), and express the excursion in
steps. A bit flip moves the code by exactly +-2^k and the next sample
returns to the previous value."""
import io, re, sys, zipfile
import numpy as np, pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A

zp, report = sys.argv[1], sys.argv[2]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
rows = []
sec = open(report).read().split("overlap no labelled event")[1]
for m in re.finditer(r"^\| (\d+) \| (\d+) \| ([^|]+) \| ([^|]+) \| ([\d.]+) \| ([+\-\d.]+) \|", sec, re.M):
    rows.append((int(m[1]), int(m[2]), pd.Timestamp(m[3].strip()), pd.Timestamp(m[4].strip()), float(m[6])))
out = []
for c in sorted({r[1] for r in rows}):
    s = A.load(z, f"{root}/channels/channel_{c}.zip")
    s = s[~s.index.duplicated(keep="last")]
    idx = s.index
    for rank, ch, a, e, exc in [r for r in rows if r[1] == c]:
        i = idx.get_indexer([a], method="nearest")[0]
        # the flagged sample may be the spike itself or the return from it: look at i-1, i
        best = None
        for j in (i - 1, i):
            if j < 1 or j + 1 >= len(s):
                continue
            prev, v, nxt = s.iloc[j - 1], s.iloc[j], s.iloc[j + 1]
            if v != prev and abs(nxt - prev) <= abs(v - prev) * 1e-6 + 1e-12:
                best = (j, prev, v, nxt)
        if best is None:
            out.append((rank, c, str(a), exc, "not a single-sample excursion", None))
            continue
        j, prev, v, nxt = best
        w = s.iloc[max(0, j - 5000): j + 5000].to_numpy(np.float64)
        u = np.unique(w)
        gaps = np.diff(u)
        step = gaps[gaps > 0].min() if (gaps > 0).any() else np.nan
        d = (v - prev) / step
        k = int(round(d))
        exact = abs(d - k) < 0.15
        pow2 = exact and k != 0 and (abs(k) & (abs(k) - 1)) == 0
        out.append((rank, c, str(a), exc, f"{d:+.2f} steps", "power of 2" if pow2 else ("integer" if exact else "non-integer")))
print("| Rank | Channel | Time | Excess (bits) | Excursion | Kind |")
print("|---:|---:|---|---:|---:|---|")
for r in sorted(out):
    print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:+.1f} | {r[4]} | {r[5] or '-'} |")
kinds = pd.Series([r[5] for r in out if r[5]])
print("\n", kinds.value_counts().to_dict(), "single-sample excursions of", len(out), "detections")
ks = [abs(int(round(float(r[4].split()[0])))) for r in out if r[5] in ("power of 2", "integer")]
big = [k for k in ks if k >= 3]
print("integer excursions >= 3 steps:", len(big), "of which powers of 2:", sum((k & (k - 1)) == 0 for k in big))
print("excursion sizes:", sorted(ks))
