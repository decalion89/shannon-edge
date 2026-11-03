# Atlas of one-bit zero-error communication tasks: preregistration

Written before any atlas computation was run (2026-11-03).

## Question

For small one-way communication tasks, where does the quantum boundary sit
relative to classical, almost-quantum and nonsignalling resources, and
where does it behave unusually? Each task is studied in isolation in the
literature; nobody has mapped the whole space of small tasks across theories.

## Task family (v0)

- Inputs s ∈ [N] (Alice), t ∈ [N] (Bob); Boolean function f: [N]×[N] → {0,1}.
- One bit M from Alice to Bob; a shared box (classical, quantum, AQ or
  nonsignalling); Bob outputs 0, 1 or abstains.
- Zero error: Bob never outputs 1 − f(s,t).
- Figure of merit: worst case over (s,t) of P(conclusive).
- WLOG (convexity and closure under local processing): Alice's setting is
  s and her binary outcome is M; Bob's setting is (t, M), outcomes {0,1,⊥}.
- All f for N = 3, reduced by row permutations, column permutations and
  output negation. N = 4 follows only if the N = 3 run passes the checks below.

## Quantities computed per task

1. Classical value: exact LP over mixtures of zero-error deterministic protocols.
2. Nonsignalling value: LP.
3. NPA level 1, level 1+AB (almost-quantum), level 2: SDP upper bounds
   (level 2 ⊇ quantum, so level 2 is an upper bound on the quantum value).

## Pre-registered anomaly definitions (tolerance 1e-4)

- **A1, quantum candidate:** level 2 > classical. Not a quantum advantage until
  a quantum strategy (see-saw lower bound) also beats classical.
- **A2, post-quantum window:** AQ > level 2.
- **A3, relativity gap:** NS > AQ (expected to be common; recorded only).
- **A4, clean value:** a value equals a rational with denominator ≤ 64 within
  1e-5 and differs from the classical value.

## Checks that must pass before anything is reported

- Equality (f = δ_st) at N = 3 must reproduce classical = quantum = 1/3
  (arXiv:2610.41448, N ≥ 3) and NS = 1.
- Ordering classical ≤ level 2 ≤ AQ ≤ level 1 ≤ NS for every task.
- Any A1 or A2 hit is re-solved with a second solver before it is listed.

## What would count as a finding

Only A1 hits confirmed by an explicit quantum strategy, or A2 hits robust to
both solvers, followed by a prior-art search. Everything else is mapping.
