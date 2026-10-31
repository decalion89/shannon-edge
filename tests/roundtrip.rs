//! End-to-end guarantees: every input comes back bit-for-bit, random data
//! never grows by more than the header, and corruption is always detected.

use shannon_edge::{
    compress, compress_with_dictionary, compress_with_model, decompress,
    decompress_with_dictionary, decompress_with_model, decompress_with_threads, Error, Options,
    PrimedModel, Session, HEADER_LEN,
};

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
        let packed = compress(
            &data,
            &Options {
                mem_bits: m,
                ..Options::default()
            },
        );
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

// ---------------------------------------------------------------------------
// Parallel block mode
// ---------------------------------------------------------------------------

fn blocked(block_size: usize, threads: usize) -> Options {
    Options {
        block_size,
        threads,
        ..Options::default()
    }
}

#[test]
fn block_mode_roundtrips_and_ignores_thread_count() {
    let data = sample_text();
    let reference = compress(&data, &blocked(8192, 1));
    assert_eq!(reference[5], 2, "expected the multi-block method");
    for threads in [0, 2, 3, 8] {
        assert_eq!(
            compress(&data, &blocked(8192, threads)),
            reference,
            "output must not depend on the thread count ({threads})"
        );
    }
    for threads in [0, 1, 3] {
        assert_eq!(decompress_with_threads(&reference, threads).unwrap(), data);
    }
}

#[test]
fn block_mode_edge_sizes() {
    let data = sample_text();
    for (bs, n) in [
        (1, 300),
        (7, 3000),
        (4096, 20_000),
        (19_999, 20_000),
        (20_000, 20_000),
        (20_001, 20_000),
    ] {
        let packed = compress(&data[..n], &blocked(bs, 0));
        assert_eq!(decompress(&packed).unwrap(), &data[..n], "block size {bs}");
    }
}

#[test]
fn block_mode_random_data_never_expands_beyond_header() {
    let mut rng = Rng(77);
    let data = rng.bytes(100_000);
    let packed = compress(&data, &blocked(10_000, 0));
    assert!(packed.len() <= data.len() + HEADER_LEN);
    assert_eq!(decompress(&packed).unwrap(), data);
}

#[test]
fn block_mode_corruption_is_detected() {
    let data = sample_text();
    let packed = compress(&data, &blocked(8192, 0));
    let mut rng = Rng(11);
    for _ in 0..50 {
        let mut bad = packed.clone();
        let i = HEADER_LEN + (rng.next() as usize % (bad.len() - HEADER_LEN));
        bad[i] ^= 1 << (rng.next() % 8);
        if let Ok(out) = decompress(&bad) {
            assert_eq!(out, data, "corruption produced wrong output");
        }
    }
    // Truncation anywhere is an error, never a panic or wrong output.
    for cut in [
        HEADER_LEN,
        HEADER_LEN + 3,
        HEADER_LEN + 9,
        packed.len() / 2,
        packed.len() - 1,
    ] {
        assert!(decompress(&packed[..cut]).is_err(), "cut at {cut}");
    }
}

const GOLDEN_V1_BLOCKS: &[u8] = include_bytes!("fixtures/golden-v1-blocks.sedge");

#[test]
fn golden_v1_block_stream_is_stable() {
    let packed = compress(&sample_text(), &blocked(8192, 0));
    if std::env::var_os("SEDGE_BLESS").is_some() {
        std::fs::write("tests/fixtures/golden-v1-blocks.sedge", &packed).unwrap();
        return;
    }
    assert_eq!(packed, GOLDEN_V1_BLOCKS, "multi-block format is not stable");
    assert_eq!(decompress(GOLDEN_V1_BLOCKS).unwrap(), sample_text());
}

// ---------------------------------------------------------------------------
// Shared-knowledge dictionaries
// ---------------------------------------------------------------------------

/// A dictionary and a "message" drawn from the same kind of text.
fn dict_and_message() -> (Vec<u8>, Vec<u8>) {
    let text = sample_text();
    (text[..40_000].to_vec(), text[40_000..42_000].to_vec())
}

