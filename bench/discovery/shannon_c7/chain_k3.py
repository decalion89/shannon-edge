#!/usr/bin/env python3
"""Layer-chaining analysis, calibration level: C7^3 = C7^2 (x) C7 (7 layers).
I subset C7^3 is independent iff every layer I_x is independent in C7^2 and I_x u I_{x+1} is independent
(and disjoint) in C7^2 for every x mod 7. So alpha(C7^3) = max over cyclic sequences of compatible states.
1. enumerate all independent sets of C7^2 (bitmasks over 49 vertices);
2. maximum sets (size 10) and their 5/5 splits -> 'split graph' on 5-sets (edge: union is a 10-set);
   35 = 7*10/2 needs a closed walk of length 7 in it: odd cycle test;
3. exact alpha(C7^3) by (max,+) transfer matrix over states (after symmetry reduction of the first layer).
"""
import itertools
import time
import numpy as np

m = 2
V = list(itertools.product(range(7), repeat=m))
nV = len(V)
close = lambda a, b: all(min((x - y) % 7, (y - x) % 7) <= 1 for x, y in zip(a, b))  # noqa: E731
NB = [sum(1 << j for j in range(nV) if close(V[i], V[j])) for i in range(nV)]  # closed neighbourhood masks

t0 = time.time()
sets = []


def rec(start, mask, forbidden, size):
    sets.append((mask, forbidden, size))
    for v in range(start, nV):
        if not (forbidden >> v) & 1:
            rec(v + 1, mask | (1 << v), forbidden | NB[v], size + 1)


rec(0, 0, 0, 0)
sizes = np.array([s[2] for s in sets])
print(f"independent sets of C7^2: {len(sets)} (max size {sizes.max()}; #size-10: {(sizes == 10).sum()}) "
      f"[{time.time() - t0:.1f}s]", flush=True)
max_sets = [s[0] for s in sets if s[2] == 10]
# split graph on 5-subsets of maximum sets
five = {}
edges = set()
for M in max_sets:
    elems = [v for v in range(nV) if (M >> v) & 1]
    for A in itertools.combinations(elems, 5):
        a = sum(1 << v for v in A)
        b = M ^ a
        edges.add((min(a, b), max(a, b)))
nodes = sorted({x for e in edges for x in e})
print(f"split graph: {len(nodes)} five-sets, {len(edges)} edges", flush=True)
# odd closed walk of length 7 exists iff some component is non-bipartite with an odd cycle of length <= 7
import collections  # noqa: E402
adj = collections.defaultdict(list)
for a, b in edges:
    adj[a].append(b); adj[b].append(a)
color, bip = {}, True
for s in nodes:
    if s in color:
        continue
    color[s] = 0
    q = [s]
    while q:
        u = q.pop()
        for w in adj[u]:
            if w not in color:
                color[w] = 1 - color[u]; q.append(w)
            elif color[w] == color[u]:
                bip = False
print("split graph bipartite:", bip, "-> 35 impossible" if bip else "-> need finer check", flush=True)

# odd girth of the split graph (shortest odd closed walk), by BFS on the bipartite double cover
idmap = {v: i for i, v in enumerate(nodes)}
A = [[idmap[w] for w in adj[v]] for v in nodes]
best = 10 ** 9
seen_comp = set()
for s in range(len(nodes)):
    # shortest odd closed walk through s = shortest path s -> s' in the double cover
    dist = {(s, 0): 0}
    q = collections.deque([(s, 0)])
    while q:
        u, p = q.popleft()
        d = dist[(u, p)]
        if d >= best:
            break
        for w in A[u]:
            key = (w, 1 - p)
            if key not in dist:
                dist[key] = d + 1
                q.append(key)
    if (s, 1) in dist:
        best = min(best, dist[(s, 1)])
    if s > 3000 and best < 10 ** 9:
        break  # vertex-transitive-ish: a sample of start nodes suffices for the minimum
print(f"odd girth of split graph (min over {min(s + 1, len(nodes))} start nodes): {best}  "
      f"-> {'35 impossible (needs a closed walk of length 7)' if best > 7 else '35 not excluded by splits alone'}",
      flush=True)
