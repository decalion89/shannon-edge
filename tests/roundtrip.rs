//! End-to-end guarantees: every input comes back bit-for-bit, random data
//! never grows by more than the header, and corruption is always detected.

use shannon_edge::{compress, decompress, Error, Options, HEADER_LEN};

/// Small deterministic PRNG (xorshift64*) so tests need no dependencies.
struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
    fn bytes(&mut self, n: usize) -> Vec<u8> {
        (0..n).map(|_| (self.next() >> 56) as u8).collect()
    }
}

fn roundtrip(data: &[u8]) -> Vec<u8> {
    let packed = compress(data, &Options::default());
    let back = decompress(&packed).expect("decompression failed");
    assert_eq!(back, data, "round-trip mismatch (len {})", data.len());
    packed
}

fn sample_text() -> Vec<u8> {
    let words = [
        "the",
        "information",
        "entropy",
        "of",
        "a",
        "source",
        "is",
        "the",
        "limit",
        "below",
        "which",
        "no",
        "lossless",
        "code",
        "can",
        "go",
        "prediction",
        "is",
        "compression",
    ];
    let mut rng = Rng(42);
    let mut s = String::new();
    while s.len() < 50_000 {
        s.push_str(words[(rng.next() % words.len() as u64) as usize]);
        s.push(if rng.next() % 9 == 0 { '\n' } else { ' ' });
    }
    s.into_bytes()
}

#[test]
fn empty_input() {
    let packed = roundtrip(b"");
    assert_eq!(packed.len(), HEADER_LEN);
}

#[test]
fn every_single_byte() {
    for b in 0..=255u8 {
        roundtrip(&[b]);
    }
}

#[test]
fn short_inputs() {
    let mut rng = Rng(7);
    for n in 0..64 {
        roundtrip(&rng.bytes(n));
        roundtrip(&vec![b'a'; n]);
    }
}

#[test]
fn long_runs_compress_extremely_well() {
    let data = vec![0u8; 1 << 20];
    let packed = roundtrip(&data);
    // 12-bit probabilities cost at least -log2(4095/4096) ≈ 0.00035 bits per
    // bit, a floor of ~370 bytes for 8 Mi bits. See ROADMAP (coder precision).
    assert!(
        packed.len() < 500,
        "1 MiB of zeros -> {} bytes",
        packed.len()
    );
}

#[test]
fn text_beats_two_bits_per_byte() {
    let data = sample_text();
    let packed = roundtrip(&data);
    let bpb = 8.0 * packed.len() as f64 / data.len() as f64;
    assert!(bpb < 2.0, "{bpb:.3} bits/byte");
}

#[test]
fn repeated_blocks_are_found_by_the_match_model() {
    let mut rng = Rng(99);
    let block = rng.bytes(20_000);
    let data: Vec<u8> = block.iter().chain(&block).chain(&block).copied().collect();
    let packed = roundtrip(&data);
    // The first copy is incompressible; the two repeats should be nearly free.
    assert!(packed.len() < 21_500, "{} bytes", packed.len());
}

/// The pigeonhole principle in action: random data cannot be compressed, and
/// the stored fallback guarantees it never grows by more than the header.
#[test]
fn random_data_never_expands_beyond_header() {
    let mut rng = Rng(2026);
    for &n in &[1usize, 100, 10_000, 200_000] {
        let data = rng.bytes(n);
        let packed = roundtrip(&data);
        assert!(packed.len() <= n + HEADER_LEN);
    }
}

#[test]
fn all_byte_values_and_binary_structure() {
    let mut data = Vec::new();
    for i in 0..40_000u32 {
        data.extend_from_slice(&(i.wrapping_mul(2_654_435_761) >> 7).to_le_bytes());
        data.push((i % 256) as u8);
    }
    roundtrip(&data);
}

#[test]
fn every_memory_level_roundtrips() {
    let data = sample_text();
    for m in 16..=24 {
        let packed = compress(&data, &Options { mem_bits: m });
        assert_eq!(decompress(&packed).unwrap(), data, "mem level {m}");
    }
}

#[test]
fn corruption_is_detected_not_silently_accepted() {
    let data = sample_text();
    let packed = compress(&data, &Options::default());
    let mut rng = Rng(5);
    for _ in 0..50 {
        let mut bad = packed.clone();
        let i = HEADER_LEN + (rng.next() as usize % (bad.len() - HEADER_LEN));
        bad[i] ^= 1 << (rng.next() % 8);
        match decompress(&bad) {
            Err(Error::ChecksumMismatch { .. }) => {}
            Ok(out) => assert_eq!(out, data, "corruption produced wrong output"),
            Err(e) => panic!("unexpected error {e:?}"),
        }
    }
}

#[test]
fn malformed_headers_are_rejected() {
    assert_eq!(decompress(b""), Err(Error::Truncated));
    assert_eq!(decompress(b"SEDG"), Err(Error::Truncated));
    assert_eq!(decompress(b"NOPE0000000000000000"), Err(Error::BadMagic));
    let mut packed = compress(b"hello hello hello hello", &Options::default());
    packed[4] = 99;
    assert_eq!(decompress(&packed), Err(Error::UnsupportedVersion(99)));
    let mut packed = compress(&sample_text(), &Options::default());
    packed[5] = 7;
    assert_eq!(decompress(&packed), Err(Error::UnknownMethod(7)));
    let mut stored = compress(&[1, 2, 3], &Options::default());
    stored.truncate(HEADER_LEN + 1);
    assert_eq!(decompress(&stored), Err(Error::Truncated));
}

// ---------------------------------------------------------------------------
// Format stability: a stream written by format v1 must decode forever, and
// compressing the same input must produce the same bytes on every platform.
// If an intentional model change breaks this test, bump FORMAT_VERSION and
// keep a decoder for v1 — never silently change what v1 means.
// ---------------------------------------------------------------------------

const GOLDEN_V1: &[u8] = include_bytes!("fixtures/golden-v1.sedge");

#[test]
fn golden_v1_stream_decodes() {
    assert_eq!(decompress(GOLDEN_V1).unwrap(), sample_text());
}

#[test]
fn golden_v1_stream_is_reproduced_exactly() {
    let packed = compress(&sample_text(), &Options::default());
    if std::env::var_os("SEDGE_BLESS").is_some() {
        std::fs::write("tests/fixtures/golden-v1.sedge", &packed).unwrap();
        return;
    }
    assert_eq!(
        packed, GOLDEN_V1,
        "compressed bytes changed: the v1 format/model is not stable"
    );
}