#[test]
fn dictionary_roundtrips_and_helps() {
    let (dict, msg) = dict_and_message();
    let plain = compress(&msg, &Options::default());
    let primed = compress_with_dictionary(&msg, &dict, &Options::default());
    assert_eq!(decompress_with_dictionary(&primed, &dict, 0).unwrap(), msg);
    assert!(
        primed.len() * 10 < plain.len() * 8,
        "dictionary should save >20%: {} vs {}",
        primed.len(),
        plain.len()
    );
}

#[test]
fn empty_dictionary_is_plain_compression() {
    let (_, msg) = dict_and_message();
    assert_eq!(
        compress_with_dictionary(&msg, &[], &Options::default()),
        compress(&msg, &Options::default())
    );
}

#[test]
fn missing_or_wrong_dictionary_is_rejected() {
    let (dict, msg) = dict_and_message();
    let primed = compress_with_dictionary(&msg, &dict, &Options::default());
    assert!(matches!(
        decompress(&primed),
        Err(Error::DictionaryRequired { len: 40_000, .. })
    ));
    let mut wrong = dict.clone();
    wrong[123] ^= 1;
    assert!(matches!(
        decompress_with_dictionary(&primed, &wrong, 0),
        Err(Error::DictionaryMismatch { .. })
    ));
    assert!(matches!(
        decompress_with_dictionary(&primed, &dict[1..], 0),
        Err(Error::DictionaryMismatch { .. })
    ));
}

#[test]
fn dictionary_is_ignored_by_plain_streams() {
    let (dict, msg) = dict_and_message();
    let plain = compress(&msg, &Options::default());
    assert_eq!(decompress_with_dictionary(&plain, &dict, 0).unwrap(), msg);
}

#[test]
fn dictionary_with_random_data_still_never_expands_beyond_header() {
    let (dict, _) = dict_and_message();
    let data = Rng(3).bytes(5_000);
    let packed = compress_with_dictionary(&data, &dict, &Options::default());
    assert!(packed.len() <= data.len() + HEADER_LEN);
    assert_eq!(decompress_with_dictionary(&packed, &dict, 0).unwrap(), data);
}

#[test]
fn dictionary_in_block_mode() {
    let text = sample_text();
    let (dict, data) = (&text[..10_000], &text[10_000..]);
    let reference = compress_with_dictionary(data, dict, &blocked(8192, 1));
    assert_eq!(reference[5], 2);
    assert_eq!(
        compress_with_dictionary(data, dict, &blocked(8192, 3)),
        reference
    );
    assert_eq!(
        decompress_with_dictionary(&reference, dict, 0).unwrap(),
        data
    );
    assert!(decompress(&reference).is_err());
}

const GOLDEN_V1_DICT: &[u8] = include_bytes!("fixtures/golden-v1-dict.sedge");

#[test]
fn golden_v1_dictionary_stream_is_stable() {
    let (dict, msg) = dict_and_message();
    let packed = compress_with_dictionary(&msg, &dict, &Options::default());
    if std::env::var_os("SEDGE_BLESS").is_some() {
        std::fs::write("tests/fixtures/golden-v1-dict.sedge", &packed).unwrap();
        return;
    }
    assert_eq!(packed, GOLDEN_V1_DICT, "dictionary format is not stable");
    assert_eq!(
        decompress_with_dictionary(GOLDEN_V1_DICT, &dict, 0).unwrap(),
        msg
    );
}

// ---------------------------------------------------------------------------
// Primed models (snapshots): a cache, never a different format
// ---------------------------------------------------------------------------

