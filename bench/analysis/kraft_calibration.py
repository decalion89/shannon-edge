"""Does the flight model obey its own Kraft bound on nominal data?
For a sample coded in an alphabet of 2^b values, a calibrated model gives
P(cost >= b + t) <= 2^-t (at most 2^b outcomes can each have probability
<= 2^-(b+t)). Measure the exceedance on nominal training samples."""
import io, sys, zipfile
import numpy as np, pandas as pd
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
import anomaly_esaadb as A

zp, split, chans = sys.argv[1], pd.Timestamp(sys.argv[2]), sys.argv[3:]
z = zipfile.ZipFile(zp)
root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
for c in ("StartTime", "EndTime"):
    lab[c] = pd.to_datetime(lab[c]).dt.tz_localize(None)
T = [1, 2, 4, 8, 12, 16, 20, 24]
print("| channel | b | nominal train samples | " + " | ".join(f"t={t}" for t in T) + " | max-b |")
print("|---|---:|---:|" + "---:|" * (len(T) + 1))
for c in chans:
    ch = f"channel_{c}"
    s = A.load(z, f"{root}/channels/{ch}.zip")
    n_uniq = len(np.unique(s.to_numpy().astype(np.float32)))
    b = max(1, int(np.ceil(np.log2(min(n_uniq, 65536)))))
    cost = A.surprise(s)
    ts = s.index.values.astype("datetime64[ns]")
    ev = np.zeros(len(ts), bool)
    for r in lab[lab["Channel"] == ch].itertuples():
        a, e = np.searchsorted(ts, np.datetime64(r.StartTime)), np.searchsorted(ts, np.datetime64(r.EndTime), "right")
        ev[a:e] = True
    nom = cost[(ts < np.datetime64(split)) & ~ev]
    cells = []
    for t in T:
        f = (nom >= b + t).mean()
        cells.append(f"{f:.1e} ({'ok' if f <= 2.0**-t else 'X'})")
    print(f"| {c} | {b} | {len(nom):,} | " + " | ".join(cells) + f" | {nom.max()-b:.1f} |", flush=True)
