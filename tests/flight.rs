//! Flight profile: round trips, determinism and robustness.

use shannon_edge::flight::FlightSession;

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

/// A plausible housekeeping channel: slow drift, a periodic component,
/// sensor noise, and occasional mode switches.
fn telemetry(n: usize, bits: u32, seed: u64) -> Vec<u16> {
    let mut rng = Rng(seed);
    let max = (1u32 << bits) - 1;
    let mut level = max as f64 / 2.0;
    (0..n)
        .map(|i| {
            if rng.next() % 2000 == 0 {
                level = (rng.next() % (max as u64 + 1)) as f64;
            }
            let wave = (i as f64 / 50.0).sin() * max as f64 * 0.05;
            let noise = (rng.next() % 7) as f64 - 3.0;
            (level + wave + noise).clamp(0.0, max as f64) as u16
        })
        .collect()
}

fn roundtrip(samples: &[u16], bits: u32, table_bits: u32, packet: usize) -> usize {
    let (mut tx, mut rx) = (
        FlightSession::new(bits, table_bits),
        FlightSession::new(bits, table_bits),
    );
    let mut total = 0;
    for p in samples.chunks(packet) {
        let frame = tx.compress(p);
        total += frame.len();
        assert_eq!(rx.decompress(&frame).unwrap(), p);
    }
    total
}

#[test]
fn roundtrips_and_compresses_telemetry() {
    for &bits in &[1, 7, 12, 16] {
        let s = telemetry(20_000, bits, bits as u64);
        let size = roundtrip(&s, bits, 14, 256);
        let raw = s.len() * bits as usize / 8;
        assert!(
            size < raw / 2 || bits == 1,
            "{bits} bits: {size} vs raw {raw}"
        );
    }
}

#[test]
fn full_range_random_and_edge_packets() {
    let mut rng = Rng(5);
    let s: Vec<u16> = (0..5_000).map(|_| rng.next() as u16).collect();
    roundtrip(&s, 16, 12, 256);
    roundtrip(&[0, 65535, 0, 65535, 1, 65534], 16, 12, 1);
    roundtrip(&[], 8, 12, 1);
    // Empty packets in the middle of a stream.
    let (mut tx, mut rx) = (FlightSession::new(8, 12), FlightSession::new(8, 12));
    for p in [&[1u16, 2, 3][..], &[], &[4, 5], &[]] {
        assert_eq!(rx.decompress(&tx.compress(p)).unwrap(), p);
    }
}

#[test]
#[should_panic(expected = "does not fit")]
fn out_of_range_sample_is_rejected() {
    FlightSession::new(8, 12).compress(&[256]);
}

#[test]
fn garbage_frames_never_panic_or_hang() {
    let mut rng = Rng(77);
    for len in 0..64 {
        let frame: Vec<u8> = (0..len).map(|_| rng.next() as u8).collect();
        let _ = FlightSession::new(12, 12).decompress(&frame);
    }
    assert!(FlightSession::new(12, 12)
        .decompress(&[0xff, 0xff, 0xff, 0xff, 0x7f])
        .is_err());
}

/// The flight format must not change silently: both ends of a link may run
/// different builds. If this fails after an intended model change, the
/// flight profile needs a new version identifier.
#[test]
fn golden_flight_stream_is_stable() {
    let s = telemetry(4096, 12, 2026);
    let mut tx = FlightSession::new(12, 14);
    let mut all = Vec::new();
    for p in s.chunks(256) {
        all.extend_from_slice(&tx.compress(p));
    }
    // FNV-1a of the concatenated frames.
    let h = all.iter().fold(0xcbf2_9ce4_8422_2325u64, |h, &b| {
        (h ^ b as u64).wrapping_mul(0x100_0000_01b3)
    });
    if std::env::var_os("SEDGE_BLESS").is_some() {
        println!("GOLDEN {} {h:#018x}", all.len());
        return;
    }
    assert_eq!(
        (all.len(), h),
        (GOLDEN_LEN, GOLDEN_HASH),
        "flight format changed"
    );
}

const GOLDEN_LEN: usize = 2140;
const GOLDEN_HASH: u64 = 0xe373_eda5_8555_da7a;

#[test]
fn sender_and_receiver_compute_the_same_surprise() {
    let mut s = telemetry(10_000, 12, 9);
    // Inject a glitch the model has never seen: a sudden jump.
    for v in &mut s[7000..7010] {
        *v = (*v + 1500) % 4096;
    }
    let (mut tx, mut rx) = (FlightSession::new(12, 14), FlightSession::new(12, 14));
    let (mut a, mut b) = (Vec::new(), Vec::new());
    for p in s.chunks(256) {
        let frame = tx.compress_scored(p, &mut a);
        assert_eq!(rx.decompress_scored(&frame, &mut b).unwrap(), p);
    }
    assert_eq!(a, b);
    let mean = |r: std::ops::Range<usize>| {
        a[r.clone()].iter().map(|&c| c as u64).sum::<u64>() / r.len() as u64
    };
    // The model reacts to change: the onset (and the end) of the glitch are
    // very surprising; inside it, the residual model adapts within a sample.
    assert!(
        a[7000] as u64 > 5 * mean(6000..7000),
        "the glitch onset should stand out: {} vs mean {}",
        a[7000],
        mean(6000..7000)
    );
}
