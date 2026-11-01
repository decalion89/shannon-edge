//! Fast packet profile: round trips, robustness, determinism.

use shannon_edge::packet_fast::FastPacketSession;

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

/// Housekeeping-like packets: header, counter, slow fields, noisy fields.
fn packets(n: usize, len: usize, seed: u64) -> Vec<Vec<u8>> {
    let mut rng = Rng(seed);
    let mut temp = 120u8;
    (0..n)
        .map(|i| {
            if rng.next() % 20 == 0 {
                temp = temp.wrapping_add((rng.next() % 3) as u8).wrapping_sub(1);
            }
            let mut p = vec![0u8; len.max(16)];
            p[0] = 0x08;
            p[1] = 0x1f;
            p[2..4].copy_from_slice(&(i as u16).to_be_bytes());
            p[4] = temp;
            for b in &mut p[5..9] {
                *b = (rng.next() % 4) as u8;
            }
            for (k, b) in p.iter_mut().enumerate().skip(9) {
                *b = (k as u8).wrapping_mul(7);
            }
            p.truncate(len);
            p
        })
        .collect()
}

fn roundtrip(ps: &[Vec<u8>], len: usize) -> usize {
    let (mut tx, mut rx) = (FastPacketSession::new(len), FastPacketSession::new(len));
    ps.iter()
        .map(|p| {
            let payload = tx.compress(p);
            assert_eq!(&rx.decompress(&payload).unwrap(), p);
            payload.len()
        })
        .sum()
}

#[test]
fn roundtrips_and_compresses() {
    for &len in &[1usize, 9, 32, 90, 1000] {
        let ps = packets(2_000, len, len as u64);
        let size = roundtrip(&ps, len);
        if len >= 32 {
            assert!(size * 6 < 2_000 * len, "{len}-byte packets: {size}");
        }
    }
}

#[test]
fn random_and_extreme_packets_roundtrip() {
    let mut rng = Rng(9);
    let ps: Vec<Vec<u8>> = (0..2_000)
        .map(|_| (0..64).map(|_| rng.next() as u8).collect())
        .collect();
    roundtrip(&ps, 64);
    // Alternating extremes: every byte changes by 255 or 1 (every delta).
    let ps: Vec<Vec<u8>> = (0..600)
        .map(|i| (0..16).map(|k| ((i * (k + 1)) % 256) as u8).collect())
        .collect();
    roundtrip(&ps, 16);
}

#[test]
fn garbage_payloads_never_panic() {
    let mut rng = Rng(4);
    let mut rx = FastPacketSession::new(40);
    for n in 0..200 {
        let payload: Vec<u8> = (0..n % 70).map(|_| rng.next() as u8).collect();
        assert_eq!(rx.decompress(&payload).unwrap().len(), 40);
    }
}

#[test]
fn lost_packet_recovers_at_next_epoch() {
    let ps = packets(300, 32, 5);
    let make = || {
        let mut s = FastPacketSession::new(32);
        s.prime(packets(50, 32, 6).iter().map(Vec::as_slice));
        s.with_epochs(64)
    };
    let mut tx = make();
    let payloads: Vec<Vec<u8>> = ps.iter().map(|p| tx.compress(p)).collect();
    let mut rx = make();
    for (i, payload) in payloads.iter().enumerate() {
        if i == 70 {
            continue; // lost
        }
        let r = rx.decompress_indexed(i as u64, payload);
        if (71..128).contains(&i) {
            assert!(r.is_err(), "packet {i} should wait for the epoch");
        } else {
            assert_eq!(r.unwrap(), ps[i], "packet {i}");
        }
    }
}

/// The fast packet format must not change silently.
#[test]
fn golden_fast_stream_is_stable() {
    let mut tx = FastPacketSession::new(48);
    let mut all = Vec::new();
    for p in packets(1_000, 48, 2026) {
        all.extend_from_slice(&tx.compress(&p));
    }
    let h = all.iter().fold(0xcbf2_9ce4_8422_2325u64, |h, &b| {
        (h ^ b as u64).wrapping_mul(0x100_0000_01b3)
    });
    if std::env::var_os("SEDGE_BLESS").is_some() {
        println!("GOLDEN_FAST {} {h:#018x}", all.len());
        return;
    }
    assert_eq!(
        (all.len(), h),
        (GOLDEN_LEN, GOLDEN_HASH),
        "fast packet format changed"
    );
}

const GOLDEN_LEN: usize = 2091;
const GOLDEN_HASH: u64 = 0xb626_82a3_244f_e674;

#[test]
fn learned_recipes_roundtrip_and_help() {
    use shannon_edge::packet_fast::recipe;
    let all = packets(3_000, 32, 11);
    let (history, test) = all.split_at(300);
    let hist: Vec<&[u8]> = history.iter().map(Vec::as_slice).collect();
    let recipes = FastPacketSession::learn_recipes(32, &hist);
    assert_eq!(
        recipes,
        FastPacketSession::learn_recipes(32, &hist),
        "deterministic"
    );
    assert!(recipes.iter().all(|&r| r < recipe::COUNT));
    let size = |r: &[u8]| -> usize {
        let mut base = FastPacketSession::with_recipes(r);
        base.prime(hist.iter().copied());
        let (mut tx, mut rx) = (base.clone(), base);
        test.iter()
            .map(|p| {
                let payload = tx.compress(p);
                assert_eq!(&rx.decompress(&payload).unwrap(), p);
                payload.len()
            })
            .sum()
    };
    // Every recipe works; the learned ones are not worse than the default.
    for r in 0..recipe::COUNT {
        size(&[r; 32]);
    }
    assert!(size(&recipes) <= size(&[recipe::LEFT_CHANGED; 32]) + 32);
}

#[test]
#[should_panic(expected = "unknown recipe")]
fn unknown_recipe_is_rejected() {
    FastPacketSession::with_recipes(&[0, 9]);
}

#[test]
fn coding_classes_roundtrip() {
    use shannon_edge::packet_fast::class;
    let all = packets(2_000, 32, 21);
    let (history, test) = all.split_at(200);
    let hist: Vec<&[u8]> = history.iter().map(Vec::as_slice).collect();
    let classes = FastPacketSession::learn_classes(32, &hist, 0.01, 0.9);
    assert!(
        classes.contains(&class::STATIC) && classes.contains(&class::ALWAYS),
        "{classes:?}"
    );
    let recipes = FastPacketSession::learn_recipes(32, &hist);
    // Learned classes, and every class forced on every column (including
    // "static" columns that do change and "always" columns that do not).
    for cl in [classes, vec![class::STATIC; 32], vec![class::ALWAYS; 32]] {
        let mut base = FastPacketSession::with_layout(&recipes, &cl);
        base.prime(hist.iter().copied());
        let (mut tx, mut rx) = (base.clone(), base);
        for p in test {
            assert_eq!(&rx.decompress(&tx.compress(p)).unwrap(), p);
        }
    }
}

#[test]
#[should_panic(expected = "unknown class")]
fn unknown_class_is_rejected() {
    FastPacketSession::with_layout(&[0, 0], &[0, 7]);
}