#[test]
fn primed_model_streams_interoperate_with_the_raw_dictionary() {
    let (dict, msg) = dict_and_message();
    let model = PrimedModel::new(&dict, &Options::default());
    let via_model = compress_with_model(&msg, &model, &Options::default());
    let via_dict = compress_with_dictionary(&msg, &dict, &Options::default());
    assert_eq!(decompress_with_model(&via_model, &model, 0).unwrap(), msg);
    assert_eq!(
        decompress_with_dictionary(&via_model, &dict, 0).unwrap(),
        msg
    );
    assert_eq!(decompress_with_model(&via_dict, &model, 0).unwrap(), msg);
    assert!(matches!(
        decompress(&via_model),
        Err(Error::DictionaryRequired { .. })
    ));
}

#[test]
fn primed_model_matches_dictionary_bytes_at_the_same_memory_level() {
    // When both paths use the same table size, a snapshot must give the very
    // same stream as re-reading the dictionary. Capping mem_bits at 18 makes
    // both paths pick 18 here.
    let (dict, msg) = dict_and_message();
    let opts = Options {
        mem_bits: 18,
        ..Options::default()
    };
    let model = PrimedModel::new(&dict, &opts);
    assert_eq!(model.mem_bits(), 18);
    let via_dict = compress_with_dictionary(&msg, &dict, &opts);
    assert_eq!(via_dict[6], 18);
    assert_eq!(compress_with_model(&msg, &model, &opts), via_dict);
}

#[test]
fn saved_model_loads_and_behaves_identically() {
    let (dict, msg) = dict_and_message();
    let model = PrimedModel::new(&dict, &Options::default());
    let bytes = model.to_bytes();
    let loaded = PrimedModel::from_bytes(&bytes).unwrap();
    assert_eq!(loaded.dictionary(), &dict[..]);
    assert_eq!(loaded.mem_bits(), model.mem_bits());
    let a = compress_with_model(&msg, &model, &Options::default());
    let b = compress_with_model(&msg, &loaded, &Options::default());
    assert_eq!(a, b);
    assert_eq!(loaded.to_bytes(), bytes, "save/load must be a fixed point");
}

#[test]
fn damaged_model_files_are_rejected() {
    let (dict, _) = dict_and_message();
    let bytes = PrimedModel::new(&dict[..5_000], &Options::default()).to_bytes();
    assert!(matches!(PrimedModel::from_bytes(&[]), Err(Error::BadModel)));
    assert!(matches!(
        PrimedModel::from_bytes(&bytes[..bytes.len() - 1]),
        Err(Error::BadModel)
    ));
    let mut rng = Rng(8);
    for _ in 0..20 {
        let mut bad = bytes.clone();
        let i = rng.next() as usize % bad.len();
        bad[i] ^= 1 << (rng.next() % 8);
        assert!(PrimedModel::from_bytes(&bad).is_err(), "flip at {i}");
    }
}

#[test]
fn primed_model_in_block_mode() {
    let text = sample_text();
    let (dict, data) = (&text[..10_000], &text[10_000..]);
    let model = PrimedModel::new(dict, &Options::default());
    let one = compress_with_model(data, &model, &blocked(8192, 1));
    assert_eq!(one[5], 2);
    assert_eq!(compress_with_model(data, &model, &blocked(8192, 4)), one);
    assert_eq!(decompress_with_model(&one, &model, 0).unwrap(), data);
    assert_eq!(decompress_with_dictionary(&one, dict, 0).unwrap(), data);
}

#[test]
fn wrong_model_is_rejected() {
    let (dict, msg) = dict_and_message();
    let packed = compress_with_dictionary(&msg, &dict, &Options::default());
    let other = PrimedModel::new(&dict[..20_000], &Options::default());
    assert!(matches!(
        decompress_with_model(&packed, &other, 0),
        Err(Error::DictionaryMismatch { .. })
    ));
}

// ---------------------------------------------------------------------------
// In-place messages with a journal: same bytes, model restored exactly
// ---------------------------------------------------------------------------

