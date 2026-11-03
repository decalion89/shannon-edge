# A receiver-only upgrade: decoding an unchanged spacecraft link with a learned telemetry prior. Pre-registration

Committed before the run. The script is
`bench/discovery/receiver_prior.py`.

## The question

**Can the ground make an existing link stronger by changing only the
receiver, without touching the spacecraft?**

Many missions send housekeeping uncompressed through a standard channel
code. Shannon's separation theorem says compression and channel coding
can be designed apart without loss. That holds only asymptotically, and
when the source is actually compressed.

Uncompressed telemetry is full of redundancy: our census found about
two thirds of a lossless stream is noise below 1σ. The rest is highly
predictable structure. A receiver that knows that structure can treat
it as **free error protection**.

## Prior art (checked)

* **Source-controlled channel decoding** (Hagenauer 1995, the a-priori
  Viterbi algorithm). Used for speech codecs in mobile radio.
  Patents US6292922 and US6348880.
* **Joint source-channel coding beats separation at finite
  blocklength.** Kostina and Verdú; recent surveys, e.g.
  arXiv:2409.17557. A textbook summary puts the gap at 0.5–2 dB for
  5G URLLC parameters; this figure is unverified.

**Not found in our searches:**
* a measurement on real spacecraft housekeeping with a learned model;
* the measurement of the risk this creates for anomalies.

The risk: a prior that expects the usual value may "correct" a real
change into the expected one. On this project's theme, that is the
cost a receiver-side prior imposes on surprise.

## Setup (fixed)

* **Data.** Venus Express housekeeping, 151,200 real packets of 90
  bytes (the set used for the CCSDS 124 comparison). The prior is
  trained on the first half and tested on the second.
* **Link.**
  * Each packet (720 bits) is sent uncompressed through the CCSDS K = 7,
    rate-1/2 convolutional code (generators 171 and 133 octal), with a
    zero tail.
  * Modulation is BPSK over AWGN. Eb/N0 is per information bit,
    including the tail rate loss.
* **Receivers:**
  * **Plain:** the standard soft-decision Viterbi decoder.
  * **With prior:** the same Viterbi decoder, adding each information
    bit's a-priori log-probability to the branch metric. The prior is a
    column model, P(byte k | byte k of the previous packet as decoded
    by this receiver). It uses KT counts from the first half, backed
    off to the column marginal, and is marginalised to bits. **No genie:**
    decoding errors in the previous packet propagate.
* **Frames.** 40 runs of 50 consecutive packets (2,000 frames) per
  Eb/N0, with run starts drawn from the second half (seed 0). Eb/N0
  runs from −1 to 7 dB in 0.5 dB steps, with fixed noise seeds.

## Hypotheses

* **G1 (the upgrade).** The Eb/N0 needed for a frame error rate of
  10⁻² falls by **≥ 1.0 dB** with the prior. The crossing point is
  found by log-linear interpolation.
  * For scale: 1 dB is 26% more data rate on the same link.
* **G2 (where the risk lies).** At the 0.5 dB grid point nearest the
  with-prior operating Eb/N0, the frame error rate of the 5% most
  surprising test packets is ≥ 5x that of the rest. Surprise is the
  packet's code length under the prior, given the true previous
  packet.
* **G3 (the cost to surprise).** At that same grid point, the
  surprising packets are decoded **worse** with the prior than
  without it.

All three are reported whatever they show.

## What a pass would and would not mean

**A G1 pass would mean:** the ground alone can buy at least 1 dB on an
unchanged link carrying uncompressed housekeeping, simply by knowing
what the spacecraft usually says.

**G2 and G3 measure the price.** If they hold, the gain is paid for by
the very packets that matter most: the anomalies. A receiver would
then have to use the prior only together with a surprise check.

**It would not mean:**
* **It works on every link.** This is one mission, one code (many
  links concatenate Reed–Solomon or use turbo/LDPC codes) and a
  simulated AWGN channel.
* **Uncompressed telemetry is the right design.** Compression plus
  coding may still be better overall. The point is a gain for links
  that already fly as they are.
