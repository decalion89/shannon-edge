#!/usr/bin/env python3
"""Does the telecommand timeline explain telemetry surprise? For ESA-AD
Mission 1 channels, the flight profile's per-sample cost (bits) is
compared inside and outside windows of 60 s / 10 min / 1 h after any
telecommand execution. Both ends of a link know the commands (the ground
sent them, the spacecraft executed them), so excess cost there would be
compressible for free. Usage: cmd_effect.py ESA-Mission1.zip channel_12 ...
(needs `cargo build --release --example flight_surprise`)."""
import io
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, '/home/user/shannon-edge/bench')
from telemetry import SafeUnpickler
z = zipfile.ZipFile(sys.argv[1]); root = 'ESA-Mission1'
def load(member):
    inner = zipfile.ZipFile(io.BytesIO(z.read(member)))
    return SafeUnpickler(io.BytesIO(inner.read(inner.namelist()[0]))).load()
tcs = sorted((n for n in z.namelist() if re.search(r'/telecommands/telecommand_\d+\.zip$', n)))
times = []
for n in tcs:
    times.append(load(n).index.values)
cmd = np.unique(np.concatenate(times)).astype('datetime64[ns]').astype(np.int64)
print(f'{len(tcs)} telecommands, {len(cmd):,} distinct execution times', flush=True)
binary = '/home/user/shannon-edge/target/release/examples/flight_surprise'
win_s = [60, 600, 3600]
tot = {w: [0.0, 0, 0.0, 0] for w in win_s}   # bits in window, samples in window, bits all, samples all
for ch in sys.argv[2:]:
    s = load(f'{root}/channels/{ch}.zip').iloc[:, 0]
    uniq, codes = np.unique(s.to_numpy().astype(np.float32), return_inverse=True)
    if len(uniq) > 65536: print(ch, 'skipped'); continue
    with tempfile.TemporaryDirectory() as t:
        cp, sp = Path(t)/'c.u16', Path(t)/'s.u32'
        codes.astype('<u2').tofile(cp)
        subprocess.run([binary, str(cp), str(sp)], check=True, capture_output=True)
        bits = np.fromfile(sp, dtype='<u4').astype(np.float64) / 256.0
    ts = s.index.values.astype('datetime64[ns]').astype(np.int64)
    # time since the most recent command at or before each sample
    j = np.searchsorted(cmd, ts, side='right') - 1
    since = np.where(j >= 0, (ts - cmd[np.maximum(j, 0)]) / 1e9, np.inf)
    warm = len(bits) // 100
    b, sn = bits[warm:], since[warm:]
    row = [ch, f'{len(b):,}', f'{b.sum()/8:,.0f} B']
    for w in win_s:
        m = sn <= w
        tot[w][0] += b[m].sum(); tot[w][1] += m.sum(); tot[w][2] += b.sum(); tot[w][3] += len(b)
        row.append(f'{100*m.mean():.2f}% of samples carry {100*b[m].sum()/b.sum():.2f}% of bits')
    print(' | '.join(row), flush=True)
for w in win_s:
    bw, nw, ba, na = tot[w]
    print(f'within {w:>5}s after a command: {100*nw/na:.2f}% of samples, {100*bw/ba:.2f}% of bits '
          f'({bw/max(nw,1):.3f} vs {(ba-bw)/max(na-nw,1):.3f} bits/sample elsewhere)')
