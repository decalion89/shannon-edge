# Atlas of one-bit zero-error tasks: results

See `PREREGISTRATION.md` for the protocol and the anomaly definitions.

## N = 3 (all 18 classes, `atlas_N3.jsonl`)

All pre-registered checks pass. Equality gives classical = AQ = level 2 = 1/3
and NS = 1, and the ordering classical ≤ L2 ≤ AQ ≤ L1 ≤ NS holds for every class.

| Classical value | Classes | Level 2 | AQ | Level 1 | NS |
|---|---|---|---|---|---|
| 1 | 11 | 1 | 1 | 1 | 1 |
| 1/2 | 5 | 1/2 | 1/2 | 0.61922 | 1 |
| 1/3 | 2 (equality and inequality) | 1/3 | 1/3 | 9/17 | 1 |

- **A1 (quantum candidate): none.** For every task with three inputs per side,
  one bit and zero error, the level-2 bound equals the classical value, so
  entanglement gives no advantage.
- **A2 (post-quantum window): none.** Almost-quantum correlations equal
  classical for every class at N = 3.
- **A3:** in every non-trivial class, nonsignalling boxes make the task perfect (value 1).
- Level 1 is strictly looser: 9/17 for equality and 0.61922 for the 1/2 class.

N = 4 (173 classes) is running with pruning.
