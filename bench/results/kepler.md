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
