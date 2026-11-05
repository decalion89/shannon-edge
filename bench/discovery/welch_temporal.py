# Temporal (sequential) version: one system, measurement A_x at time 1 (Lueders), then B_y at time 2.
# p(0,0|x,y) = tr(B_y A_x rho A_x).  Classical (macrorealist) strategies obey S^2 <= T. Does quantum?
import numpy as np
from scipy.optimize import minimize
rng=np.random.default_rng(5)
def unit(v,d): c=v[:d]+1j*v[d:]; return c/np.linalg.norm(c)
def run(N,d,rank1=True):
    def unpack(q):
        k=0; A=[];B=[]
        for L in (A,B):
            for x in range(N):
                c=unit(q[k:k+2*d],d); k+=2*d; L.append(np.outer(c,c.conj()))
        c=unit(q[k:k+2*d],d); rho=np.outer(c,c.conj()); return A,B,rho
    def ST(q):
        A,B,rho=unpack(q)
        P=np.array([[np.real(np.trace(B[y]@A[x]@rho@A[x])) for y in range(N)] for x in range(N)])
        return np.trace(P),P.sum()
    best=-1e9;arg=None
    for rep in range(40):
        q0=rng.normal(size=(2*N+1)*2*d)
        r=minimize(lambda q:-(ST(q)[0]**2-ST(q)[1]),q0,method='L-BFGS-B',options={'maxiter':500})
        S,T=ST(r.x)
        if S*S-T>best: best=S*S-T;arg=(S,T)
    return best,arg
for N,d in [(2,2),(3,2),(3,3),(4,2),(4,3)]:
    b,(S,T)=run(N,d); print(f"temporal N={N} d={d}: max S^2-T = {b:.5f} (S={S:.4f}, T={T:.4f})",flush=True)