fn messages() -> Vec<Vec<u8>> {
    let text = sample_text();
    let mut rng = Rng(21);
    let mut out: Vec<Vec<u8>> = (0..12)
        .map(|i| {
            let start = 40_000 + i * 700;
            text[start..start + 200 + (rng.next() % 500) as usize].to_vec()
        })
        .collect();
    out.push(Vec::new());
    out.push(vec![b'x'; 3]);
    out.push(rng.bytes(800)); // incompressible: stored
    out
}

#[test]
fn compress_message_matches_compress_with_model_and_restores_the_model() {
    let (dict, _) = dict_and_message();
    let mut model = PrimedModel::new(&dict, &Options::default());
    let pristine = model.to_bytes();
    for msg in messages() {
        let reference = compress_with_model(&msg, &model, &Options::default());
        let fast = model.compress_message(&msg, &Options::default());
        assert_eq!(fast, reference, "message of {} bytes", msg.len());
        assert!(model.to_bytes() == pristine, "model changed after compress");
        assert_eq!(model.decompress_message(&fast).unwrap(), msg);
        assert!(
            model.to_bytes() == pristine,
            "model changed after decompress"
        );
        assert_eq!(decompress_with_dictionary(&fast, &dict, 0).unwrap(), msg);
    }
}

#[test]
fn decompress_message_rejects_corruption_and_still_restores_the_model() {
    let (dict, msg) = dict_and_message();
    let mut model = PrimedModel::new(&dict, &Options::default());
    let pristine = model.to_bytes();
    let packed = model.compress_message(&msg, &Options::default());
    let mut rng = Rng(4);
    for _ in 0..20 {
        let mut bad = packed.clone();
        let i = HEADER_LEN + 8 + (rng.next() as usize % (bad.len() - HEADER_LEN - 8));
        bad[i] ^= 1 << (rng.next() % 8);
        if let Ok(out) = model.decompress_message(&bad) {
            assert_eq!(out, msg);
        }
        assert!(model.to_bytes() == pristine);
    }
    assert_eq!(model.decompress_message(&packed).unwrap(), msg);
}

#[test]
fn decompress_message_falls_back_for_other_streams() {
    let (dict, msg) = dict_and_message();
    let mut model = PrimedModel::new(&dict, &Options::default());
    // Raw-dictionary stream with a different memory level.
    let other = compress_with_dictionary(
        &msg,
        &dict,
        &Options {
            mem_bits: 16,
            ..Options::default()
        },
    );
    assert_eq!(model.decompress_message(&other).unwrap(), msg);
    // Plain and multi-block streams.
    assert_eq!(
        model
            .decompress_message(&compress(&msg, &Options::default()))
            .unwrap(),
        msg
    );
    let big = sample_text();
    let blocks = compress_with_model(&big, &model, &blocked(8192, 0));
    assert_eq!(model.decompress_message(&blocks).unwrap(), big);
}

// ---------------------------------------------------------------------------
// Sessions: both sides keep learning, and stay in step
// ---------------------------------------------------------------------------

/// A stream of similar records, like events from one device.
fn event_stream(n: usize) -> Vec<Vec<u8>> {
    let mut rng = Rng(31);
    (0..n)
        .map(|i| {
            format!(
                "{{\"device\":\"sensor-{}\",\"seq\":{},\"temp\":{}.{},\"status\":\"{}\"}}",
                rng.next() % 4,
                i,
                15 + rng.next() % 10,
                rng.next() % 10,
                if rng.next() % 5 == 0 { "warn" } else { "ok" }
            )
            .into_bytes()
        })
        .collect()
}

#[test]
fn session_roundtrips_and_learns() {
    let opts = Options {
        mem_bits: 18,
        ..Options::default()
    };
    let (mut tx, mut rx) = (Session::new(&opts), Session::new(&opts));
    let events = event_stream(300);
    let mut sizes = Vec::new();
    for e in &events {
        let packed = tx.compress(e);
        sizes.push(packed.len());
        assert_eq!(&rx.decompress(&packed).unwrap(), e);
    }
    assert_eq!(rx.messages(), 300);
    // Compare payloads: every frame carries ~8 fixed bytes (kind, length,
    // sequence, CRC-32) whatever the model knows.
    let payload = |s: &[usize]| s.iter().map(|n| n - 8).sum::<usize>();
    let (early, late) = (payload(&sizes[..20]), payload(&sizes[280..]));
    assert!(
        late * 2 < early,
        "later payloads should be much smaller: {early} vs {late} bytes"
    );
    assert!(sizes[280..].iter().all(|&n| n < 16), "{:?}", &sizes[280..]);
}

