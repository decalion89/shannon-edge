#!/usr/bin/env python3
"""Why the direction (1,1,3)? Structure of the conflict graph INSIDE one plane <u,x> = c of C7^3 and BETWEEN
consecutive planes, for several u. For u = (1,1,3): x3 = 5(c - x1 - x2), so dx3 = 2(dx1 + dx2) mod 7 and only moves
with dx1 + dx2 = 0 conflict inside a plane -> the plane is 7 disjoint 7-cycles (alpha = 21)."""
import itertools
import networkx as nx
import numpy as np

V = list(itertools.product(range(7), repeat=3))
close = lambda a, b: all(min((x - y) % 7, (y - x) % 7) <= 1 for x, y in zip(a, b))  # noqa: E731
for u in [(1, 1, 3), (1, 2, 3), (1, 1, 1), (0, 1, 1), (0, 0, 1)]:
    planes = {c: [v for v in V if sum(a * b for a, b in zip(u, v)) % 7 == c] for c in range(7)}
    G = nx.Graph(); G.add_nodes_from(planes[0])
    G.add_edges_from((a, b) for a, b in itertools.combinations(planes[0], 2) if close(a, b))
    comps = sorted(len(c) for c in nx.connected_components(G))
    deg = sorted(set(dict(G.degree()).values()))
    # alpha of one plane (exact, small)
    from networkx.algorithms.clique import find_cliques
    H = nx.complement(G)
    a = max(len(c) for c in find_cliques(H)) if len(H) <= 60 else None
    cross = sum(1 for a_ in planes[0] for b in planes[1] if close(a_, b))
    print(f"u={u}: plane = {len(planes[0])} pts, in-plane degree {deg}, components {comps[:8]}{'...' if len(comps) > 8 else ''}, "
          f"alpha(plane)={a}, edges plane0-plane1 = {cross}")
