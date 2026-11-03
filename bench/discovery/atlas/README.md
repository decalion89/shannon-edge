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

## N = 4 (partial: 68 of 173 classes, `atlas_N4_partial.jsonl`)

The run hit the 2-hour background limit and was not restarted. With pruning,
62 classes were skipped (classical = 1, or AQ = classical). In the 6 remaining
classes classical = level 2 = 1/4 and NS = 1.

- **A1 (quantum candidate): none.**
- **A2 candidate, not confirmed:** one class has AQ = 0.2523, while classical =
  level 2 = 0.25. The other five sit at 0.2502–0.2503, which is SCS precision.
  As preregistered, the 0.2523 class must be re-solved with a second solver
  before it is listed as a post-quantum window.

  **Second-solver check** for f = [[0,0,0,0],[0,0,1,1],[0,1,0,1],[1,1,1,0]]:
  AQ = 0.25284 (CLARABEL) and 0.25217 (SCS, eps 1e-10); the exact classical LP
  gives 0.25000. Both solvers put AQ above classical by about 0.002. The window
  counts as confirmed only once level 2 is also re-solved with CLARABEL (running).

  **Level 2 re-solved** with an independent explicit-matrix formulation (SCS, eps 1e-9):
  0.250000, status optimal. (CLARABEL cannot handle the 321 × 321 level-2 cone: it tries
  to allocate 21 GB.)
  **Verdict: A2 confirmed.** For this task, classical = quantum (level 2) = 1/4, while
  almost-quantum reaches 0.2522–0.2528, depending on the solver. This is a second
  post-quantum window, at only N = 4 inputs per side, for a function other than
  equality; in equality certification the AQ advantage only appears from N = 9.
  Next (`window_n4.py`): test whether the coincidence family (Σp)² ≤ Σp detects this
  window.

  **Does the coincidence family detect this window? (`window_n4.py`)** We searched
  locally over pair lists (with repetition) on the optimal AQ strategy. The SCS
  solution gave a "violation" of 4.4·10⁻⁵, from a list built only out of
  zero-error-forbidden outcomes (p = 0) with weights 7, 10, 10, 16. Re-solved with
  CLARABEL, those probabilities are 0 to 6 digits and S² − T = −6.6·10⁻⁴: the violation
  was numerical noise. **No genuine violation was found**, so the window is not
  explained by any family member that this search reached. Possible readings:
  - the search missed the violating list;
  - a different law separates quantum from almost-quantum here; this is the
    interesting case and should be checked by solving for the most violated
    weighted list exactly.

  Also noted: the AQ optimum itself is solver-sensitive (CLARABEL 0.25284; SCS
  0.25217 and 0.25256 across runs), always ≥ 0.002 above the quantum value 0.25.
