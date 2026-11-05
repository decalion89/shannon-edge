#!/usr/bin/env python3
"""Ideal adaptive cost of the "same as above?" decisions on the last 90% of
Venus Express, with the fast profile's contexts and with "parent column
changed" added. Usage: flags.py venus-express.ccsds MI.npy"""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
D=(P[1:]-P[:-1])%256; n=len(D); split=n//10
S=(D==0).astype(np.int64)            # 1 = same
run=np.zeros_like(D); chl=np.zeros_like(D); r=np.zeros(90,dtype=np.int64); last=np.zeros(90,dtype=np.int64)
for t in range(n):
    run[t]=np.minimum(r,15); chl[t]=last
    r=np.where(S[t]==1,r+1,0); last=1-S[t]
lc=np.zeros_like(D); lc[:,1:]=1-S[:,:-1]
MI=np.load(sys.argv[2])
# parent for the flag: best earlier column by flag mutual information on history
def mi(a,b):
    j=np.bincount(a*2+b,minlength=4).reshape(2,2)/len(a)
    pa=j.sum(1,keepdims=True); pb=j.sum(0,keepdims=True)
    with np.errstate(divide='ignore',invalid='ignore'):
        return np.nansum(j*np.log2(j/(pa*pb)))
H=S[:split]
par=[0]+[int(np.argmax([mi(H[:,k],H[:,j]) for j in range(k)])) for k in range(1,90)]
pc=np.zeros_like(D)
for k in range(1,90): pc[:,k]=1-S[:,par[k]]
def flag_cost(ctx_list):
    tot=0.0
    for k in range(90):
        ctx=sum(c[:,k]*m for c,m in ctx_list)
        p=np.full(ctx.max()+1, 0.5)
        x=S[:,k]
        for t in range(n):
            c=ctx[t]; q=p[c] if x[t] else 1-p[c]
            if t>=split: tot+=-np.log2(max(q,1e-9))
            p[c]+= ((x[t])-p[c])/16
    return tot/8
cur=flag_cost([(run,4),(lc,2),(chl,1)])
withp=flag_cost([(run,8),(lc,4),(chl,2),(pc,1)])
print(f"flag cost on test: current contexts {cur:,.0f} bytes; + parent changed {withp:,.0f} bytes")
