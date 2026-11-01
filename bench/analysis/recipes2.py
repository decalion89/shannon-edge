#!/usr/bin/env python3
"""Ideal adaptive cost of changed bytes on the last 90% of Venus Express,
with per-column context recipes chosen on the first 10%, with and without
"parent column delta" recipes (parent = earlier column with the highest
mutual information). Usage: recipes2.py venus-express.ccsds MI.npy"""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
n=len(P); split=n//10
D=(P[1:]-P[:-1])%256; A=P[:-1]; ch=D!=0
def bucket(d):
    s=np.where(d>127,d-256,d); a=np.abs(s)
    return np.select([a==0,a==1,a<=3,a<=15],[0,1,2,3],4)*2+(s<0)
C=bucket(D)
leftD=np.zeros_like(D); leftD[:,1:]=D[:,:-1]
lastD=np.zeros_like(D); cur=np.zeros(90,dtype=np.int64)
for t in range(len(D)):
    lastD[t]=cur; cur=np.where(D[t]!=0,D[t],cur)
MI=np.load(sys.argv[2])
par=[None]+[int(np.argmax(MI[k,:k])) for k in range(1,90)]  # best earlier column (history MI)
def ctx_parent(k): return C[:,par[k]] if par[k] is not None else np.zeros(len(D),dtype=np.int64)
base={
 'left_changed': lambda k:(leftD[:,k]!=0).astype(np.int64),
 'left_delta': lambda k:bucket(leftD[:,k]),
 'last_delta': lambda k:bucket(lastD[:,k]),
 'above>>4': lambda k:A[:,k]>>4,
 'lc+last': lambda k:(leftD[:,k]!=0)*10+bucket(lastD[:,k]),
}
withp=dict(base); withp['parent_delta']=ctx_parent; withp['parent+last']=lambda k:ctx_parent(k)*10+bucket(lastD[:,k])
def cost(ctx,k,decay=0.999):
    rows=np.nonzero(ch[:,k])[0]; tables={}; tr=te=0.0
    for t in rows:
        c=int(ctx[t]); d=int(D[t,k]); f=tables.get(c)
        if f is None: f=np.full(256,0.05); f[0]=0; tables[c]=f
        b=-np.log2(f[d]/f.sum())
        if t+1<split: tr+=b
        else: te+=b
        f*=decay; f[d]+=1
    return tr,te
for name,rec in (('current recipes',base),('+ parent recipes',withp)):
    tot=0.0
    for k in range(90):
        if not ch[:,k].any(): continue
        res={nm:cost(f(k),k) for nm,f in rec.items()}
        pick=min(res,key=lambda nm:res[nm][0]); tot+=res[pick][1]
    print(f"{name}: changed-byte cost on test {tot/8:,.0f} bytes")
