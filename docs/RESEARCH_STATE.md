# Research state: anomaly detection from the compressor's surprise

The working state of this line of research. Written so that the next
session can resume exactly where the last one stopped. Update it at the
end of every session. Results are in `bench/results/`; this file only
says where things stand.

## Established (pre-registered or confirmed on held-out data)

* **ESA Mission 2, whole mission, Alcarria et al.'s protocol.**
  * The training-free windowed e-value rule scores **0.724**, vs 0.698
    for their monthly-retrained method (`esa_chronological.md`).
  * Every score is above 20 circular time shifts.
* **Habituation is real.** An adaptive model learns a persistent
  anomaly. A reference snapshot of the normal prefix corrects it:
  * TSB-AD-M: 0.190 → 0.275;
  * TSB-AD-U: 0.219 → 0.269 with change + state;
  * Exathlon: 0.31 → 0.89.
* **Where it stands.** Mid-table on TSB-AD:
  * 8th of 25 on TSB-AD-M;
  * 18th of 33 on TSB-AD-U, level with the zero-shot foundation models
    Lag-Llama and Chronos.

* **Edge link, ESA Mission 2 lightweight (pre-registered,
  `esa_edge_link_preregistration.md`).**
  * The design: exact on-board detection, alarms sent losslessly, values
    sent with an error bound of δ = 1 robust σ.
  * Result: **65.1%** fewer real bytes than the lossless stream, after a
    correction. The first report said 78.6%, but channel 25's indices
    were binned after the error check, so it is now sent lossless.
    Channels 18–20 alone save 80.5%.
  * The error bound held on every sample. The 22 on-board alarms cost
    83 bytes.
  * Ground re-detection on the reconstructed values is **not** preserved;
    see below.
  * Both halves are prior art (CCSDS 123 near-lossless, on-board
    detection). What is new is the measured combination with a Kraft
    guarantee.

* **The three layers of a link (`bench/discovery/bit_layers_preregistration.md`).**
  * L1, noise census: the median share of the lossless stream below 1
    robust σ is 0.720 on TSB-AD-U-Eva (holds) and 0.499 on TSB-AD-M-Eva
    (refuted by 0.001). Pooled over bytes, about 67% on both.
  * L2 holds: at their own noise scale, series from 25 domains cost
    1.88 bits/sample (median), with an IQR of 0.45 bits against 4.33
    raw. Part of this is by construction.
  * L3 is refuted: ESA's labelled decisions are 1/8,800 and 1/3,400 of
    the lossless stream, not < 10⁻⁴.
  * The on-board alarms carry 50–300x fewer bits than the labelled
    decisions.

* **Anomalies that exist only between sensors (`bench/discovery/joint_only*`).**
  The question comes from the zero-rate testing theorem (Shalaby and
  Papamarcou 1992): per-sensor alarms can exploit only marginal
  statistics.
  * Exploratory run: J1 holds, J2 refuted. Confirmation on 76 fresh
    Mission 1 events: K1 holds (67% "joint-only"), K2 refuted again
    (27/31 Global events "joint-only").
  * **Not established.** The joint statistic, a cost difference with a
    tight null, is more powerful at any change, including marginal
    changes of the other channel. It does not isolate the relationship.
  * **Marginal-free coupling test with drift controls
    (`joint_coupling_preregistration.md`):** R1 refuted on effect size.
    5.3% of 711 events break the coupling, against 0.6% of controls
    (p = 2e-8, difference 4.8 points < 5).
  * Post hoc, about 6 of 711 events (< 1%) are coupling breaks with no
    per-channel signal. The relationship-only blind spot is real but
    small on ESA telemetry.

* **Receiver-only prior on an unchanged CCSDS convolutional link
  (`bench/discovery/receiver_prior_preregistration.md`).**
  * G1 refuted: a learned column prior in the Viterbi decoder gains
    0.15 dB, not >= 1 dB, on uncompressed Venus Express packets.
  * G3 holds: surprising packets are decoded worse with the prior.
  * Post hoc: source compression would be worth ~2.9 dB here, so the
    receiver recovers ~5% of it. Separation stands in practice.

## Refuted (pre-registered)

* **Error-bounded re-detection.** Detecting on the ground from 1σ
  near-lossless values, uniform or with rare values kept exact, loses
  detection quality (`esa_near_lossless_preregistration.md`).

* **Cross-channel corroboration as a general rule.** ESA Mission 2
  improved post hoc (0.871), but TSB-AD-M did not (0.171 < 0.190).
* **Beating the best published method on TSB-AD** (H2, H3, H5).
* **Mission 1 to 0.700.** It stays at 0.432; recurring anomalies
  (class_7) are invisible to surprise.

* **On-board triage (stage 4, TSB-AD-U-Eva, pre-registered).**
  * At 10% of the downlink, the ground keeps 62% of Sub-PCA's VUS-PR,
    so H6 (≥ 75%) is refuted.
  * That is 2.5x the random-window control, so H7 holds (p = 7e-30).
  * The 75% level is reached at about 30% of the downlink.

## Refuted (development only)

* The general model's match model does not see noisy shapes (0.15 vs
  0.25).
* One label recovers only ~40% of a recurring class (ideal template
  matcher).
* On-board triage + ground Sub-PCA keeps 85% of Sub-PCA at a 20%
  downlink, below the 90% criterion. It is still far above random
  windows (82% vs 28% at 10%).

## The boundary found

Lossless coding measures exactness; abnormal *shapes* need similarity up
to noise. The compressor's surprise sees events that are improbable in
their context:
* onsets;
* rare values;
* multi-channel bursts.
It does not see abnormal subsequences made of normal-looking steps.
Methods that compare subsequences (Sub-PCA, KShapeAD, matrix profile)
do.

## Measured, kept

* **Low-bit saturation law.** The transition model's cost of the 2 least
  significant bits saturates at 2.00 bits for white noise σ ≥ 4 quanta,
  invariant to amplitude, while the total cost grows one bit per
  doubling of σ (`tsbad.md`).
* The free API is `FlightSession::compress_scored_split`.
* As a detection channel it was **discarded** after L-switching:
  p = 0.077, 13 wins against 29 losses. It confuses discrete telemetry
  with structured fine scale.

## Competitors found in the literature (2026-11)

* Alcarria et al., SPAICE 2026, arXiv:2609.10017: 0.700 / 0.698.
* PitIA (GMV), as cited: 0.424 / 0.882. Unverified.
* Goetze, Schlippe and Lakey, SCC 2025, arXiv:2603.29375: 0.927 on
  Mission 1 lightweight; their 59 KB edge model scores 0.888.
* Prior art for the method: atypicality, universal Levin tests,
  e-detectors (Shin, Ramdas, Rinaldo), and per-series model selection
  (Goswami et al., ICLR 2023).

## Open, in order of expected value

1. **Done:** the cascade, see above.
   * Triage by events (window + neighbours) was tried in development: no
     gain (68% vs 82% at q = 10%, n.s.).
   * Next: a shape-aware on-board score; it must stay cheap.
2. **Calibration of the reference model under drift:** a quarantined
   update, accepting a window into the reference only under a stricter
   threshold and after a delay. Gated updating is prior art, so measure
   it; don't claim it.
3. **v2_lp C port.**

## Scratch data (not in the repository)

* ESA-AD missions, TSB-AD zips and the benchmark checkout live in the
  session scratchpad.
* Re-download links are in the scripts' docstrings: TSB-AD from
  thedatum.org; ESA-AD from Zenodo 10.5281/zenodo.12528696.
