#!/usr/bin/env python3
"""Cross-channel structure in Venus Express packets: for every column, the
other column whose delta class (in the same packet) best predicts it, by
empirical conditional entropy on the first 10% of the packets; reports
bits/packet on history and on the other 90%, and saves the mutual
information matrix. Usage: parents.py venus-express.ccsds MI_OUT.npy"""
import sys

import numpy as np
P=np.fromfile(sys.argv[1],dtype=np.uint8).reshape(-1,90).astype(np.int64)
D=(P[1:]-P[:-1])%256
n=len(D); split=n//10
def cls(d):
    s=np.where(d>127,d-256,d); a=np.abs(s)
    b=np.select([a==0,a==1,a<=3,a<=15],[0,1,2,3],4)
    return b*2+(s<0)
C=cls(D)
H=D[:split]; HC=C[:split]
def cond_entropy(x, ctx, nctx):
    # empirical H(x | ctx) in bits per sample, x in 0..255 (includes delta 0 = "same")
    joint=np.bincount(ctx*256+x, minlength=nctx*256).reshape(nctx,256).astype(float)
    tot=joint.sum(1,keepdims=True)
    p=np.where(joint>0, joint/np.maximum(tot,1), 1)
    return -(joint*np.log2(p)).sum()/len(x)
base=np.array([cond_entropy(H[:,k], np.zeros(len(H),dtype=np.int64),1) for k in range(90)])
left=np.array([cond_entropy(H[:,k], HC[:,k-1] if k>0 else np.zeros(len(H),dtype=np.int64),10) for k in range(90)])
best=np.zeros(90); par=np.zeros(90,dtype=int)
MI=np.zeros((90,90))
for k in range(90):
    for j in range(90):
        if j==k: continue
        h=cond_entropy(H[:,k], HC[:,j], 10)
        MI[k,j]=base[k]-h
    par[k]=np.argmax(MI[k]); best[k]=base[k]-MI[k,par[k]]
print(f"history (first 10%), bits/packet: no context {base.sum():.1f}, left neighbour {left.sum():.1f}, best other column (any) {best.sum():.1f}")
# test part: same estimates fixed from history? report empirical on test with chosen parents (static, optimistic)
T=D[split:]; TC=C[split:]
tb=sum(cond_entropy(T[:,k],np.zeros(len(T),dtype=np.int64),1) for k in range(90))
tl=sum(cond_entropy(T[:,k],TC[:,k-1] if k>0 else np.zeros(len(T),dtype=np.int64),10) for k in range(90))
tp=sum(cond_entropy(T[:,k],TC[:,par[k]],10) for k in range(90))
print(f"test (90%), parents chosen on history, bits/packet: none {tb:.1f}, left {tl:.1f}, chosen parent {tp:.1f}")
print("parents far from left neighbour:", sum(1 for k in range(90) if abs(par[k]-k)>1), "of 90")
np.save(sys.argv[2], MI)
