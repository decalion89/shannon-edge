#!/usr/bin/env python3
"""Size-profile integer program for alpha(C7^4).
C7^4 = C7^2 (x) C7^2: a 7x7 grid of layers L_xy (independent sets of C7^2), sizes c_xy. Valid constraints:
  - 2x2 blocks of layer indices (x,x+1)x(y,y+1): union independent in C7^2      -> sum <= 10
  - 2x1 blocks (x,x+1)x{y} and {x}x(y,y+1): subsets of 2x2 blocks (implied)
  - rows: {x} x C7 is a C7^3 set                                              -> sum <= 33
  - pairs of rows {x,x+1} x C7: union of two adjacent C7^3 layers               -> sum <= 33
  - same for columns
  - single layers: c_xy <= 10
Maximise sum c_xy exactly (HiGHS MILP). Usage: profile_ip.py
"""
import itertools
import numpy as np
from scipy.optimize import milp, LinearConstraint, Bounds

idx = lambda x, y: (x % 7) * 7 + (y % 7)  # noqa: E731
rows, ub = [], []


def add(cells, b):
    r = np.zeros(49)
    for c in cells:
        r[idx(*c)] = 1
    rows.append(r); ub.append(b)


for x, y in itertools.product(range(7), repeat=2):
    add([(x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)], 10)
for x in range(7):
    add([(x, y) for y in range(7)], 33)
    add([(y, x) for y in range(7)], 33)
    add([(x, y) for y in range(7)] + [(x + 1, y) for y in range(7)], 33)
    add([(y, x) for y in range(7)] + [(y, x + 1) for y in range(7)], 33)
for c in range(7):  # diagonals (x, x+c) and anti-diagonals (x, c-x): 7-cycles of layers -> C7^3 copies
    add([(x, x + c) for x in range(7)], 33)
    add([(x, c - x) for x in range(7)], 33)
A = np.array(rows)
lp = milp(c=-np.ones(49), constraints=LinearConstraint(A, -np.inf, ub), integrality=np.zeros(49),
          bounds=Bounds(0, 10))
ip = milp(c=-np.ones(49), constraints=LinearConstraint(A, -np.inf, ub), integrality=np.ones(49),
          bounds=Bounds(0, 10), options={"time_limit": 600})
print(f"size-profile LP bound: {-lp.fun:.3f}; integer bound: {-ip.fun:.0f}  (layer bound 115, known lower 108)")
c = np.round(ip.x).astype(int).reshape(7, 7)
print(c)
