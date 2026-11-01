# Packet profile under packet loss: Venus Express

Data: the Venus Express housekeeping packets of the CCSDS 124 test vectors
(151,200 packets of 90 bytes). The first 10% (15,120 packets) play the
spacecraft's history and are used only to prime the model ("Primed");
the remaining 136,080 packets (12,247,200 bytes) are the test link.
Tables 2^16 (~1.3 MiB). Loss is i.i.d. per packet (`Rng(0x5eed + loss)`);
"decoded" is the fraction of all test packets the receiver recovers, every
one verified byte for byte. At 1% loss, about 99% is the ceiling for packets
sent once; in the "sent twice" columns a key packet is lost only if both
copies are (with K=1 that duplicates every packet, hence more than 99%).

Produced by `cargo run --release --example packet_robust -- venus-express.ccsds 90 16`.

| Key interval K | Epoch E | Primed | Test bytes | Decoded at 0.1% loss | at 1% loss | Key packets sent twice: bytes | decoded at 1% loss |
|---:|---:|---|---:|---:|---:|---:|---:|
| 1 | none | no | 3109927 | 0.36% | 0.03% | 6219854 | 7.57% |
| 1 | none | yes | 3108861 | 0.36% | 0.03% | 6217722 | 7.57% |
| 1 | 1000 | no | 3183429 | 64.33% | 9.11% | 6366858 | 94.22% |
| 1 | 1000 | yes | 3193645 | 64.33% | 9.11% | 6387290 | 94.22% |
| 1 | 100 | no | 3620803 | 95.13% | 63.14% | 7241606 | 99.34% |
| 1 | 100 | yes | 3560301 | 95.13% | 63.14% | 7120602 | 99.34% |
| 1 | 10 | no | 5631335 | 99.46% | 94.72% | 11262670 | 99.94% |
| 1 | 10 | yes | 5269770 | 99.46% | 94.72% | 10539540 | 99.94% |
| 4 | none | no | 3862294 | 1.34% | 0.03% | 4735957 | 12.03% |
| 4 | none | yes | 3832108 | 1.34% | 0.03% | 4704203 | 12.03% |
| 4 | 1024 | no | 4000319 | 84.61% | 34.63% | 4926735 | 97.83% |
| 4 | 1024 | yes | 3891806 | 84.61% | 34.63% | 4814577 | 97.83% |
| 16 | none | no | 4360916 | 9.94% | 0.36% | 4603097 | 80.91% |
| 16 | none | yes | 4313870 | 9.94% | 0.36% | 4554916 | 80.91% |
| 16 | 1024 | no | 4632759 | 97.87% | 73.28% | 4910879 | 98.72% |
| 16 | 1024 | yes | 4460445 | 97.87% | 73.28% | 4737620 | 98.72% |
| 64 | none | no | 5260585 | 99.89% | 3.17% | 5328885 | 99.04% |
| 64 | none | yes | 5131325 | 99.89% | 3.17% | 5198904 | 99.04% |
| 64 | 1024 | no | 5702952 | 99.89% | 90.97% | 5795128 | 99.04% |
| 64 | 1024 | yes | 5298696 | 99.89% | 90.97% | 5389467 | 99.04% |

## CCSDS 124 on the same 136,080 test packets

Best of the parameter sweep of `bench/ccsds124.py` for each robustness
level, round trip verified (open C implementation, tanagraspace/ccsds124):

| CCSDS 124 robustness | Best configuration | Bytes |
|---|---|---:|
| R=0 | pt=14, ft=10⁵, rt=10⁶ | 4,772,219 |
| R=1 | pt=20, ft=10⁵, rt=10⁶ | 4,976,442 |
| R=2 | pt=20, ft=10⁵, rt=10⁶ | 5,123,900 |
| R=3 | pt=50, ft=10⁵, rt=10⁶ | 5,241,460 |

CCSDS 124 with robustness R is designed to keep decoding after up to R
consecutive lost packets. Its decoder was not run under simulated loss here,
so its decoded fractions are not measured.

## Reading

* Without loss, the packet profile is −34.9% vs CCSDS 124 R=0 on this split
  (3,108,861 vs 4,772,219 bytes). But one lost packet desynchronises it for
  good: 0.03% of the packets decoded at 1% loss.
* **Epochs alone** (return to a common, optionally primed, origin every E
  packets) are a weak fix: E=100 costs +15% and still loses 37% of the
  packets at 1% loss; E=10 decodes 94.7% at +70% size. Priming the origin
  with history helps only 2–6%. Negative result.
* **Key packets** (`with_key_interval(K)`): only every K-th packet teaches
  the model and becomes the reference; the others are coded with the model
  frozen, so losing one affects nothing else. Sending key packets twice
  makes the rest of the link loss-tolerant:
  * K=16, E=1024, primed, key packets twice: **4,737,620 bytes, 98.72%
    decoded at 1% loss** — **−4.8% vs CCSDS 124 R=1** and −7.5% vs R=2.
  * K=64, primed, key packets twice: 5,198,904 bytes, 99.04% (every
    received packet decoded) — +4.5% vs R=1.
* So robustness costs most of the advantage: the ~35% gain at R=0 shrinks to
  ~5–8% at the robustness level CCSDS 124 R=1/R=2 aims for. The frozen model
  is the price: a non-key packet is predicted from a reference up to K
  packets old by a model that learns from 1/K of the data.
