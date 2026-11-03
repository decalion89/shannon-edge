#!/usr/bin/env python3
"""Noise-scale telemetry protocol vs the CCSDS 121 standard (pre-registered in
bench/discovery/protocol_preregistration.md).

Per channel, whole mission:
  B1  CCSDS 121 (libaec, unit-delay preprocessor, 256-sample packets) on the lossless value codes
  B2  CCSDS 121 on the noise-scale lattice indices (standard coder, same quantisation as the protocol)
  P   flight profile on the lattice indices
  A   Kraft alarms computed on the exact data (sent losslessly, added to B2 and P)
Lattice: k = round((v - v0) / 2 delta), delta = robust sigma of the training part; channels whose indices
need more than 16 bits, or where the bound fails, are sent lossless (B2 = B1, P = flight lossless).

Usage: protocol.py ESA-Mission1.zip ESA-Mission2.zip
"""

import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from anomaly_esaadb import load  # noqa: E402
from bit_layers import robust_sigma  # noqa: E402
from esa_edge_link import flight, to_codes, varint_len  # noqa: E402
import imagecodecs  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "results" / "data"
SPECS = [("ESA-Mission1", range(41, 47), "2006-10-01", "2007-01-01"),
         ("ESA-Mission2", range(18, 29), "2001-07-01", "2001-10-01")]


PACKET = 256


def bits(x):
    return max(1, int(x.max()).bit_length())


def ccsds_size(codes, b):
    """CCSDS 121 (libaec) in 256-sample packets with the right sample width: 1 byte for b <= 8, else 2.
    (A first version passed 2-byte samples with b <= 8, which libaec reads as twice as many 1-byte
    samples and inflates the size; found from implausible per-channel output before the verdict.)"""
    arr = codes.astype("<u1") if b <= 8 else codes.astype("<u2")
    w = arr.itemsize
    flags = imagecodecs.AEC.FLAG.DATA_PREPROCESS
    total, n = 0, len(arr) // PACKET * PACKET
    for i in range(0, n, PACKET):
        p = arr[i:i + PACKET].tobytes()
        c = imagecodecs.aec_encode(p, bitspersample=b, flags=flags, blocksize=16, rsi=128)
        back = imagecodecs.aec_decode(c, bitspersample=b, flags=flags, blocksize=16, rsi=128, out=PACKET * w)
        assert bytes(back) == p, "CCSDS round trip"
        total += len(c)
    return total + (len(arr) - n) * w


def main():
    rows = []
    for zp, (name, chans, val, split) in zip(sys.argv[1:3], SPECS):
        z = zipfile.ZipFile(zp)
        series = {}
        for ch in chans:
            s = load(z, f"{name}/channels/channel_{ch}.zip")
            series[ch] = s[~s.index.duplicated(keep="last")].sort_index()
        n_test = sum(int((s.index >= pd.Timestamp(split)).sum()) for s in series.values())
        t = float(np.ceil(np.log2(n_test)))
        for ch, s in series.items():
            v = s.to_numpy(np.float64)
            idx = s.index.tz_localize(None) if s.index.tz is not None else s.index
            codes = to_codes(v)
            b = bits(codes)
            B1 = ccsds_size(codes, b)
            L, cost = flight(codes)
            al = np.nonzero((idx >= pd.Timestamp(split)) & (cost >= b + t))[0]
            A = sum(varint_len(int(x)) for x in np.diff(np.r_[0, al])) + varint_len(len(al))
            sig = robust_sigma(v[idx < pd.Timestamp(val)])
            ok = False
            if sig > 0:
                k = np.round((v - v[0]) / (2 * sig)).astype(np.int64)
                li = k - k.min()
                err = float(np.max(np.abs(v[0] + 2 * sig * k - v)))
                ok = li.max() < 65536 and err <= sig * (1 + 1e-9) + 1e-12
            if ok:
                li = li.astype("<u2")
                B2 = ccsds_size(li, bits(li))
                Pb, _ = flight(li)
            else:
                B2, Pb = B1, L
            rows.append(dict(mission=name, channel=ch, samples=len(v), ccsds_lossless=B1, flight_lossless=L,
                             ccsds_noise_scale=B2, protocol=Pb, alarm_B=A, bounded=ok, delta=sig))
            print(f"{name} ch{ch}: CCSDS121 lossless {B1:,}  flight lossless {L:,}  CCSDS121 noise-scale {B2:,}  "
                  f"protocol {Pb:,} + alarms {A}  (bounded: {ok})", flush=True)
    d = pd.DataFrame(rows)
    d.to_csv(DATA / "protocol_esa.csv", index=False)
    print()
    ok1 = ok2 = True
    for m, g in d.groupby("mission"):
        B1, L, B2, P, A = (g[c].sum() for c in ("ccsds_lossless", "flight_lossless", "ccsds_noise_scale", "protocol",
                                                 "alarm_B"))
        r1, r2 = (P + A) / B1, (P + A) / (B2 + A)
        ok1 &= r1 <= 0.5
        ok2 &= r2 <= 0.85
        print(f"{m}: CCSDS 121 lossless {B1:,} B | flight lossless {L:,} B ({100 * (L / B1 - 1):+.1f}%) | "
              f"CCSDS 121 at noise scale + alarms {B2 + A:,} B | protocol {P + A:,} B")
        print(f"  protocol / CCSDS 121 lossless = {r1:.3f} (P1 needs <= 0.50); "
              f"protocol / CCSDS 121 at noise scale = {r2:.3f} (P2 needs <= 0.85)")
    print(f"P1 (at most half of today's standard, both missions): {'HOLDS' if ok1 else 'REFUTED'}")
    print(f"P2 (>= 15% below the standard coder on the same noise-scale data, both missions): "
          f"{'HOLDS' if ok2 else 'REFUTED'}")


if __name__ == "__main__":
    main()
