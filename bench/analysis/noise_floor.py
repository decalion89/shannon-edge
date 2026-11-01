#!/usr/bin/env python3
"""Noise diagnostics for the numeric fields of Venus Express packets: lag-1
autocorrelation of the first differences, a variance-based noise estimate
(invalid as a bound for heavy-tailed data; see side_information.md) and the
entropy of each field's first difference. Usage: noise_floor.py venus-express.ccsds"""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
n=len(P)
fields=[(2,2),(7,3),(10,2),(18,3),(22,3),(26,3),(30,3),(33,4),(37,4),(42,3),(58,3),(62,3),(66,3),(70,3),(74,3),(77,4),(81,4),(85,4)]
covered=set(k for s,w in fields for k in range(s,s+w))
singles=[(k,1) for k in range(90) if k not in covered]
tot_floor=0.0; rows=[]
for s,w in fields+singles:
    v=np.zeros(n,dtype=np.int64)
    for i in range(w): v=v*256+P[:,s+i]
    mod=1<<(8*w)
    d=(v[1:]-v[:-1])%mod; d=np.where(d>=mod//2,d-mod,d).astype(np.float64)
    if d.std()==0: continue
    r1=np.corrcoef(d[1:],d[:-1])[0,1]
    # white-noise variance from the lag-1 autocovariance of the differences
    cov1=np.mean((d[1:]-d.mean())*(d[:-1]-d.mean()))
    sig2=max(-cov1,0.0)
    # empirical entropy of the first difference (an upper bound for a model using only the previous value)
    vals,counts=np.unique(d,return_counts=True); p=counts/counts.sum()
    hd=-(p*np.log2(p)).sum()
    # Gaussian noise entropy (bits/sample) of the measurement noise, if it exceeds one LSB
    hn=0.5*np.log2(2*np.pi*np.e*sig2) if sig2>0.25 else 0.0
    floor=max(hn,0.0)
    tot_floor+=floor
    rows.append((s,w,r1,np.sqrt(sig2),hd,floor))
rows.sort(key=lambda r:-r[5])
print("field(start,len) | lag-1 autocorr of diffs | noise sigma (LSB) | H(first diff) bits | noise floor bits/pkt")
for s,w,r1,sg,hd,fl in rows[:14]:
    print(f"({s},{w}) | {r1:+.2f} | {sg:,.1f} | {hd:.2f} | {fl:.2f}")
print(f"sum of white-noise floors: {tot_floor:.1f} bits/packet = {tot_floor/8*n:,.0f} bytes for the file")
