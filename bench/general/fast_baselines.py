"""Fast-baseline speed/size check: zstd -3 (default level) on raw, byte
planes and field-delta + planes, one thread, verified. Reuses baselines.py's
transforms by importing it would run it, so they are repeated here.
Usage: nice -n 10 python3 -I fast_baselines.py DATA.bin WORKDIR
"""
import hashlib, json, os, subprocess, sys, time
import numpy as np

path, work = sys.argv[1], sys.argv[2]
meta = json.load(open(path[:-4] + ".json")); L = meta["record_len"]
raw = open(path, "rb").read(); N = len(raw) // L
dt = np.dtype([(n, t) for n, t in meta["fields"]])
UINT = {1: np.uint8, 2: np.uint16, 4: np.uint32, 8: np.uint64}
SINT = {1: np.int8, 2: np.int16, 4: np.int32, 8: np.int64}
planes = lambda b: np.frombuffer(b, np.uint8).reshape(N, L).T.tobytes()

def fdelta(b):
    a = np.frombuffer(b, dt); o = np.empty(N, dt)
    for n in dt.names:
        ft = dt[n]; w = ft.itemsize; u = a[n].view(UINT[w]).astype(UINT[w]); d = u.copy()
        if ft.kind == "f":
            d[1:] = u[1:] ^ u[:-1]
        else:
            d[1:] = u[1:] - u[:-1]; s = d.view(SINT[w]); d = ((s << 1) ^ (s >> (8 * w - 1))).view(UINT[w])
        o[n] = d.view(ft)
    return o.tobytes()

name = os.path.basename(path)[:-4]
for tag, f in [("zstd3", lambda b: b), ("planes+zstd3", planes), ("fdelta+planes+zstd3", lambda b: planes(fdelta(b)))]:
    t = time.perf_counter(); data = f(raw); tt = time.perf_counter() - t
    src = os.path.join(work, name + ".f.in"); open(src, "wb").write(data)
    t = time.perf_counter()
    z = subprocess.run(["zstd", "-3", "--long=27", "-T1", "-q", "-c", src], stdout=subprocess.PIPE, check=True).stdout
    ct = time.perf_counter() - t
    back = subprocess.run(["zstd", "-d", "--long=27", "-q", "-c"], input=z, stdout=subprocess.PIPE, check=True).stdout
    assert hashlib.sha256(back).digest() == hashlib.sha256(data).digest()
    os.remove(src)
    print(f"{name} {tag}: {len(z)} bytes ({len(raw)/len(z):.3f}x), compress {len(raw)/(ct+tt)/1e6:.1f} MB/s incl. transform, verified")