#[test]
fn session_detects_loss_reordering_and_corruption_without_desync() {
    let opts = Options {
        mem_bits: 18,
        ..Options::default()
    };
    let (mut tx, mut rx) = (Session::new(&opts), Session::new(&opts));
    let events = event_stream(40);
    let packed: Vec<Vec<u8>> = events.iter().map(|e| tx.compress(e)).collect();
    for (i, p) in packed.iter().enumerate() {
        if i + 1 < packed.len() {
            assert!(matches!(
                rx.decompress(&packed[i + 1]),
                Err(Error::SessionOutOfSync { .. })
            ));
        }
        // Corrupt a payload byte: rejected (and the receiver unchanged), or,
        // if that byte happened not to matter, decoded correctly.
        let mut bad = p.clone();
        let at = 8 + (i % (bad.len() - 8));
        bad[at] ^= 0x10;
        match rx.decompress(&bad) {
            Ok(out) => assert_eq!(out, events[i], "message {i}"),
            Err(_) => assert_eq!(rx.decompress(p).unwrap(), events[i], "message {i}"),
        }
    }
}

#[test]
fn session_handles_incompressible_and_empty_messages() {
    let opts = Options {
        mem_bits: 16,
        ..Options::default()
    };
    let (mut tx, mut rx) = (Session::new(&opts), Session::new(&opts));
    let mut rng = Rng(9);
    let msgs = vec![
        b"hello hello hello".to_vec(),
        rng.bytes(500),
        Vec::new(),
        b"hello again hello".to_vec(),
    ];
    for m in &msgs {
        assert_eq!(&rx.decompress(&tx.compress(m)).unwrap(), m);
    }
}

#[test]
fn sessions_with_different_origins_do_not_mix() {
    let (dict, msg) = dict_and_message();
    let model = PrimedModel::new(&dict, &Options::default());
    let mut primed = Session::from_model(model.clone());
    let packed = primed.compress(&msg);
    // A receiver that started without the dictionary cannot decode it, and
    // stays usable.
    let mut fresh = Session::from_model(PrimedModel::new(&dict[..1000], &Options::default()));
    assert!(fresh.decompress(&packed).is_err());
    assert_eq!(fresh.messages(), 0);
    let mut rx = Session::from_model(model);
    assert_eq!(rx.decompress(&packed).unwrap(), msg);
    // A session message is not a plain stream, and vice versa.
    assert!(decompress(&packed).is_err());
    assert!(matches!(
        rx.decompress(&compress(&msg, &Options::default())),
        Err(Error::NotThisSession)
    ));
}

#[test]
fn session_history_is_bounded_and_stays_in_sync() {
    let opts = Options {
        mem_bits: 18,
        ..Options::default()
    };
    let limit = 64 << 10;
    let mut tx = Session::new(&opts).with_history_limit(limit);
    let mut rx = Session::new(&opts).with_history_limit(limit);
    let text = sample_text();
    let mut rng = Rng(77);
    // ~400 KiB of records: the window slides several times.
    for i in 0..800 {
        let start = (rng.next() as usize) % (text.len() - 600);
        let mut rec = text[start..start + 500].to_vec();
        rec.extend_from_slice(format!(" #{i}").as_bytes());
        let frame = tx.compress(&rec);
        assert_eq!(rx.decompress(&frame).unwrap(), rec, "record {i}");
        assert!(tx.history_len() <= 2 * limit + 600);
        assert_eq!(tx.history_len(), rx.history_len());
    }
}
