#!/usr/bin/env python3
"""Upper bound on what prior ("fleet") knowledge could save: the warm-up
excess of the flight profile, i.e. how many more bits it spends on a
channel's first 100,000 samples than at its steady rate (median of
100,000-sample windows). Usage: warmup.py ESA-MissionN.zip channel_12 ..."""
import io
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np
sys.path.insert(0, '/home/user/shannon-edge/bench')
from telemetry import SafeUnpickler
mission, chans = sys.argv[1], sys.argv[2:]
z = zipfile.ZipFile(mission); root = Path(mission).stem
def load(member):
    inner = zipfile.ZipFile(io.BytesIO(z.read(member)))
    return SafeUnpickler(io.BytesIO(inner.read(inner.namelist()[0]))).load().iloc[:, 0]
binary = '/home/user/shannon-edge/target/release/examples/flight_surprise'
print('channel | samples | total bits | first 1k: bits/sample | 1k-10k | 10k-100k | steady (median of 100k windows) | warm-up excess | excess share of total')
tot_ex = tot = 0.0
for ch in chans:
    s = load(f'{root}/channels/{ch}.zip')
    uniq, codes = np.unique(s.to_numpy().astype(np.float32), return_inverse=True)
    if len(uniq) > 65536: print(ch, 'skipped'); continue
    with tempfile.TemporaryDirectory() as t:
        cp, sp = Path(t)/'c.u16', Path(t)/'s.u32'
        codes.astype('<u2').tofile(cp)
        subprocess.run([binary, str(cp), str(sp)], check=True, capture_output=True)
        b = np.fromfile(sp, dtype='<u4').astype(np.float64) / 256.0
    w = 100_000
    rates = [b[i:i+w].mean() for i in range(0, len(b) - w + 1, w)]
    steady = float(np.median(rates))
    first = b[:100_000]
    excess = max(0.0, first.sum() - steady * len(first))
    tot_ex += excess; tot += b.sum()
    print(f'{ch} | {len(b):,} | {b.sum():,.0f} | {b[:1000].mean():.2f} | {b[1000:10000].mean():.2f} | {b[10000:100000].mean():.2f} | '
          f'{steady:.2f} | {excess/8:,.0f} B | {100*excess/b.sum():.3f}%', flush=True)
print(f'all: warm-up excess {tot_ex/8:,.0f} bytes of {tot/8:,.0f} ({100*tot_ex/tot:.3f}%)')
