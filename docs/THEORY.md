# Theory: where the edge is, and why

This project exists to push lossless compression as close as possible to its
true limit. To do that seriously, we first have to be precise about what that
limit is. This document states it, proves the part that is provable on one
page, and explains the one lever that genuinely moves it.

## 1. Two kinds of "impossible"

| Kind | Examples | Can it fall? |
|---|---|---|
| **Engineering** — missing technology, money or ideas | Powered flight, the Moon, real-time 8K video on a phone | Yes, and it usually does |
| **Logical** — contradicts counting or definitions | A square circle, 4 objects in 3 boxes with no box holding two | Never, with any technology |

"Compress **every** file to 1% of its size, losslessly" is of the second kind.
"Compress the files people actually create far better and faster than today"
is of the first kind. This project is about the second sentence.

## 2. No lossless compressor can shrink every file

**Claim.** For any `n ≥ 1`, no lossless compressor maps every `n`-bit file to
a shorter one.

**Proof.** Lossless means decompression recovers the input exactly, so the
compressor must be injective: two different inputs can never produce the
same output. There are `2^n` inputs of length `n`. The number of outputs
shorter than `n` bits is

    2^0 + 2^1 + ... + 2^(n-1) = 2^n - 1  <  2^n.

`2^n` inputs cannot map injectively into `2^n - 1` outputs (pigeonhole
principle). ∎

**The quantitative version is much stronger.** At most `2^(k+1) - 1` inputs
can be mapped to outputs of at most `k` bits. So the fraction of `n`-bit
files that *any* lossless method can compress to 1% (`k = n/100`) is below

    2^(n/100 + 1) / 2^n  =  2^(1 - 0.99·n).

For a single kilobyte (`n = 8192`) that is below `2^-8100` — a number with
about 2,400 zeros after the decimal point. For a typical file, compression to
1% is not "hard"; it is excluded by counting.

**Consequence: every compressor expands some inputs.** If a method shrinks
some files, it must grow others. The best possible worst case is "grow by a
constant number of bytes" — which is what `sedge` guarantees: if modelling
does not help, the data is stored verbatim behind a 20-byte header (see the
test `random_data_never_expands_beyond_header`).

## 3. Shannon: the limit is the information, not the bytes

For data drawn from a source with probability distribution `P`, Shannon's
source coding theorem (1948) says the expected compressed length of a
lossless code is at least the entropy

    H(P) = -Σ P(x) · log2 P(x)   bits,

and that codes exist that come within a fraction of a bit of it. Text,
spreadsheets, logs and source code have entropy far below 8 bits per byte —
that gap is what compression harvests. Random bytes, encrypted data and
already-compressed files (JPEG, H.265, ZIP) sit at or near 8 bits per byte:
there is nothing left to harvest.

## 4. Compression is prediction

`sedge` never stores the data directly. Before each bit it predicts
`p = P(next bit = 1)`, and an arithmetic coder then spends

    -log2(p)       bits if the bit is 1,
    -log2(1 - p)   bits if the bit is 0.

The total size of the output is therefore the model's **cumulative surprise**
(its log-loss) over the file, plus a few bytes. Halve your surprise, halve
your file. Every improvement in compression is an improvement in prediction,
and vice versa — which is why the best compressors and the best language
models are, mathematically, the same kind of object.

The decoder runs the identical model on the identical history, so it makes
the identical predictions and can invert each step. The model is never
transmitted; it is *re-learned* during decompression.

## 5. The lever that does move the edge: shared knowledge

The entropy above is relative to what the receiver already knows. If sender
and receiver share some knowledge `K` (a dictionary, a corpus, a trained
model), the relevant limit becomes the conditional entropy

    H(X | K)  ≤  H(X),

and it can be dramatically lower. Sending "the third movement of Beethoven's
Fifth, the 1963 Karajan recording" costs a few bytes *if the receiver already
has the recording*. Nothing is violated: the information was paid for once,
when `K` was distributed, and is reused for every message afterwards.

This is the honest version of the "1%" dream:

* For one arbitrary file with no shared context — impossible, by Section 2.
* For the enormous stream of *similar* data that real systems store and send
  (logs, backups, documents, code, telemetry), with a well-trained shared
  model — single-digit percentages are realistic, and the remaining frontier
  is speed and cost.

## 6. What this means for the project

1. Measure everything against the real limit (bits per byte), never against a
   marketing number.
2. Get closer to that limit with better prediction (more and better context
   models, smarter mixing, learned models).
3. Make that prediction fast enough to use everywhere.
4. Lower the limit itself with shared knowledge, honestly accounted for.

See [`ROADMAP.md`](../ROADMAP.md) for how.
