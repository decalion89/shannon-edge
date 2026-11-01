# Planet transits as anomalies (Kepler, no training)

A planet crossing its star dims the light for a few hours, which makes it
an anomaly in a time series. The test: can the flight profile's surprise,
knowing nothing about astronomy, see it? `bench/analysis/kepler_surprise.py`
uses NASA Kepler long-cadence light curves (public domain, via MAST),
quarter 3. Flux is quantised in units of each star's point-to-point noise.

**Kepler-10** (KIC 11904151; noise 51 ppm). Kepler-10c (P = 45.295 d)
transits twice in the quarter, at about −596 ppm.
* Mean surprise in transit is 4.09 bits against 2.66 overall.
* The in-transit peak is 14.8 bits, against an overall 99.9th percentile
  of 12.4.
* Points from both transits are among the ten most surprising of 4,134.
  One of them is the most surprising point of all.
* Other top points are not transits, so there are false alarms.
* Kepler-10b (152 ppm, 3σ per point) is not visible per sample. It needs
  folding over many orbits, which this detector does not do.

**TrES-2 / Kepler-1** (KIC 11446443; noise 54 ppm). 33 transits of about
1.5% in the quarter.
* The peak surprise at each transit onset is 8–17 bits, against a median
  of 1.88. In order:
  12.7, 10.7, 14.3, 10.6, 9.7, 14.8, 13.7, 9.9, 13.6, 15.4, 13.8, 16.0,
  16.0, 17.3, 15.0, 15.1, 10.5, 9.2, 14.3, 12.7, 11.5, 10.6, 15.8, 9.0,
  17.0, 16.9, 14.7, 15.6, 15.5, 14.8, 14.1, 8.0, 15.4.
* **The model does not get used to them:** a transit recurring every
  2.47 days stays as surprising at the 33rd onset as at the first.

This fits the "rarity limit" (`ecg_kraft.md`): onsets of a ~280σ drop are
rare in time, even if the transit recurs.

**What this is not.** Both planets are known, and their transits are
obvious: any dip detector finds them. Finding *new* planets means
low-signal transits, folding and false-positive vetting, which this
per-sample detector does not attempt. The result is that the same
training-free surprise transfers to starlight unchanged, onsets included.

## Accumulating weak transits: planet search as compression (`bench/analysis/mdl_transit_search.py`)

