"""PhysioNet INCART 12-lead ECG (incartdb 1.0.0, ODC-By 1.0) -> 24-byte frames.

Usage: python3 -I conv_ecg_incart.py DL_DIR OUT.bin I01 I02 ...

Format 16 in WFDB = int16 little-endian, channels interleaved, so each
.dat file already *is* a sequence of fixed-length frames: one frame per
sampling instant (257 Hz) with 12 leads x int16 (I, II, III, aVR, aVL, aVF,
V1..V6, in header order). We check the header (12 signals, all format 16,
one file, no byte offset) and the file length, then concatenate the
records unchanged: the output bytes are the native ADC samples.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from common import write

dl, out, recs = sys.argv[1], sys.argv[2], sys.argv[3:]
leads = None
parts = []
for r in recs:
    hea = open(os.path.join(dl, r + ".hea")).read().splitlines()
    name, nsig, fs, nsamp = hea[0].split()[:4]
    assert int(nsig) == 12 and int(fs) == 257, hea[0]
    sig = [l.split() for l in hea[1 : 1 + 12]]
    assert all(s[0] == r + ".dat" and s[1] == "16" for s in sig), sig
    names = [s[-1] for s in sig]
    leads = leads or names
    assert names == leads, (names, leads)
    raw = np.fromfile(os.path.join(dl, r + ".dat"), dtype="<i2")
    assert raw.size == int(nsamp) * 12, (raw.size, nsamp)
    parts.append(raw.reshape(-1, 12))
    print(r, nsamp, "samples")
fields = [[f"lead_{n}", "<i2"] for n in leads]
data = np.concatenate(parts)
arr = np.empty(data.shape[0], dtype=np.dtype([(n, t) for n, t in fields]))
for i, (n, _) in enumerate(fields):
    arr[n] = data[:, i]
assert arr.tobytes() == data.tobytes()  # byte-identical to the .dat files
write(
    out,
    arr,
    fields,
    "https://physionet.org/content/incartdb/1.0.0/ (ODC-By 1.0), records " + ",".join(recs),
    "Native WFDB format-16 frames, concatenated unchanged; 257 Hz, 12 leads int16 LE.",
)
