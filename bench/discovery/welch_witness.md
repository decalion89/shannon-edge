# A noise-robust quantum coincidence inequality: S² ≤ T

## Statement

For a bipartite box with binary outcomes and N settings per side, let

- S = Σₓ p(0,0|x,x) (diagonal coincidences),
- T = Σₓ,ᵧ p(0,0|x,y) (all coincidences).

**Claim.** Every commuting-operator box (and hence every quantum box,
finite- or infinite-dimensional) satisfies

    S² ≤ T.

On the face F₀ of arXiv:2610.41448 (p(0,0|x,y) = 0 for x ≠ y) we have T = S,
and the inequality becomes S ≤ 1. That is their exact-zero witness, Eq. (witness).
Off the face, the inequality stays valid and degrades smoothly. This gives
the "quantitative version that allows nonzero off-diagonal coincidences",
which that paper leaves for future work (end of their Sec. "exact-zero
witness").

## Proof

Let ψ be the state and A_x, B_y the outcome-0 effects (0 ≤ A_x, B_y ≤ 1) with
[A_x, B_y] = 0. Put A = Σ A_y, B = Σ B_y and X = Σ_y A_y B_y. Then
S = ⟨ψ, Xψ⟩ and T = ⟨ψ, ABψ⟩.

1. For each y, the block operator

       [[A_y², A_y B_y], [B_y A_y, B_y²]] = v_y v_y†,   v_y = [A_y; B_y],

   is positive. Summing over y and using A_y² ≤ A_y and B_y² ≤ B_y gives
   [[A, X], [X, B]] ≥ 0.
2. X is Hermitian, since A_y and B_y commute. By the maximal characterisation of the
   operator geometric mean (Ando; Pusz–Woronowicz), [[A, X], [X, B]] ≥ 0
   implies X ≤ A # B. If needed, first replace A, B by A + δ, B + δ and let δ → 0.
3. A and B commute, so A # B = A^{1/2} B^{1/2}.
4. Hence S = ⟨ψ, Xψ⟩ ≤ ⟨ψ, A^{1/2}B^{1/2}ψ⟩ ≤ ‖A^{1/2}B^{1/2}ψ‖ = ⟨ψ, ABψ⟩^{1/2} = √T. ∎

The proof uses only commutation of Alice's and Bob's operators, so it covers the
commuting-operator model. No dimension bound and no N ≥ 3 condition are needed.

## Tightness

- **Classical:** shared uniform label u; each party outputs 0 iff its setting is
  u. Then S = T = 1.
- **Quantum:** a maximally entangled state in C^d ⊗ C^d with rank-one
  projectors A_x = |φₓ⟩⟨φₓ| and B_x = conjugate. Here S = N/d and
  T = Σ |⟨φₓ|φᵧ⟩|²/d. Equality S² = T is exactly equality in the Welch bound
  Σₓ,ᵧ |⟨φₓ|φᵧ⟩|² ≥ N²/d. It is attained by equiangular tight frames, e.g. SIC
  POVMs (N = d²) and complete MUB-type frames. In this form the inequality is a
  device-independent version of the Welch bound.
- **NPA level 2:** for symmetric boxes, the level-2 maximum of S at fixed
  off-diagonal coincidence ε (`npa_robust.py`, N = 4…10, 20 points) equals
  (1 + √(1 + 4E))/2 with E = N(N−1)ε. That is exactly S² = S + E = T (maximum
  deviation 5·10⁻⁶). Since level 2 contains the quantum set and the bound is
  attained, the inequality is the exact quantum boundary in these coordinates.

## Post-quantum violation and noise tolerance

The optimal almost-quantum certificate boxes of arXiv:2610.41448 lie on F₀ with
S = N³/(17N² − 80N + 64). They violate S² ≤ T for every N ≥ 9 (S² − T = S(S − 1) > 0).
If those boxes are perturbed by off-diagonal coincidences ε while S stays fixed,
the violation survives as long as ε < S(S − 1)/(N(N − 1)):

| N | S | S² − T | tolerated ε |
|---|---|---|---|
| 9 | 1.011 | 0.011 | 0.00016 |
| 18 | 1.411 | 0.581 | 0.0019 |
| 100 | 6.170 | 31.9 | 0.0032 |
| 1000 | 59.10 | 3434 | 0.0034 |
| ∞ | N/17 | ~N²/289 | **1/289 ≈ 0.35 %** |

The tolerated noise per off-diagonal entry does not vanish as N grows. It
tends to the constant 1/289. The exact-zero witness, by contrast, certifies
nothing at any nonzero noise.

## Numerical checks (`welch_witness.py`)

- 4000 random quantum strategies (projectors and general effects, random
  states, N = 2…8, local dimensions 2–4): max S² − T = 1.8·10⁻¹⁵.
- Operator inequality A^{1/2}B^{1/2} − X ≥ 0 in 1500 random cases: minimum
  eigenvalue −2.5·10⁻⁹, which is matrix-square-root round-off.
- ETF equality cases: N = 4, 7, 9, 16 all give S² = T exactly.

## Prior art (searched 2026-11-03)

- The face version S ≤ 1 is in arXiv:2610.41448 (Corollary "exact-zero
  witness"). For tensor products it follows from Claim 1 of Klauck–de Wolf (2013).
- The Welch bound is classical in frame theory (Welch 1974).
- We did not find the robust inequality S² ≤ T stated for correlations, nor
  its geometric-mean proof, nor the Welch-bound interpretation. The searches
  covered almost-quantum and Welch-bound correlation inequalities, and ETF
  self-testing. The closest hits are ETF-based self-testing in the
  prepare-and-measure scenario (arXiv:2609.13075) and ETF Bell-state
  measurements (arXiv:2405.03872). The inequality is short enough that it
  could exist elsewhere under another name; a deeper search is still needed
  before calling it new.

## Classical = quantum in the (S, T) plane

S² ≤ T also holds classically, and it is not a Bell inequality. A deterministic
local strategy has S = |Z_A ∩ Z_B| and T = |Z_A||Z_B| ≥ S², where Z_A, Z_B are the
settings with output 0. Mixtures satisfy E[s]² ≤ E[s²] ≤ E[t]. So in these
coordinates quantum correlations are exactly as constrained as classical ones,
while almost-quantum correlations are not. This is the robust form of the
"no quantum advantage, unbounded AQ advantage" statement of arXiv:2610.41448.

## Where the proof breaks (exploration)

- **Three parties** (`welch_tripartite.py`): S³ ≤ T₃ with S = Σ p(000|xxx) and
  T₃ = Σ p(000|xyz) holds classically. Gradient search over three-qubit states
  and rank-one projectors found no quantum violation for N = 2, 3 (max S³ − T₃ ≈ −2·10⁻¹¹).
  N = 4 ran out of time. No proof yet.
- **Time instead of space** (`welch_temporal.py`): one system, Lüders
  measurement A_x, then B_y. Here [A_x, B_y] ≠ 0 and the proof fails.
  Macrorealist (non-invasive) models obey S² ≤ T, but quantum mechanics violates
  it strongly:

  | N | d | max S² − T found | S | T |
  |---|---|---|---|---|
  | 2 | 2 | 0.537 | 1.585 | 1.975 |
  | 3 | 2 | 1.209 | 2.377 | 4.443 |
  | 3 | 3 | 1.483 | 2.224 | 3.465 |
  | 4 | 2 | 2.149 | 3.170 | 7.899 |
  | 4 | 3 | 2.636 | 2.966 | 6.160 |

  This is a Leggett–Garg-type violation of macrorealism. That genre is known,
  and an invasive classical model (B remembering x) reaches S² − T = N² − N, so
  the violation by itself certifies nothing beyond macrorealism. Whether the
  quantum temporal maximum has a closed form is open.

## General form: any list of pairs (`welch_family.py`)

For any list of K (Alice outcome, setting; Bob outcome, setting) pairs, with
repetition allowed and any number of outcomes:

    ( Σ_k p(a_k b_k | x_k y_k) )²  ≤  Σ_{k,l} p(a_k b_l | x_k y_l).

The proof is the same: A_k, B_k are the corresponding effects and A_k² ≤ A_k.
The classical version is the Cauchy–Schwarz inequality for indicator functions.
A check over 3000 random quantum strategies (three-outcome measurements, random
lists with K ≤ 8) gives max S² − T = 0. The diagonal inequality is the case
K = N, k ↦ (0|k, 0|k).
