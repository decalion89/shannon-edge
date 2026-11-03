# The three layers of a telemetry link: noise, structure, decision. Pre-registration

Committed before any number below is computed. The script
(`bench/discovery/bit_layers.py`) is committed with it and is not changed
after the run.

## Question

What fraction of a lossless telemetry link is a bit-exact copy of
sensor noise? How small is the information a decision needs, compared
with what is sent?

Every link today is sized by **samples**. If most of the bytes are
noise and the decision is many orders of magnitude smaller, a link
could be sized by **decisions** instead. This test measures the three
layers on real data, from many domains and from two spacecraft.

## Thinking it through first: what is already known

* **Noise.** High-resolution quantisation theory predicts the cost of
  white noise at a given resolution, about log2(σ·√(2πe)/Δ) bits per
  sample. Near-lossless coding exploits it: JPEG-LS and CCSDS 123.
  This project has measured it before on Venus Express (61% saved at
  1σ, `near_lossless.md`) and on ESA Mission 1 (57%).
  * New here: the census across 528 series from many domains (TSB-AD),
    with real bytes from one coder.
* **Decision.** Goal-oriented and semantic communication is an active
  field, for example Stavrou and Kountouris's rate-distortion treatment
  (EURECOM) and arXiv:2604.19614.
* **"Does the decision grow more slowly than the data?"** On reflection
  this reduces to known results, so it is **not** claimed as a law:
  * a decision of the form "is there an event at time t" costs about
    n·h_b(λ) bits, the binary entropy of the event rate;
  * its growth over time is the event process's trend, which reliability
    engineering models as the Crow-AMSAA law N(t) = λt^β.
  * The decision layer is therefore reported as a measured ratio, with
    an order-of-magnitude prediction.

## Definitions (fixed)

**Coder.** For every channel, the flight profile's real frame bytes
(`flight_surprise`, as in `bench/esa_edge_link.py`, whose `to_codes`,
`flight` and `varint_len` are imported unchanged).

* **Lossless layer, L.** The frame bytes of the channel's value codes.
  These are the distinct values, merged into 65,536 ordered bins if
  there are more, as everywhere in this project.
* **Structure layer, E.** The frame bytes of the lattice indices
  k = round((v − v₀)/2δ):
  * δ = 1 robust σ = 1.4826·MAD(first differences)/√2, estimated on the
    normal or training part only;
  * |v − v̂| ≤ δ is checked on every sample.
  * If σ = 0, E = L (no saving).
  * If the indices span more than 65,536 values, or the bound fails, the
    channel also counts as E = L. This is conservative.
* **Noise share of a series:** 1 − ΣE/ΣL over its channels.
* **Decision layer, D (ESA only, where events are labelled).**
  * Labelled intervals are mapped to sample indices per channel and
    sorted by start.
  * Each event costs γ(gap + 1) + γ(length), with
    γ(x) = 2⌊log2 x⌋ + 1 bits (Elias gamma). The gap is counted from the
    previous event's end.
  * Each channel adds γ(count + 1).

## Data

* **TSB-AD-U-Eva:** 348 series. **TSB-AD-M-Eva:** 180 series, all
  channels.
  * The normal part is the benchmark's `tr_N`, taken from the file
    name.
* **ESA-ADB, whole missions:**
  * Mission 1 lightweight, channels 41–46; training before 2006-10-01.
  * Mission 2 lightweight, channels 18–28; training before 2001-07-01.

## Hypotheses (each passes or fails on its own; all are reported)

* **L1 (noise census).** The median noise share is ≥ 50% on TSB-AD-U-Eva,
  and separately on TSB-AD-M-Eva.
* **L2 (the noise scale removes the arbitrary resolution).** On
  TSB-AD-U-Eva series with σ > 0 and the bound held:
  * the interquartile range (IQR) of structure bits per sample (8E/n)
    is less than half the IQR of lossless bits per sample (8L/n).
  * In words: once sub-noise detail is removed, signals from different
    domains cost much more alike than their raw streams do.
* **L3 (decision layer).** D/(8L) < 10⁻⁴ on both ESA missions.

**Also reported, with no hypothesis:**
* per-dataset noise shares;
* the bound check on every channel;
* each ESA mission's three layers (L, E, D);
* the on-board Kraft alarms' bytes, using the rule of
  `esa_edge_link.py` with the ESA-ADB test split (Mission 1:
  2007-01-01; Mission 2: 2001-10-01).

## What a pass would and would not mean

**A pass would mean:** on real data from many domains, most of a lossless
link is noise at the sensor's own scale, and the decision is orders of
magnitude smaller than either. That argues for sizing links by
decisions and noise scale, not by samples.

**It would not mean:**
* new physics or a new bound;
* that 1σ is acceptable for any particular user;
* that ground analyses other than the on-board detector are preserved.
  The re-detection test on reconstructed data was refuted
  (`bench/results/esa_near_lossless_preregistration.md`).
