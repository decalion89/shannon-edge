# Shannon capacity of C7: a first computational probe

State of the art (checked 2026-11-03):
- Best published lower bound: α(C7^⊠5) ≥ 367, so Θ(C7) ≥ 367^{1/5} > 3.2578
  (Polak–Schrijver 2018, arXiv:1808.07438; computer search via the circular
  graph C_{108,382}).
- Preprint arXiv:2607.21517 (2026, unverified here): α(C7^⊠10) ≥ 134753, so
  Θ(C7) > 3.258020. It was found through iterative interaction with an LLM.
- Upper bound: Lovász ϑ(C7) < 3.3177. The exact value has been open since 1956.

Probe (`cyclic_search.py`): cyclic sets {t·(1, a, …, a^{m−1}) mod n} that map
losslessly to C7 through φ(x) = ⌊7x/n⌋, with required circular distance
k = ⌈2n/7⌉.

| m | largest n found | known α(C7^m) (lower bound) |
|---|---|---|
| 2 | 10 | 10 (exact) |
| 3 | 31 | 33 |
| 4 | 94 | 108 |
| 5 | 299 (none in 300–400) | 367 |

Verdict: this lossless power-generator family is clearly weaker than the
known constructions, which use circular graphs with n/k slightly above 7/2 plus
a computer repair step. Beating the record needs those more general
constructions; an AI-assisted team is already working on them.
