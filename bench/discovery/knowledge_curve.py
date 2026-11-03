#!/usr/bin/env python3
"""How many bits does the link need as the shared model accumulates knowledge? (ESA-AD Mission 1)

Per channel, the flight profile's cost per sample is measured three ways:
* A, memory:    one session over the whole mission (the model shared by spacecraft and ground
                keeps learning; examples/flight_surprise);
* B, amnesia:   a fresh model every day (examples/flight_reference_surprise with TRAIN = 0 and
                BLOCK = samples per day): what a receiver with no accumulated knowledge pays;
* C, stronger:  the general sedge model (examples/byte_costs, 16-bit little-endian samples) on one
                month, an upper bound on what a better shared model could still save there.

Output per channel: bits/sample per year for A and B, and the month comparison A vs C.
Descriptive measurement, not a hypothesis test.

Usage: knowledge_curve.py ESA-Mission1.zip CHANNEL...
"""

import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from anomaly_esaadb import load  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
EX = ROOT / "target/release/examples"


def run(args):
    subprocess.run([str(a) for a in args], check=True, capture_output=True)


def main():
    z = zipfile.ZipFile(sys.argv[1])
    rows = []
    for ch in sys.argv[2:]:
        s = load(z, f"ESA-Mission1/channels/channel_{ch}.zip")
        s = s[~s.index.duplicated(keep="last")].sort_index()
        _, codes = np.unique(s.to_numpy().astype(np.float32), return_inverse=True)
        if codes.max() >= 65536:
            codes = codes.astype(np.int64) * 65536 // (codes.max() + 1)
        codes = codes.astype("<u2")
        t = s.index
        per_day = max(1, int(round(len(codes) / ((t[-1] - t[0]).total_seconds() / 86400))))
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            codes.tofile(d / "c.u16")
            run([EX / "flight_surprise", d / "c.u16", d / "a.u32", 14])
            run([EX / "flight_reference_surprise", d / "c.u16", d / "b.u32", 0, per_day, 14])
            a = np.fromfile(d / "a.u32", "<u4") / 256.0
            b = np.fromfile(d / "b.u32", "<u4") / 256.0
            # C: one month in the middle of the mission, general model on 16-bit samples.
            mid = len(codes) // 2
            m = slice(mid, mid + 30 * per_day)
            codes[m].tofile(d / "m.bin")
            run([EX / "byte_costs", d / "m.bin", d / "m.f32", 22, 2])
            cm = np.fromfile(d / "m.f32", "<f4").astype(float).reshape(-1, 2).sum(axis=1)
        yr = t.year
        for y in sorted(set(yr)):
            k = yr == y
            rows.append((ch, y, a[k].mean(), b[k].mean()))
        print(f"channel {ch}: {len(codes):,} samples, {per_day} per day; month in mid-mission: "
              f"A {a[m].mean():.3f} bits/sample, C (general model) {cm.mean():.3f}, "
              f"B {b[m].mean():.3f}", flush=True)
    df = pd.DataFrame(rows, columns=["channel", "year", "A_memory", "B_amnesia"])
    piv = df.groupby("year")[["A_memory", "B_amnesia"]].mean()
    piv["saving_%"] = 100 * (1 - piv.A_memory / piv.B_amnesia)
    print("\nMean over channels, bits/sample per year:")
    print(piv.round(3).to_string())
    df.to_csv(ROOT / "bench/results/data/knowledge_curve_m1.csv", index=False)


if __name__ == "__main__":
    main()
