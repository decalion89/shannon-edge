#!/usr/bin/env python3
"""Error-bounded ("near-lossless") preprocessing of Venus Express packets:
bytes 0-9 (header, sequence count, time) stay exact; every numeric field
(layout from bench/analysis/fields.py) is reconstructed within +-delta by a
closed-loop quantiser (as in JPEG-LS / CCSDS 123 near-lossless), with delta
a fraction k of the field's robust noise sigma estimated on the first 10% of
the packets. Each output file is then compressed losslessly by any sedge
codec, so the error bound holds exactly. Use --safe to keep the three fields
with implausibly large noise (bytes 33-44, possibly not integers) exact.
Usage: near_lossless.py venus-express.ccsds OUT_PREFIX [--safe] k ..."""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
out_prefix=sys.argv[2]; n=len(P); split=n//10
safe="--safe" in sys.argv
args_k=[a for a in sys.argv[3:] if a!="--safe"]
fields=[(10,2),(18,3),(22,3),(26,3),(30,3),(33,4),(37,4),(42,3),(58,3),(62,3),(66,3),(70,3),(74,3),(77,4),(81,4),(85,4)]
def vals(s,w):
    v=np.zeros(n,dtype=np.int64)
    for i in range(w): v=v*256+P[:,s+i]
    return v
sig={}
for s,w in fields:
    mod=1<<(8*w); v=vals(s,w)[:split]          # noise estimated on history only
    d=(v[1:]-v[:-1])%mod; d=np.where(d>=mod//2,d-mod,d)
    mad=np.median(np.abs(d-np.median(d)))
    sig[(s,w)]=1.4826*mad/np.sqrt(2)          # robust noise sigma (white-noise model)
print('robust noise sigma per field (LSB):', {f'{s}+{w}':round(x,1) for (s,w),x in sig.items()})
if safe:
    fields=[f for f in fields if f not in ((33,4),(37,4),(42,3))]
for k in [float(x) for x in args_k]:
    Q=P.copy(); worst_ratio=0.0
    for s,w in fields:
        delta=int(k*sig[(s,w)]); step=2*delta+1; mod=1<<(8*w); v=vals(s,w)
        r=np.empty(n,dtype=np.int64); r[0]=v[0]
        for t in range(1,n):
            d=(v[t]-r[t-1])%mod
            if d>=mod//2: d-=mod
            r[t]=(r[t-1]+int(np.round(d/step))*step)%mod
        e=(v-r)%mod; e=np.where(e>=mod//2,e-mod,e)
        assert np.abs(e).max()<=delta
        if sig[(s,w)]>0: worst_ratio=max(worst_ratio,np.abs(e).max()/sig[(s,w)])
        for i in range(w): Q[:,s+w-1-i]=(r>>(8*i))&255
    Q.astype(np.uint8).tofile(f'{out_prefix}{k}.bin')
    print(f'k={k}: every field within {k} x its noise sigma (worst {worst_ratio:.2f} sigma)', flush=True)
