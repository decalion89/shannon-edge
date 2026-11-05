import numpy as np
from scipy.optimize import minimize
rng=np.random.default_rng(3)
d=2
def proj_from(v):  # rank-1 projector from real params (complex vector)
    c=v[:d]+1j*v[d:]; c=c/np.linalg.norm(c); return np.outer(c,c.conj())
def val(params,N,psi_fixed=None):
    k=0; P=[]
    for party in range(3):
        L=[]
        for x in range(N):
            L.append(proj_from(params[k:k+2*d])); k+=2*d
        P.append(L)
    if psi_fixed is None:
        v=params[k:k+2*d**3]; psi=v[:d**3]+1j*v[d**3:]; psi/=np.linalg.norm(psi)
    else: psi=psi_fixed
    def p(x,y,z): 
        O=np.kron(np.kron(P[0][x],P[1][y]),P[2][z]); return np.real(psi.conj()@O@psi)
    S=sum(p(x,x,x) for x in range(N)); T=sum(p(x,y,z) for x in range(N) for y in range(N) for z in range(N))
    return S,T
best={}
for N in [2,3,4]:
    nparam=3*N*2*d+2*d**3; bv=-1e9
    for rep in range(30):
        x0=rng.normal(size=nparam)
        r=minimize(lambda q:-(val(q,N)[0]**3-val(q,N)[1]),x0,method='L-BFGS-B',options={'maxiter':400})
        S,T=val(r.x,N); bv=max(bv,S**3-T)
        if S**3-T>1e-6: print('VIOLATION',N,S,T)
    print(f"N={N} qubits: max S^3 - T3 found = {bv:.3e}")
