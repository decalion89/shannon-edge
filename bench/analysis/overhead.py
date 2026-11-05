#!/usr/bin/env python3
"""Decompose the cost of loss protection for compressed packets: for packet
loss p and erasure-code group size G, the parity needed for a target of
< 0.1 unrecoverable groups over the stream (binomial tail), and the
resulting overhead with Reed-Solomon parity padded to the longest payload
(as in shannon_edge::fec), with parity the size of a mean payload, and the
ideal m/G. Usage: overhead.py PAYLOAD_SIZES.txt (from SEDGE_SIZES_OUT)"""
import sys

import numpy as np
from math import comb
sizes=np.loadtxt(sys.argv[1]).astype(int); N=len(sizes); total=sizes.sum()
from math import lgamma, log, exp
def fail(G,m,p):
    n=G+m   # binomial tail P(X>m), X~Bin(n,p), summed in log space
    lt=lambda k: lgamma(n+1)-lgamma(k+1)-lgamma(n-k+1)+k*log(p)+(n-k)*log(1-p)
    return sum(exp(lt(k)) for k in range(m+1, min(n, m+200)+1))
for p in (0.001,0.01,0.05):
    print(f"\n=== packet loss {p:.1%}: asymptotic minimum overhead p/(1-p) = {100*p/(1-p):.2f}% ===")
    print("G | m | groups failing (expected) | parity overhead: padded RS (ours) | if parity = mean payload | m/G (no padding, ideal symbols)")
    for G in (16,32,64,128,256,1024,4096):
        groups=N/G
        m=0
        while fail(G,m,p)*groups>0.1: m+=1
        padded=sum(m*(2+max(sizes[i:i+G])) for i in range(0,N,G))
        mean_par=m*(2+sizes.mean())*groups
        print(f"{G} | {m} | {fail(G,m,p)*groups:.3f} | {100*padded/total:.1f}% | {100*mean_par/total:.1f}% | {100*m/G:.1f}%")
