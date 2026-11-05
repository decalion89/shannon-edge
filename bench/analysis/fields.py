#!/usr/bin/env python3
"""Numeric fields in Venus Express packets: finds a partition of the 90
bytes into big- or little-endian fields of 1-4 bytes that minimises a crude
entropy estimate of the numeric deltas (dynamic programming, on the first
10% of the packets), and reports the estimate on the other 90%.
Usage: fields.py venus-express.ccsds"""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
n=len(P); split=n//10
def seg_values(k,w,be):
    cols=P[:,k:k+w]
    if not be: cols=cols[:,::-1]
    v=np.zeros(n,dtype=np.int64)
    for i in range(w): v=v*256+cols[:,i]
    return v
def cost(k,w,be,rng):
    v=seg_values(k,w,be); mod=1<<(8*w)
    d=(v[1:]-v[:-1])%mod; d=np.where(d>=mod//2,d-mod,d)       # signed numeric delta
    z=np.where(d>=0,2*d,-2*d-1)
    cls=np.zeros(len(z),dtype=np.int64); nz=z>0
    cls[nz]=np.floor(np.log2(z[nz])).astype(np.int64)+1      # 0 = no change
    prev=np.concatenate([[0],cls[:-1]])
    a,b=rng
    c,pc,cl=cls[a:b],prev[a:b],cls[a:b]
    nc=8*w+2
    joint=np.bincount(pc*nc+c,minlength=nc*nc).reshape(nc,nc).astype(float)
    tot=joint.sum(1,keepdims=True)
    p=np.where(joint>0,joint/np.maximum(tot,1),1)
    h=-(joint*np.log2(p)).sum()
    mant=np.maximum(cl-1,0).sum()
    return h+mant
H=(0,split-1); T=(split-1,n-1)
# DP partition on history
best=[0.0]+[None]*90; choice=[None]*91
for e in range(1,91):
    for w in (1,2,3,4):
        s=e-w
        if s<0: continue
        for be in ((True,) if w==1 else (True,False)):
            c=best[s]+cost(s,w,be,H)
            if best[e] is None or c<best[e]: best[e]=c; choice[e]=(s,w,be)
segs=[]; e=90
while e>0:
    s,w,be=choice[e]; segs.append((s,w,be)); e=s
segs=segs[::-1]
bytewise_T=sum(cost(k,1,True,T) for k in range(90))
fields_T=sum(cost(s,w,be,T) for s,w,be in segs)
bytewise_H=sum(cost(k,1,True,H) for k in range(90))
print(f"history: byte-wise {bytewise_H/8/(split-1):.2f} B/packet, fields {best[90]/8/(split-1):.2f}")
print(f"test:    byte-wise {bytewise_T/8/(n-split):.2f} B/packet, fields {fields_T/8/(n-split):.2f}  ({100*(fields_T/bytewise_T-1):+.1f}%)")
print("fields found:", [(s,w,'BE' if be else 'LE') for s,w,be in segs if w>1])
