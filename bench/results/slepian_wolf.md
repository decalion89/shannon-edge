# Slepian–Wolf for housekeeping packets: a thin encoder, a thinking ground

**Question.** Our packet profile beats CCSDS 124 by ~35% but its encoder
is ~10x slower and needs megabytes. Slepian and Wolf (1973) showed the
encoder does not need the model at all: if the decoder holds correlated
side information, the encoder can send *syndromes* (parities of bit
subsets) at a total rate close to the conditional entropy. On a spacecraft
that would mean an encoder of XORs and no state — simpler than CCSDS 124 —
with the modelling done on the ground, where compute is free and the whole
history is available. Distributed source coding has been studied for
onboard *hyperspectral image* compression (e.g. Magli et al., EURASIP 2007;
Nonnis et al., ICIP 2005); we found no prior work on housekeeping packets.

**Data.** Venus Express packets of the CCSDS 124 test vectors (90 bytes),
first 10% used only to train the decoder's model, as in the other packet
experiments.

## 1. The bound

Per-bit side information at the decoder: adaptive probabilities (decay
0.98) per bit position, in contexts from the two previously decoded
packets. Ideal Slepian–Wolf cost = sum of −log2 p of the true bits, on the
136,080 test packets:

| Representation, contexts | Ideal bytes | vs CCSDS 124 R=0 (4,772,219) |
|---|---:|---:|
| binary, bit above | 3,956,489 | −17.1% |
| binary, bit above + two back | 3,887,779 | −18.5% |
| binary, linear extrapolation + above + above+1 + two back | 3,731,414 | −21.8% |
| **Gray code per byte**, same contexts | **3,452,668** | **−27.7%** |

(For reference, the full packet profile: 3,108,861.) Gray coding is
stateless on board and halves the bit flips of slowly changing values.

## 2. A real code: `examples/slepian_wolf.rs`

Encoder: Gray code, then m parity checks of degree 9 from a fixed
quasi-regular, rate-compatible sequence (every prefix covers every bit
almost equally), plus a CRC-24. Decoder: BP, then OSD-0/OSD-1, with a
CRC + typical-set acceptance test. Rateless with feedback: the ground asks
for 4 more checks at a time until a candidate is accepted.

First 6,000 test packets (CCSDS 124 R=0 on the same packets: 225,475
bytes):

| | Bytes | vs CCSDS 124 R=0 |
|---|---:|---:|
| Ideal Slepian–Wolf (same model) | 162,223 | −28.1% |
| **Rateless with feedback: checks + CRC-24** | **194,403** | **−13.8%** |

Gap to the ideal: +19.8% (short 720-bit blocks, step granularity, and the
24 CRC bits + 8-bit typicality margin per packet). 7.6 feedback rounds per
packet on average; 3 packets of 6,000 needed all 720 checks. Every packet
verified.

Development notes, kept because they matter: purely random checks left
many uncertain bits covered once or not at all (+37% gap, 2.5% packets
failed); the quasi-regular sequence and OSD fixed that. Without the
typical-set test a wrong candidate passed the CRC-24 (packet 18,389: a
solution of the 204 checks *more* likely under the model than the truth,
cost 198.8 vs 218.3 bits) — search-based decoding needs a verification
budget beyond the CRC.

## 3. Without feedback: negative result

Deep-space links cannot afford a round trip per packet. Without feedback
the encoder must choose m itself. Its cheapest proxy, the number of
(Gray) bits changed since the previous packet (90 bytes of state, as
CCSDS 124 keeps), correlates only 0.37 with the checks actually needed
(the decoder's own expected cost: 0.63). Fitting m = a·d + b on the first
3,000 packets and testing on the next 3,000 (1-byte rate header, failed
packets resent raw):

| Target success | Rule | Decoded first time | Bytes incl. resends | vs CCSDS 124 R=0 |
|---:|---|---:|---:|---:|
| 95% | m = 1.00·d + 178 | 98.07% | 126,101 | +10.8% |
| 99% | m = 2.25·d + 115 | 99.90% | 148,830 | +30.7% |
| 99.9% | m = 3.50·d + 59 | 100.00% | 178,894 | +57.1% |

With feedback the oracle cost on those packets is 97,331 bytes (−14.5%).

## Reading

* The bound is real and large: an XOR-only, stateless encoder could in
  principle get −28% vs CCSDS 124, close to the full learning compressor.
* With per-packet feedback a first practical code gets −13.8%. That
  setting exists (a ground station in live contact with a low-orbit
  satellite, requests batched per round trip), but it is not the
  deep-space case, and 7.6 rounds per packet is a lot.
* Without feedback, rate selection on 720-bit packets fails: it is worse
  than CCSDS 124. The open problem is rate selection, not decoding. Ideas
  not yet tried: coding many packets per block (rates average out, but
  side information becomes older), letting the ground uplink per-bit
  volatility so the encoder estimates its rate better, or hybrid schemes
  (a few predicted bits sent plainly, the rest by syndromes).

## 4. Rate selection with a ground-uplinked table

Follow-up on the open problem. The ground, which decodes everything, can
uplink a per-bit *flip-cost table* (720 bytes; refreshed every 1000 packets
here): the encoder adds the cost of each bit that changed (Gray domain)
since the previous packet — one table lookup per changed bit, no model and
no arithmetic coder — and sets m = a·est + b. Fitted on the first 3,000
test packets, tested on the next 3,000 (`bench/slepian_wolf_rate.py`;
1-byte rate header and CRC-24 counted). On those packets the oracle with
per-packet feedback takes 97,367 bytes and CCSDS 124 R=0 113,887.

| Encoder-side estimate | Correlation with checks needed |
|---|---:|
| bits changed (section 3) | 0.38 |
| per-bit flip-cost table | 0.78 |
| order-1 table (did the bit flip last time?) | 0.78 |

| Order-1 table | Packets needing a 2nd round | Bytes | vs CCSDS 124 R=0 |
|---|---:|---:|---:|
| No feedback, 99.97% first-time (failures resent raw) | 0% (0.03% resent) | 140,551 | +23.4% |
| No feedback, 99.60% first-time | 0% (0.4% resent) | 127,160 | +11.7% |
| Hybrid ARQ (only failures ask for more checks) | 11.7% | 106,752 | −6.3% |
| Hybrid ARQ | 4.9% | 110,064 | −3.4% |
| Hybrid ARQ | 2.1% | 115,300 | +1.2% |

(The hybrid ARQ rows assume the decoder knows how many more checks a failed
packet needs, rounded up to 16; one extra round is optimistic.)

**Reading.** The table doubles the predictability of the rate, but not
enough: the checks a 720-bit packet needs vary too much around its
information content (short-block decoding), so a safe fixed rate wastes
more than the model gains. Without feedback the scheme stays worse than
CCSDS 124; with feedback on a small fraction of packets it is a few
percent better. On these packets Slepian–Wolf coding gives an XOR-only
encoder near CCSDS 124's efficiency, not beyond it. The learning encoder
plus erasure coding (`venus_fec.md`, −30% under 1% loss) remains the
stronger result.
