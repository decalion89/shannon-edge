# Fuzzing

Coverage-guided fuzzing (libFuzzer via `cargo fuzz`, nightly toolchain) of
every decoder and of losslessness:

| Target | Property |
|---|---|
| `decompress` | any byte string: `Ok` or `Err`, never a panic, hang, out-of-bounds access or unbounded allocation |
| `packet_fast` | a fast-profile receiver fed arbitrary payloads (plain and indexed): never a panic; decoded packets have the session's length |
| `packet_v2` | the same for packet profile v2 |
| `flight` | the flight profile's frame decoder: never a panic; samples fit the sample width |
| `roundtrip` | arbitrary data comes back bit-exact through the file format and both packet profiles |

    rustup toolchain install nightly --profile minimal
    cargo install cargo-fuzz --locked
    cargo +nightly fuzz run -O decompress -- -max_total_time=600 -rss_limit_mb=2048 -max_len=4096

CI runs each target for 60 s on every pull request.

## Findings

- `decompress` (first minute): a header announcing ~4 GB over a few payload
  bytes made the decoder reserve the announced size before decoding
  anything. Fixed: the declared length no longer drives allocation, and the
  decoder stops as soon as it reads more than `coder::MAX_OVERRUN` bytes past
  the payload, which no valid stream does (`docs/FORMAT.md`, Integrity).
  Regression test: `a_lying_length_costs_neither_memory_nor_time`.
