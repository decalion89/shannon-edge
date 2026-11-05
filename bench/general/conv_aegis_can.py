"""AEGIS automotive CAN-bus example data (Zenodo 3267184, CC BY 4.0) -> 416-byte records.

Usage: python3 -I conv_aegis_can.py OUT.bin TRIP1.hdf TRIP2.hdf ...

Each trip file holds ~109 signals (decoded CAN signals, GPS, IMU "plugins",
math channels) logged by the data logger at a common 20 Hz rate, each as an
(N, 2) float32 array [value, time]. One record per 20-Hz tick:
  f32 time        the shared time column (checked identical for every
                  float32 signal of the trip; restarts at 0 for each trip)
  f32 AI/AI 1     the only 1-D signal
  f32 x 102       value column of every 2-D float32 signal, sorted by HDF5
                  path (CAN/..., GPS/..., Math/..., Plugins/...)
Exact float32 bits as stored in the HDF5 files (little-endian); nothing
quantized. Dropped: 6 float64 datasets (GPS/Current sec, GPS/Latitude,
GPS/Longitude, Plugins/Latitude2, Plugins/Longitude2, Plugins/Time) that
are entirely zero (value and time) in these trips (checked).
Trips with a different signal set (Driver1 trips 3-6 have 155 signals) are
not mixed in. Trips are concatenated in the order given.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import h5py
import numpy as np
from common import write

out, trips = sys.argv[1], sys.argv[2:]
ref = None
parts = []
for fn in trips:
    f = h5py.File(fn, "r")
    names = []
    f.visititems(lambda n, o: names.append(n) if isinstance(o, h5py.Dataset) else None)
    names.sort()
    f64 = [n for n in names if f[n].dtype == np.float64]
    for n in f64:
        assert not np.any(f[n][:]), n  # all zero -> dropped
    f32 = [n for n in names if f[n].dtype == np.float32 and f[n].ndim == 2]
    one_d = [n for n in names if f[n].ndim == 1]
    assert one_d == ["AI/AI 1"] and len(f32) + len(f64) + 1 == len(names)
    if ref is None:
        ref = (f32, f64)
    assert (f32, f64) == ref, fn
    t = f[f32[0]][:, 1]
    cols = [t, f["AI/AI 1"][:]]
    for n in f32:
        d = f[n][:]
        assert np.array_equal(d[:, 1].view(np.uint32), t.view(np.uint32)), n
        cols.append(d[:, 0])
    m = np.stack(cols, axis=1).astype("<f4")
    parts.append(m)
    print(os.path.basename(fn), m.shape)
fields = [["time_s", "<f4"], ["AI/AI 1", "<f4"]] + [[n, "<f4"] for n in ref[0]]
data = np.ascontiguousarray(np.concatenate(parts))
arr = data.view(np.dtype([(n, t) for n, t in fields])).reshape(-1)
write(
    out,
    arr,
    fields,
    "https://zenodo.org/records/3267184 (CC BY 4.0), trips " + ",".join(os.path.basename(t) for t in trips),
    "20-Hz logger records of decoded CAN + GPS/IMU signals of one passenger car; exact float32 bits.",
)
