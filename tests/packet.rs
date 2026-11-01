//! Packet profile: round trips, determinism and robustness.

use shannon_edge::packet::PacketSession;

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

fn roundtrip(ps: &[Vec<u8>], len: usize, table_bits: u32) -> usize {
    let (mut tx, mut rx) = (
        PacketSession::new(len, table_bits),
        PacketSession::new(len, table_bits),
    );
    ps.iter()
        .map(|p| {
            let payload = tx.compress(p);
            assert_eq!(&rx.decompress(&payload).unwrap(), p);
            payload.len()
        })
        .sum()
}

#[test]
fn roundtrips_and_compresses_housekeeping_packets() {
    for &len in &[1usize, 9, 32, 90] {
        let ps = packets(3_000, len, len as u64);
        let size = roundtrip(&ps, len, 14);
        if len >= 32 {
            assert!(size * 8 < 3_000 * len, "{len}-byte packets: {size}");
        }
    }
}

#[test]
fn random_packets_roundtrip() {
    let mut rng = Rng(9);
    let ps: Vec<Vec<u8>> = (0..500)
        .map(|_| (0..64).map(|_| rng.next() as u8).collect())
        .collect();
    roundtrip(&ps, 64, 12);
}

#[test]
fn garbage_payloads_never_panic() {
    let mut rng = Rng(4);
    let mut rx = PacketSession::new(40, 12);
    for n in 0..64 {
        let payload: Vec<u8> = (0..n).map(|_| rng.next() as u8).collect();
        assert_eq!(rx.decompress(&payload).unwrap().len(), 40);
    }
}

#[test]
#[should_panic(expected = "packet length")]
fn wrong_packet_length_is_rejected() {
    PacketSession::new(10, 12).compress(&[0; 9]);
}

/// The packet format must not change silently.
#[test]
fn golden_packet_stream_is_stable() {
    let mut tx = PacketSession::new(48, 14);
    let mut all = Vec::new();
    for p in packets(1_000, 48, 2026) {
        all.extend_from_slice(&tx.compress(&p));
    }
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
        "packet format changed"
    );
}

const GOLDEN_LEN: usize = 1448;
const GOLDEN_HASH: u64 = 0x9b4e_9d6e_15f8_dfed;

/// Send `ps` through a link that drops the packets in `lost`; returns, for
/// each packet, whether the receiver decoded it (decoded packets verified).
fn lossy_link(ps: &[Vec<u8>], make: impl Fn() -> PacketSession, lost: &[usize]) -> Vec<bool> {
    let mut tx = make();
    let payloads: Vec<Vec<u8>> = ps.iter().map(|p| tx.compress(p)).collect();
    let mut rx = make();
    (0..ps.len())
        .map(|i| {
            if lost.contains(&i) {
                return false;
            }
            match rx.decompress_indexed(i as u64, &payloads[i]) {
                Ok(out) => {
                    assert_eq!(out, ps[i], "packet {i}");
                    true
                }
                Err(_) => false,
            }
        })
        .collect()
}

#[test]
fn key_packets_roundtrip_and_absorb_lost_non_key_packets() {
    let ps = packets(400, 32, 3);
    let make = || PacketSession::new(32, 12).with_key_interval(8);
    // No loss: everything decodes.
    assert!(lossy_link(&ps, make, &[]).iter().all(|&d| d));
    // Lost non-key packets (not multiples of 8): only they are missing.
    let lost = [1, 2, 3, 13, 100, 101, 399];
    let got = lossy_link(&ps, make, &lost);
    for (i, &d) in got.iter().enumerate() {
        assert_eq!(d, !lost.contains(&i), "packet {i}");
    }
}

#[test]
fn lost_key_packet_recovers_at_next_epoch() {
    let ps = packets(400, 32, 4);
    let make = |key| {
        move || {
            let mut s = PacketSession::new(32, 12).with_key_interval(key);
            s.prime(packets(50, 32, 5).iter().map(Vec::as_slice));
            s.with_epochs(64)
        }
    };
    let check = |key, lost: &[usize], dead: std::ops::Range<usize>| {
        let got = lossy_link(&ps, make(key), lost);
        for (i, &d) in got.iter().enumerate() {
            assert_eq!(d, !lost.contains(&i) && !dead.contains(&i), "packet {i}");
        }
    };
    // Key packet 136 lost: the rest of its epoch is lost, 192.. decodes.
    check(4, &[136], 137..192);
    // The key packet that starts an epoch lost: that whole epoch.
    check(4, &[190, 191, 192], 193..256);
    // A gap spanning an epoch boundary, with no key packet lost after the
    // boundary (key interval 5, so 192 is not a key packet): both ends
    // restarted at 192, so decoding resumes right after the gap.
    check(5, &[189, 190, 191, 192, 193], 0..0);
}
