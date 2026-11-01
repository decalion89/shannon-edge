# Losing frames, not packets: a realistic link

Real space links (CCSDS TM/AOS) carry packets inside **fixed-length
transfer frames** and lose whole frames, when the channel decoder fails.
A lost frame takes several consecutive packets with it, and a packet that
straddles two frames is lost if either is. The earlier experiments lost
packets independently; this one loses frames.

**Setup** (`examples/frame_fec.rs`). Venus Express, last 90% of the packets
(136,080), first 10% used to prime the models (epochs of 4096). Compressed
payloads are packed back to back into **223-byte frames** (the classic
CCSDS Reed–Solomon codeblock size), each payload preceded by a 1-byte
length and each frame starting with a 2-byte first-header pointer, so a
receiver can resynchronise after a lost frame (as in CCSDS TM frames).
Every byte is counted: lengths, pointers, the partly filled last frame, and
all parity. Frames (data and parity) are lost i.i.d. For sedge, groups of
G frames get m Reed–Solomon parity frames (`shannon_edge::fec`): all frames
have the same length, so **parity needs no padding** — the overhead is
exactly m/G. CCSDS 124 (open C implementation) is framed the same way, the
same frame-loss process decides which of its packets survive
(`frame_fec --sizes`), and its own decoder runs on the survivors with every
gap reported (`bench/c/ccsds124_loss.c` with a mask file); every output is
compared with the original.

## sedge packet profile v2 (2^16) in frames

Payloads 2,843,306 bytes → 13,482 frames, 3,006,486 bytes (+5.7% for
lengths, frame pointers and the last frame; a real link pays the 6-byte
space-packet header instead, and so would CCSDS 124).

| Frame loss | G frames | m | Bytes sent | Overhead vs frames | Packets decoded |
|---:|---:|---:|---:|---:|---:|
| 0.1% | none | 0 | 3006486 | +0.0% | 85.70% |
| 0.1% | 200 | 2 | 3037086 | +1.0% | 100.00% |
| 0.1% | 250 | 3 | 3042936 | +1.2% | 100.00% |
| 1.0% | none | 0 | 3006486 | +0.0% | 23.72% |
| 1.0% | 200 | 6 | 3098286 | +3.1% | 97.45% |
| 1.0% | 240 | 8 | 3109086 | +3.4% | 100.00% |
| 1.0% | 240 | 10 | 3134736 | +4.3% | 100.00% |
| 5.0% | none | 0 | 3006486 | +0.0% | 5.29% |
| 5.0% | 200 | 22 | 3343086 | +11.2% | 100.00% |
| 5.0% | 220 | 26 | 3369186 | +12.1% | 100.00% |
| 5.0% | 220 | 30 | 3424986 | +13.9% | 100.00% |

## CCSDS 124 in the same frames, under the same frame loss

Its built-in robustness R tolerates up to R consecutive lost packets; a
lost 223-byte frame takes ~6–7 CCSDS 124 packets.

| CCSDS 124 configuration | Bytes in frames | Correct at 0.1% frame loss | 1% | 5% |
|---|---:|---:|---:|---:|
| R=0, pt=14, ft=10⁵, rt=10⁶ | 4,952,830 | 5.96% | 0.26% | 0.05% |
| R=2, pt=20, ft=10⁵, rt=10⁶ | 5,307,623 | 5.55% | 1.08% | 0.04% |
| R=3, pt=50, ft=10⁵, rt=10⁶ | 5,426,259 | 48.01% | 3.58% | 0.15% |
| R=5, pt=50, ft=10⁵, rt=10⁶ | 5,552,700 | 89.85% | 31.31% | 0.03% |
| R=7, pt=50, ft=10⁵, rt=10⁶ | 5,673,343 | 99.89% | 98.75% | 8.80% |
| R=7, pt=50, ft=100, rt=100 | 5,807,812 | 99.88% | 98.75% | 51.90% |

Only the maximum robustness, R=7, works, and not at 5%.

## Best against best

| Frame loss | CCSDS 124 (its own robustness) | **sedge v2 + RS over frames** | sedge fast + RS over frames |
|---:|---|---|---|
| 0.1% | R=7: 5,673,343 bytes, 99.89% | **G=200, m=2: 3,037,086, 100% (−46.5%)** | 3,687,856, 100% (−35.0%) |
| 1% | R=7: 5,673,343 bytes, 98.75% | **G=240, m=8: 3,109,086, 100% (−45.2%)** | 3,775,156, 100% (−33.5%) |
| 5% | R=7, ft=rt=100: 5,807,812 bytes, 51.90% | **G=200, m=22: 3,343,086, 100% (−42.4%)** | 4,056,856, 100% (−30.1%) |

**With the same protection for both.** CCSDS 124 at R=0 in the same frames
with the same Reed–Solomon parity frames: 5,003,230 / 5,120,230 /
5,507,230 bytes; sedge v2 is **−39.3%** at every loss rate, and the fast
profile −26.3%. With equal protection only compression
differs, as separation predicts; and frame-level protection makes CCSDS
124's own robustness unnecessary for it as well.

Protection overhead over the frames: +1.0% at 0.1% loss, +3.4% at 1%,
+11.2% at 5% (packet-level parity needed 1.5%, 6.3% and 24.8%; theory with
unlimited delay: 0.1%, 1.0%, 5.3%). Latency: after a loss, the receiver
waits for the group (up to 248 frames of ~10 packets). Not modelled: burst
losses longer than a group's parity (interleave groups), frame headers and
channel coding, which are the same for any codec.

### Fast profile, full table

| Frame loss | G frames | m | Bytes sent | Overhead vs frames | Packets decoded |
|---:|---:|---:|---:|---:|---:|
| 0.1% | none | 0 | 3650956 | +0.0% | 80.23% |
| 0.1% | 200 | 2 | 3687856 | +1.0% | 100.00% |
| 0.1% | 250 | 3 | 3695506 | +1.2% | 100.00% |
| 1.0% | none | 0 | 3650956 | +0.0% | 18.77% |
| 1.0% | 200 | 6 | 3761656 | +3.0% | 98.59% |
| 1.0% | 240 | 8 | 3775156 | +3.4% | 100.00% |
| 1.0% | 240 | 10 | 3806206 | +4.3% | 100.00% |
| 5.0% | none | 0 | 3650956 | +0.0% | 3.59% |
| 5.0% | 200 | 22 | 4056856 | +11.1% | 100.00% |
| 5.0% | 220 | 26 | 4089706 | +12.0% | 100.00% |
| 5.0% | 220 | 30 | 4157206 | +13.9% | 100.00% |
