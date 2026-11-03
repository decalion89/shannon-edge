#!/usr/bin/env python3
"""Does the noise-scale protocol generalise beyond spacecraft? (pre-registered in
bench/discovery/protocol_general_preregistration.md)

TSB-AD-M-Eva (180 multivariate series, 17 domains). Per channel, as in bench/discovery/protocol.py:
CCSDS 121 lossless on value codes (B1), CCSDS 121 on noise-scale lattice indices (B2), flight profile on
the lattice indices (P); sigma from the benchmark's normal prefix (tr_N); channels with sigma = 0, indices
over 16 bits or a failed bound go lossless. Alarms are not included (they are tens of bytes).

Usage: protocol_general.py TSB-AD-M.zip TSB-AD-checkout [--jobs 2]
"""

import io
import sys
import zipfile
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bit_layers import robust_sigma  # noqa: E402
from esa_edge_link import flight, to_codes  # noqa: E402
from protocol import bits, ccsds_size  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"


def one(job):
    zp, name = job
    z = zipfile.ZipFile(zp)
    root = next(n.split("/")[0] for n in z.namelist() if n.endswith(name))
    df = pd.read_csv(io.BytesIO(z.read(f"{root}/{name}"))).dropna()
    X = df.drop(columns=[c for c in df.columns if c.lower() == "label"]).to_numpy(np.float64)
    tr = int(name.split(".")[0].split("_")[-3])
    B1 = B2 = P = 0
    for j in range(X.shape[1]):
        v = X[:, j]
        codes = to_codes(v)
        b1 = ccsds_size(codes, bits(codes))
        L, _ = flight(codes)
        sig = robust_sigma(v[: max(tr, 2)])
        ok = False
        if sig > 0:
            k = np.round((v - v[0]) / (2 * sig)).astype(np.int64)
            li = k - k.min()
            ok = li.max() < 65536 and float(np.max(np.abs(v[0] + 2 * sig * k - v))) <= sig * (1 + 1e-9) + 1e-12
        if ok:
            li = li.astype("<u2")
            b2 = ccsds_size(li, bits(li))
            p, _ = flight(li)
        else:
            b2, p = b1, L
        B1, B2, P = B1 + b1, B2 + b2, P + p
    return dict(file=name, ds=name.split("_")[1], n=len(X), channels=X.shape[1], ccsds_lossless=B1,
                ccsds_noise_scale=B2, protocol=P)


def main():
    zp, checkout = sys.argv[1], sys.argv[2]
    jobs = int(sys.argv[sys.argv.index("--jobs") + 1]) if "--jobs" in sys.argv else 2
    files = pd.read_csv(Path(checkout) / "Datasets/File_List/TSB-AD-M-Eva.csv")["file_name"].tolist()
    out = DATA / "protocol_tsbad_m.csv"
    done = set(pd.read_csv(out).file) if out.exists() else set()
    todo = [(zp, f) for f in files if f not in done]
    with Pool(jobs) as p:
        for i, r in enumerate(p.imap_unordered(one, todo)):
            pd.DataFrame([r]).to_csv(out, mode="a", header=not out.exists(), index=False)
            print(f"[{len(done) + i + 1}/{len(files)}] {r['file']}: protocol/CCSDS {r['protocol'] / r['ccsds_lossless']:.3f}",
                  flush=True)
    d = pd.read_csv(out).drop_duplicates("file")
    r1 = d.protocol.sum() / d.ccsds_lossless.sum()
    r2 = d.protocol.sum() / d.ccsds_noise_scale.sum()
    d["r1"] = d.protocol / d.ccsds_lossless
    dsr = d.groupby("ds").apply(lambda g: g.protocol.sum() / g.ccsds_lossless.sum())
    share = float((dsr <= 0.5).mean())
    print(f"\n{len(d)} series, {d.ds.nunique()} domains")
    print(f"G1 pooled protocol / CCSDS 121 lossless = {r1:.3f} (needs <= 0.50): {'HOLDS' if r1 <= 0.5 else 'REFUTED'}")
    print(f"G2 pooled protocol / CCSDS 121 at noise scale = {r2:.3f} (needs <= 0.85): {'HOLDS' if r2 <= 0.85 else 'REFUTED'}")
    print(f"G3 domains where the protocol needs <= half of CCSDS 121: {share:.0%} of {len(dsr)} (needs >= 50%): "
          f"{'HOLDS' if share >= 0.5 else 'REFUTED'}")
    print(f"median per-series protocol / CCSDS 121 = {d.r1.median():.3f}")
    print(dsr.round(3).sort_values().to_string())


if __name__ == "__main__":
    main()
