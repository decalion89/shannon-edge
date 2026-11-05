# Searching for new laws of information (non-Shannon inequalities)

**Question.** Are there linear inequalities on the entropies of four
random variables that hold for every distribution but are not yet
known? Zhang and Yeung (1998) found the first that does not follow
from Shannon's. Matúš (2007) proved there are infinitely many. The full
set is still unknown, and it decides, among other things, the capacity
of general networks (network coding).

**Method.**
* Shannon (elemental) inequalities plus the **copy lemma**.
* For a sequence of copy steps, `project.py` computes **all** the
  4-variable inequalities it implies: the projection of the extended
  polymatroid cone onto the 15 coordinates.
  * It works by outer approximation: vertices come from cdd, separating
    inequalities from an LP over Farkas multipliers, and each is rounded
    to integers and re-verified.

**Checks that the machinery reproduces known results:**
* **Zhang–Yeung** is not Shannon-provable: its minimum over Shannon
  alone is −0.25. One copy (A over CD) proves it.
* **One copy step** yields only Zhang–Yeung variants, as Dougherty,
  Freiling and Zeger report.
* **DFZ's first inequality** is proved by their own copy sequence.
* **DFZ's six two-copy inequalities** of 2006 are all implied by their
  final list of 214 (`dfz_list.json`).
  * That list was extracted from the arXiv source of arXiv:1104.3602,
    Section "Inequalities Using Four Copy Variables with at most Three
    Copy Steps".

* **Exhaustive two-auxiliary search** (`search.py 2`):
  * 91 copy strategies up to symmetry give 7 irredundant inequalities
    (`two_copy_irredundant.json`).
  * They are **exactly equivalent** to Zhang–Yeung plus DFZ's six
    two-copy inequalities of 2006: each set implies the other.
  * This reproduces DFZ's exhaustive two-copy result independently, in
    about a minute.

**Frontier.** DFZ searched exhaustively up to four auxiliary variables
with at most three copy steps, which took 50–100 CPU-years. Four steps
was estimated at 70x that. `frontier.py` samples random four-step
strategies.
* Each inequality found is checked against Shannon plus the 214 DFZ
  inequalities under all 24 relabellings.
* A survivor is only a **candidate**: it must still be checked against
  later literature (Matúš's families, Xu–Wang–Sun, Csirmaz) before any
  claim.

## Beyond the Copy Lemma: the Maximum Entropy Method

Csirmaz (arXiv:2509.12439, 2025) lists as open problems:
* whether the Maximum Entropy Method (MEM) can prove an inequality that
  the iterated Copy Lemma cannot;
* the fact that there has been no systematic numerical exploration of
  it.

`mem.py` casts MEM as a projection problem:
* f on A, B, C, D is extended by exact duplicates, which is still
  entropic;
* g agrees with f on a down-closed family F and satisfies **every**
  conditional independence that separates F.

**Check:** with one duplicate and F = {ABCD, A'CD} (a single separating
statement, equivalent to a copy), it reproduces exactly Zhang–Yeung.

`memsearch.py` samples instances with 2–3 duplicates and up to 3 extra
maximal sets. Most instances impose several independence statements at
once, which is where MEM could exceed copies.

### Result: power of single MEM instances (`mem_power.py 2 600 7`)

The sample: 600 random MEM instances with two duplicates, each
imposing at least two conditional independence statements at once.
Results are in `mem_power_k2.json`.

* They imply **137 distinct non-Shannon 4-variable inequalities**.
* **All 137 follow from Zhang–Yeung alone**, i.e. from one copy step.
* None reaches beyond two copy steps, and none implies any of the 214
  DFZ inequalities.
* The random explorers (`memsearch.py`, about 2,400 more instances with
  2–3 duplicates) found no inequality outside the DFZ list either.

**Reading.** Csirmaz asks whether MEM can beat the iterated Copy Lemma.
In this regime the answer the data suggest is the opposite: imposing
many independence statements at once on duplicate-extended polymatroids
gives **no more than a single copy**.

This does not settle the open problem:
* other regimes are untested: auxiliary variables that are not
  duplicates, larger families, and 5-variable consequences, where
  Csirmaz's own MEM examples live;
* the instances are a random sample, not an exhaustive enumeration.

It is a measured data point on a question no one had explored
numerically.
