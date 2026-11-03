# Real (great-circle) qubit model, Bloch angles: overlap |<u|v>|^2 = cos^2((u-v)/2). rho pure at angle 0.
import numpy as np, mpmath
from scipy.optimize import minimize
c2=lambda t: np.cos(t/2)**2
def ratio(p):
    a1,a2,b1,b2=p
    w=[c2(a1),c2(a2)]; a=[a1,a2]; b=[b1,b2]
    S=sum(w[x]*c2(a[x]-b[x]) for x in range(2)); T=sum(w[x]*c2(a[x]-b[y]) for x in range(2) for y in range(2))
    return S*S/T
best=None
rng=np.random.default_rng(1)
for _ in range(300):
    r=minimize(lambda p:-ratio(p),rng.uniform(-np.pi,np.pi,4),method='BFGS',options={'gtol':1e-14})
    if best is None or r.fun<best.fun: best=r
print(-best.fun, np.mod(best.x+np.pi,2*np.pi)-np.pi)