**The idea.** A code that knows a period, phase, duration and depth
predicts every dip, so it compresses the detrended light curve better than
a code that does not. The bits it saves are the evidence. Every
hypothesis on the search grid is named with log2(#hypotheses) bits, plus
0.5·log2(n) bits for the depth. By Kraft, *if the noise were white and
Gaussian*, the probability that pure noise saves t net bits is at most
2^−t, with no simulation needed.

**Kepler-10, quarter 3.** Both planets are recovered, with no astronomy in
the code:

| Planet | Found | Published | Net bits saved |
|---|---|---|---:|
| Kepler-10b (rocky, about 1.4 Earth radii) | P = 0.83730 d, 137 ppm, 2 h | P = 0.8375 d, about 152 ppm, about 1.8 h | **2,135** |
| Kepler-10c | P = 45.353 d, 381 ppm | P = 45.295 d | **1,157** |

The per-sample surprise could not see Kepler-10b, which is 3σ per point.
Accumulating it over 107 transits makes it the strongest signal in the
light curve.

**Control: nine stars with no known transiting planet.** The
asteroseismic targets KIC 12069449, 8006161, 3427720, 6106415, 6225718,
10454113, 8379927, 7510397 and 9139151 were searched the same way.

| Period range searched | "Net bits" of the best false signal in the nine stars |
|---|---|
| 0.5–50 days | 93–4,601 |
| 0.5–20 days (at least 4 transits possible) | 65–1,780 |

**The white-noise guarantee does not hold on real light curves.**
* Two different stars give the same "planet": P = 43.20 d at phase 0.906,
  and two others P ≈ 45.9 d at phase 0.85. These are instrument
  systematics that hit every star at the same time, not planets.
* The false signals rest on 8–10 points, that is one event, while
  Kepler-10b rests on 398 points spread over its transits.
* As a result, raw net bits do not separate Kepler-10b (2,135) from noise
  (up to 4,601).

A usable search would need what NASA's pipeline does: systematics removal
(cotrending against other stars), several transits each consistent in
depth, and vetting. Without those, **no new-planet claim can be made
from this code.** The finding stands as stated: compression accounting
recovers both known planets of Kepler-10, and its false-alarm bound needs
a calibrated noise model.

### Making the evidence honest: cotrending and split-half consistency

Two vetting steps, both standard in transit searches, were added to
`mdl_transit_search.py`.

**Cotrending (`--cotrend`).** The other stars of the same quarter give a
common mode: the median of their detrended flux, each in its own noise
units, interpolated to this star's times. It is subtracted, scaled by
least squares. A signal shared by every star is the instrument, not a
planet.

**Split-half consistency.** The best box must save bits in *each half*
of the quarter separately. A one-off instrumental event can only be in
one half.

Search over 0.5–20 days, quarter 3, each star cotrended against the
other nine:

| Star | Best period | Net bits | **Weaker half** |
|---|---:|---:|---:|
| **Kepler-10** (Kepler-10b) | 0.83730 d | 2,127.7 | **901.3** |
| KIC 8006161 | 14.957 d | 261.4 | 114.5 |
| KIC 12069449 | 18.914 d | 715.2 | 98.6 |
| KIC 10454113 | 18.408 d | 195.8 | 40.3 |
| KIC 9139151 | 8.114 d | 63.3 | 27.2 |
| KIC 7510397 | 12.508 d | 29.9 | 4.7 |
| KIC 3427720, 6106415, 6225718, 8379927 | — | 92–390 | ≤ 0.7 |

**Result.**
* Cotrending cut the false evidence by 2–5x (e.g. 1,780 → 715 bits) and
  left Kepler-10b unchanged.
* The weaker-half test then drops every false signal to at most 115
  bits, while Kepler-10b keeps 901: a margin of about 8x.
* On these ten stars a threshold of a few hundred bits in the weaker
  half separates the real planet from instrument effects.

Ten stars and one quarter are far too few to set a threshold or to claim
a false-alarm rate. A real search would need hundreds of quiet stars and
all quarters to calibrate it, and then candidates would still need
vetting by astronomers.

### Calibration on 62 quiet stars (Kepler LEGACY asteroseismic sample)

**Setup.** Three changes from the runs above:
* Cadences the pipeline flags (`SAP_QUALITY` ≠ 0) are now dropped. An
  earlier run without this step let flagged instrument events pass as
  transits.
* Each star is cotrended against 20 others.
* A per-transit check was added: for each predicted transit with data,
  is that transit's own mean dip below −2σ?

The search covers 0.5–20 days in quarter 3.

| | Bits in the weaker half |
|---|---:|
| 62 quiet stars: median | 12.1 |
| 62 quiet stars: 90th percentile | 94.8 |
| 61 of 62 quiet stars: at most | 174.9 |
| **Kepler-10b** (98 of 100 predicted transits show the dip) | **842.1** |
| KIC 11081729 (4 of 5 predicted "transits" show a dip) | 1,061.9 |

**Kepler-10b clears every quiet star but one.** The exception, KIC
11081729, is a variable F star (6,630 K). Its raw flux scatters by
220 ppm, against 31 ppm of white noise. Its deepest 8-hour dips fall
7.6, 6.9, 8.1, 27.7 and 17.9 days apart, which is not periodic, yet 4 of
the 5 epochs predicted at 17.93 days line up with a dip. With only five
epochs, the per-transit check cannot reject it.

At a threshold of 300 weaker-half bits, the empirical rate is about one
false positive per 62 star-quarters. Kepler observed ~150,000 stars, so
that is far too many for discovery. A usable search would also need
stellar-variability filtering, transit shape (U versus V), odd/even depth
and centroid tests, all of which the NASA pipeline applies.

**Where this leaves the idea.** The compression framing is sound and
finds a 1.4-Earth-radius planet. Vetting is what makes a planet search
trustworthy, and this code has only the first steps of it. No discovery
is claimed.
