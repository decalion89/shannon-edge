#!/usr/bin/env python3
"""Noise, structure and decision layers of a telemetry link (pre-registered in
bench/discovery/bit_layers_preregistration.md). Real frame bytes of the flight profile.

Usage:
  bit_layers.py tsbad TSB-AD-U.zip TSB-AD-M.zip TSB-AD-checkout [--jobs 2]
  bit_layers.py esa ESA-Mission1.zip ESA-Mission2.zip
"""

import io
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import load  # noqa: E402
from esa_edge_link import flight, to_codes, varint_len  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"


def robust_sigma(x):
    d = np.diff(x)
    if len(d) == 0:
        return 0.0
    return float(1.4826 * np.median(np.abs(d - np.median(d))) / np.sqrt(2))


def layers(v, sigma):
    """Lossless bytes, structure bytes, bound held, cost per sample (bits)."""
    codes = to_codes(v)
    L, cost = flight(codes)
    if not sigma > 0:
        return L, L, False, cost
    step = 2 * sigma
    k = np.round((v - v[0]) / step).astype(np.int64)
    idx = k - k.min()
    if idx.max() >= 65536:
        return L, L, False, cost
    err = float(np.max(np.abs(v[0] + step * k - v)))
    if err > sigma * (1 + 1e-9) + 1e-12:
        return L, L, False, cost
    E, _ = flight(idx.astype("<u2"))
    return L, E, True, cost


def tsbad_one(job):
    zp, coll, name = job
    z = zipfile.ZipFile(zp)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    X = df.drop(columns=[c for c in df.columns if c.lower() == "label"]).to_numpy(np.float64)
    tr = int(name.split(".")[0].split("_")[-3])
    Ls = Es = 0
    held = pos = 0
    for j in range(X.shape[1]):
        v = X[:, j]
        s = robust_sigma(v[: max(tr, 2)])
        L, E, ok, _ = layers(v, s)
        Ls += L
        Es += E
        held += ok
        pos += s > 0
    return dict(collection=coll, file=name, n=len(X), channels=X.shape[1], lossless_B=Ls, structure_B=Es,
                noise_share=1 - Es / Ls, channels_sigma_pos=pos, channels_bound_held=held)


def tsbad(args):
    uz, mz, checkout = args[:3]
    jobs = int(args[args.index("--jobs") + 1]) if "--jobs" in args else 2
    fl = Path(checkout) / "Datasets/File_List"
    work = [(uz, "U", f) for f in pd.read_csv(fl / "TSB-AD-U-Eva.csv")["file_name"]]
    work += [(mz, "M", f) for f in pd.read_csv(fl / "TSB-AD-M-Eva.csv")["file_name"]]
    out = DATA / "bit_layers_tsbad.csv"
    done = set(pd.read_csv(out).file) if out.exists() else set()
    todo = [w for w in work if w[2] not in done]
    with Pool(jobs) as p:
        for i, r in enumerate(p.imap_unordered(tsbad_one, todo)):
            pd.DataFrame([r]).to_csv(out, mode="a", header=not out.exists(), index=False)
            print(f"[{len(done) + i + 1}/{len(work)}] {r['collection']} {r['file']}: noise share {r['noise_share']:.3f}",
                  flush=True)
    d = pd.read_csv(out).drop_duplicates("file")
    print(f"\n{len(d)} series (expected {len(work)})")
    for c in ("U", "M"):
        s = d[d.collection == c]
        m = s.noise_share.median()
        print(f"L1 TSB-AD-{c}-Eva: median noise share {m:.3f} over {len(s)} series (>= 0.50): "
              f"{'HOLDS' if m >= 0.5 else 'REFUTED'}")
    u = d[(d.collection == "U") & (d.channels_bound_held == 1)]
    lb, eb = 8 * u.lossless_B / u.n, 8 * u.structure_B / u.n
    iqr = lambda x: float(np.quantile(x, 0.75) - np.quantile(x, 0.25))  # noqa: E731
    print(f"L2 TSB-AD-U ({len(u)} series with sigma > 0 and bound held): IQR structure bits/sample {iqr(eb):.3f} "
          f"vs lossless {iqr(lb):.3f} (needs < half): {'HOLDS' if iqr(eb) < 0.5 * iqr(lb) else 'REFUTED'}")
    print(f"   medians: lossless {lb.median():.2f}, structure {eb.median():.2f} bits/sample")
    d["ds"] = d.file.str.split("_").str[1]
    print("\nPer dataset (median noise share, series):")
    print(d.groupby(["collection", "ds"]).noise_share.agg(["median", "size"]).round(3).to_string())


