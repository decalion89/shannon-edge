# The limit for transmitting a sensor with a per-sample error guarantee

**Problem.** Send a source X so that every reconstructed sample obeys
|X − Y| ≤ δ. What is the minimum rate R∞(δ) any method can achieve?
This is Kolmogorov's ε-entropy with a sup-norm (per-sample) criterion.

## 1. The floor (Shannon lower bound for a max-error criterion)

The error X − Y lies in [−δ, δ], so its entropy is at most log2(2δ).
Therefore

    R∞(δ) ≥ I(X;Y)/n ≥ h(X) − log2(2δ)    (bits/sample, h = differential entropy rate)

Every sensor has noise. For X = S + N with N independent white noise,
h(X) ≥ h(N): adding an independent variable never lowers entropy. With
Gaussian noise of standard deviation σ_N:

    R∞(δ) ≥ log2( sqrt(2πe) · σ_N / (2δ) ),   so at δ = σ_N:  R∞ ≥ log2(sqrt(2πe)/2) = 1.047 bits/sample

**No method can send a sensor with white Gaussian noise σ, guaranteeing
every sample within σ, for less than about 1.05 bits per sample.** The
floor does not depend on the sensor, the domain or the technology.

## 2. The exact limit, computed (`eps_entropy.py`)

Blahut–Arimoto with a hard constraint minimises I(X;Y) over channels
supported on |x − y| ≤ δ, for an i.i.d. source on a fine grid. The
discrete Shannon bound is h − log2(2δ + dx).

| Source | δ | Shannon floor | Exact ε-entropy | Uniform lattice (step 2δ) | Lattice excess |
|---|---:|---:|---:|---:|---:|
| Gaussian | 0.5σ | 2.047 | 2.047 | 2.105 | +0.058 |
| Gaussian | **1σ** | **1.047** | **1.047** | **1.241** | **+0.194 (+18.5%)** |
| Gaussian | 2σ | 0.047 | 0.18 | 0.312 | +0.13 |
| Laplace | 0.5σ | 1.943 | 1.946 | 2.014 | +0.07 |

**Notes on the computation:**
* The exact values are the grid computation corrected by the
  discretisation term log2(1 + dx/2δ).
* At δ = 1σ the exact value equals the discrete Shannon bound at
  dx = 0.02 (1.0328 vs 1.0327) and dx = 0.01 (1.0400 vs 1.0399). The
  continuous limit is therefore 1.047 to within about 10⁻⁴.

**Findings:**
* **At the noise scale (δ ≤ σ), the Shannon floor is essentially tight
  for Gaussian noise.** The limit is known in closed form:
  log2(√(2πe)·σ/2δ).
* **The uniform lattice pays a "lattice tax" of 0.19 bit/sample (18.5%)
  at δ = σ.** The lattice is what near-lossless standards use (JPEG-LS,
  CCSDS 123.0-B-2) and what our protocol uses.
  * The tax is small at δ = 0.5σ (0.06) and rises in the coarse regime.
  * It can be recovered in principle by block (vector) coding that
    reaches the ε-entropy. That is an engineering target, not yet
    built.

## 3. Where real data sit

On 297 TSB-AD-U series at δ = robust σ, the protocol spends a median of
1.88 bit/sample (`kolmogorov_limit_preregistration.md`). That is about
0.8 bit above the 1.05 noise floor:
* about 0.19 is the lattice tax;
* the rest is the signal's own innovation (what it says beyond noise)
  plus coder overhead.

The floor uses the true noise σ_N. Our robust σ is estimated from
first differences and can include signal innovation, so for real
series the floor is indicative.

**Prior art.** ε-entropy goes back to Kolmogorov and Tikhomirov (1959)
and Posner, Rodemich and Rumsey (1967, 1971). The Shannon lower bound
for difference distortions is textbook. What is assembled here is its
use as a universal floor for noise-scale telemetry, the numerical
tightness at δ = σ, and the size of the lattice tax.

## 4. First attempt to remove the lattice tax: "hold" quantisers (`free_quant.py`)

**Idea.** The guarantee leaves freedom: any reproduction within ±δ is
valid. The "hold" quantiser keeps the previous value while it stays
admissible, and otherwise moves minimally on a grid of step 2δ/m.

| Source (δ = σ, flight profile real bytes) | Lattice | hold m=2 | m=4 | m=8 | m=16 |
|---|---:|---:|---:|---:|---:|
| white Gaussian noise | **1.374** | 1.712 | 2.059 | 2.435 | 2.832 |
| random walk + noise | **1.721** | 2.052 | 2.369 | 2.746 | 3.152 |

**Refuted: holding is worse,** and worse the finer the grid. Repeats
become cheap, but every move is an unpredictable jump among many
possible values. That costs more than the repeats save.

**What the numbers do show:**
* On white noise, the flight coder spends **1.374** bit/sample on lattice
  indices whose entropy is **1.241**.
  * That is a **coder overhead of 0.13 bit/sample (10%)**: adaptive
    learning and binary decomposition.
  * It is recoverable with a better-matched model, independent of the
    lattice.
* The lattice tax itself (1.241 against the limit 1.047) can only be
  removed by block schemes.
  * The optimal backward channel is X = Y + uniform noise. Reaching it
    needs randomised choices shared with the receiver (channel
    simulation, e.g. the Poisson functional representation of Li and El
    Gamal, 2018).
  * Their overhead is about log2(nI + 1) + 4 bits per block.
  * At feasible block lengths (n·I of 10–20 bits), that overhead exceeds
    the 0.19 bit/sample gain.
  * Recovering the tax is therefore a long-block coding problem, of the
    kind LDPC or polar codes solve for channels. It remains open here.

## 5. Does physics beyond classical change the floor?

**Short argument.**
* Alice holds X^n and shares any resource with Bob: entanglement, or
  any quantum state.
* She sends a classical message M of nR bits, and Bob outputs Y^n.
* By data processing, I(X^n;Y^n) ≤ I(X^n; M, B), where B is Bob's share.
* I(X^n; M, B) = I(X^n; B) + I(X^n; M | B). The first term is 0,
  because the shared resource is independent of X^n. The second is at
  most H(M) ≤ nR, because M is classical.
* Hence **R ≥ I(X;Y)/n ≥ R∞(δ)**.

**The floor log2(√(2πe)·σ/2δ) therefore holds for any quantum
protocol.**
* Entanglement does not raise the classical capacity of a classical
  channel either.
* Breaking the floor would need correlations that let m classical bits
  carry more than m bits of information. That is exactly what
  **information causality** forbids (Pawłowski et al., Nature 2009).
  * PR boxes violate it, and that is one reason physicists believe such
    boxes do not exist in nature.
* **The limit on sending a sensor with a guarantee is as robust as
  information causality itself.**

**Where non-classical resources do help.** One-shot, zero-error
settings with confusability structure:
* entanglement enlarges the zero-error one-shot capacity of some
  channels (Cubitt, Leung, Matthews, Winter, PRL 104, 230503, 2010);
* it can improve zero-error source codes without bound (Briët, Buhrman
  et al.).

A guarantee **per packet, with fixed-length packets** is a one-shot,
zero-error requirement. Whether entanglement shrinks the
worst-case packet size for guaranteed-error telemetry seems to be
open. It could be formulated as a graph problem on the confusability of
lattice cells and bounded with non-signalling linear programs, as in
arXiv:1003.3195.
