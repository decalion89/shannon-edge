# Half the link, every anomaly kept? Error-bounded telemetry on ESA-ADB (pre-registration)

Committed before any error-bounded run on ESA data.

**Why.** On ESA Mission 1, 43–63% of lossless bits go to the four finest
levels of each value (`near_lossless.md`), largely sensor noise.
Agencies send everything losslessly so that no fault signature is lost.
This tests whether an error-bounded link keeps the anomaly detection
intact while sending far fewer bits.

**Data and protocol.** ESA-ADB Mission 1 lightweight (channels 41–46),
the ESA-ADB split, scored with ESA-ADB's own metric code (`--official`),
as in `esa_adb.md`.

**Reconstruction.** For each channel, a closed-loop quantiser on the
values (as in `bench/analysis/near_lossless.py`):
* r_t = r_{t−1} + 2δ·round((v_t − r_{t−1})/(2δ)), so |v_t − r_t| ≤ δ
  holds for every sample (real-valued channels, hence 2δ rather than
  the integer 2δ+1);
* δ = K × robust noise σ, where σ = 1.4826·MAD(first differences)/√2 is
  estimated on the training part only (before the validation start).

The detector then runs on the reconstructed values (`--near-lossless K`).

**Budgets.**
* **Primary: K = 1**, the "safe ≤ 1 σ" level of the Venus Express study.
* Reported as well: K = 0.5.

**Measures.**
* **Bits:** the flight profile's total cost over all samples of the six
  channels, reconstructed vs lossless.
* **Detection:** the corrected event-wise F0.5 (official) for two
  rules, on reconstructed vs lossless data:
  * the trained rule (q = 1.0, chosen on validation);
  * the training-free Kraft auto rule.

**Success, all required at K = 1:**
* bits saved ≥ 40%;
* |ΔF0.5| ≤ 0.01 for both rules.

Anything else is reported as it is.

## Result (run once per budget; the full outputs are in `bench/results/data/esa_nl_k{0,1,05}.md`)

| Budget | Bits, 6 channels | Saved | F0.5 trained rule (q = 1.0) | F0.5 Kraft auto |
|---|---:|---:|---:|---:|
| Lossless | 45.27 MB | — | 0.690 (20 TP, 0 FP) | 0.705 (21 TP, 0 FP) |
| **K = 1 (primary)** | **19.39 MB** | **57.2%** | 0.703 (26 TP, **4 FP**) | **0.674** (19 TP) |
| K = 0.5 | 29.20 MB | 35.5% | 0.665 (23 TP, 4 FP) | 0.657 (18 TP) |

**Verdict at K = 1: refuted.**
* The bits condition holds: 57.2% saved, well above 40%.
* The detection condition fails: the trained rule moves by +0.013 and
  Kraft auto by −0.031, both outside ±0.01.

**What changed.** The detector runs on reconstructed values, and the
reconstruction changes the statistics it sees.
* The trained rule now raises 4 false detections; it finds more events
  but less cleanly.
* Kraft auto loses two of its 21 events.

At K = 0.5 both rules lose more, so the effect is not monotone in the
error bound. Quantisation to a lattice reshapes the surprise rather
than just removing noise.

**What this means.** A uniform error bound halves the link, but it does
**not** leave anomaly detection unchanged. The version designed for this
keeps rare values exact (surprise-adaptive, `near_lossless.md`), and it
is not what was tested here. Any test of it has to be pre-registered
separately.