def gamma(x):
    return 2 * int(np.floor(np.log2(x))) + 1


def esa(args):
    specs = [(args[0], range(41, 47), "2006-10-01", "2007-01-01"), (args[1], range(18, 29), "2001-07-01", "2001-10-01")]
    rows = []
    for zp, chans, val, split in specs:
        z = zipfile.ZipFile(zp)
        root = next(n.split("/")[0] for n in z.namelist() if n.endswith("labels.csv"))
        lab = pd.read_csv(io.BytesIO(z.read(f"{root}/labels.csv")))
        lab["StartTime"] = pd.to_datetime(lab.StartTime).dt.tz_localize(None)
        lab["EndTime"] = pd.to_datetime(lab.EndTime).dt.tz_localize(None)
        series = {}
        for ch in chans:
            s = load(z, f"{root}/channels/channel_{ch}.zip")
            series[ch] = s[~s.index.duplicated(keep="last")].sort_index()
        n_test = sum(int((s.index >= pd.Timestamp(split)).sum()) for s in series.values())
        t = float(np.ceil(np.log2(n_test)))
        for ch, s in series.items():
            v = s.to_numpy(np.float64)
            idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
            sig = robust_sigma(v[idx < pd.Timestamp(val)])
            L, E, ok, cost = layers(v, sig)
            ev = lab[lab.Channel == f"channel_{ch}"].sort_values("StartTime")
            D, prev, k = 0, 0, 0
            for a, b in zip(ev.StartTime, ev.EndTime):
                i0 = int(np.searchsorted(idx, a))
                i1 = max(int(np.searchsorted(idx, b, side="right")) - 1, i0)
                D += gamma(max(i0 - prev, 0) + 1) + gamma(i1 - i0 + 1)
                prev, k = i1 + 1, k + 1
            D += gamma(k + 1)
            bw = max(1, int(to_codes(v).max()).bit_length())
            al = np.nonzero((idx >= pd.Timestamp(split)) & (cost >= bw + t))[0]
            alarm_B = sum(varint_len(int(x)) for x in np.diff(np.r_[0, al])) + varint_len(len(al))
            rows.append(dict(mission=root, channel=ch, samples=len(v), lossless_B=L, structure_B=E, bound_held=ok,
                             events=k, decision_bits=D, alarms=len(al), alarm_B=alarm_B))
            print(f"{root} ch{ch}: L {L:,} B, E {E:,} B, events {k}, D {D} bits, alarms {len(al)} ({alarm_B} B)",
                  flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "bit_layers_esa.csv", index=False)
    print()
    for m, g in d.groupby("mission"):
        L, E, D = g.lossless_B.sum(), g.structure_B.sum(), g.decision_bits.sum()
        r = D / (8 * L)
        print(f"{m}: lossless {L:,} B = noise {L - E:,} B ({100 * (1 - E / L):.1f}%) + structure {E:,} B; "
              f"decision {D:,} bits = {D / 8:,.0f} B; on-board alarms {g.alarm_B.sum()} B")
        print(f"  L3 D / lossless bits = {r:.3g} (< 1e-4): {'HOLDS' if r < 1e-4 else 'REFUTED'}")


if __name__ == "__main__":
    {"tsbad": tsbad, "esa": esa}[sys.argv[1]](sys.argv[2:])
