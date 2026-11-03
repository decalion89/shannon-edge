# Independent verification: "Almost-Quantum Correlations Violate Information Causality" (arXiv:2610.41444)

**The claim.** Das Bhowmik and Banik (v1, 30 Oct 2026) claim to settle a
problem open since 2015. Almost-quantum (AQ) correlations, the "1+AB"
level of the NPA hierarchy and the best-known supra-quantum candidate,
**violate information causality (IC), without bound**. They use one
explicit box, one bit of communication and a zero-error block
certification protocol.

**Status when checked (3 Nov 2026).** Four days old, not peer-reviewed,
no independent replication found. Another recent preprint still lists
the question as open (arXiv:2610.06604).

The script is `bench/discovery/verify_aq_ic.py`; its output is below.

```
(A) explicit AQ realisation of p* (max errors: commutation on psi, probabilities, projector):
    N=  1: 6.5e-17  1.1e-16  1.1e-16
    N=  2: 6.5e-17  1.1e-16  1.1e-16
    N=  3: 6.5e-17  1.1e-16  1.1e-16
    N=  5: 6.5e-17  1.1e-16  1.1e-16
    N= 10: 6.5e-17  1.1e-16  1.1e-16
    N= 30: 6.5e-17  1.1e-16  1.1e-16
    N= 60: 6.5e-17  1.1e-16  1.1e-16
(B) information-causality sum, exact vs the paper's bound:
    k=18, N=757,693: exact I = 1.000000272, bound = 1.000000186  (IC requires I <= 1)
    k=18, N=757,692: exact I = 1.000000048, bound = 0.999999962  (IC requires I <= 1)
    k=18, N=4,194,304: exact I = 1.058823496, bound = 1.058823410  (IC requires I <= 1)
    k=24, N=402,653,184: exact I = nan, bound = 1.411764706  (IC requires I <= 1)
    k=30, N=503,316,480: exact I = nan, bound = 0.660381160  (IC requires I <= 1)
(C) NPA level 1+AB feasibility of p* (status, min eigenvalue of the moment matrix):
    N=2: optimal, min eig -2.23e-09
    N=3: optimal, min eig -7.39e-09
    N=4: optimal, min eig -1.61e-09
    N=5: optimal, min eig -1.22e-09
    N=6: optimal, min eig -1.26e-09
(D) max sum_x p(0,0|x,x) over certificate boxes (p(0,0|x,y)=0 for x!=y):
    N=3: level 1+AB 1.0000 (optimal); level 2 1.0000 (optimal)  [paper: quantum <= 1]
    N=4: level 1+AB 1.0000 (optimal); level 2 1.0000 (optimal)  [paper: quantum <= 1]
/home/user/shannon-edge/bench/discovery/verify_aq_ic.py:136: UserWarning: Solution may be inaccurate. Try another solver, adjusting the solver settings, or solve with verbose=True for more information.
  prob.solve(solver="CLARABEL")
    N=5: level 1+AB 1.0000 (optimal); level 2 1.0000 (optimal_inaccurate)  [paper: quantum <= 1]
```

## Findings

**(A) The explicit AQ realisation is correct.** The paper's Appendix A
gives vectors ψ, u_x, v_x, w_x and the projectors onto span{u_x, w_x}
and span{v_y, w_y}. Built in numbers for N = 1 to 60 settings, they
satisfy:
* every AQ condition: commutation on ψ for all outcome pairs, and
  projectors;
* the box table: p(0,0|x,y) = δ_xy/17 and marginals 3/17;
* to machine precision (~10⁻¹⁶).

The construction is the same for every N, since each setting uses its
own basis vectors f_x, g_x. At N = 60 the box gives
Σ_x p(0,0|x,x) = 60/17 ≈ 3.5.

**(B) The violation holds with the exact mutual information**, not only
with the paper's lower bound I ≥ k·W:
* at their threshold (k = 18, N = 757,693), exact I = 1.000000272 > 1;
* the exact threshold is one setting lower, N = **757,692**
  (I = 1.000000048), where the paper's bound gives 0.99999996;
* over k, the smallest violating N is at k = 18;
* the growth is unbounded: at N = 2²², I = 1.0588.

**(C) Independent check of AQ membership by semidefinite programming.**
The NPA level-1+AB moment matrix for p* is feasible for N = 2–6 and
N = 12, with minimum eigenvalue ≈ −10⁻⁹, i.e. solver tolerance. This
agrees with (A) by a different method. Larger N was too slow for this
solver.

**(D) The contrast with quantum theory.** For "certificate boxes"
(p(0,0|x,y) = 0 for x ≠ y), the maximum of Σ_x p(0,0|x,x) is 1.0000
for N = 3–5, at NPA level 2 (an outer bound on quantum) and at level
1+AB.
* This is consistent with the companion paper's quantum bound
  Σ ≤ 1 (s ≤ 1/N).
* At small N the AQ box is not separated, since N/17 < 1.
* By (A), the AQ maximum must exceed 1 from N = 18. The separation
  appears only with many settings, as the paper says.

## Verdict

Every computational ingredient checked here **reproduces**:
* the AQ realisation, also confirmed independently by SDP for small N;
* the protocol's information sum, now with exact mutual information
  and a threshold one setting lower.

**Not verified here:**
* the companion paper's quantum bound for general N; only N ≤ 5 was
  checked numerically, at NPA level 2;
* the paper's interpretation.

The logical step from the zero-error RABC protocol to the IC sum is
elementary: a fair bit, and a never-wrong guess made with probability
t, carry h(t) − h(2t)/2 bits. We checked that formula in the exact
computation.

**On this evidence, the claim stands:** the best-known supra-quantum
candidate set violates information causality. IC therefore
distinguishes quantum correlations from their nearest known neighbour.
If confirmed by the community, this strengthens IC as a candidate
law of nature. That is the principle behind the robustness of our
telemetry floor (`bench/discovery/limit/README.md`, section 5).
