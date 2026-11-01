//! Robustness experiment for the packet profile: key packets, epochs and a
//! primed origin.
//!
//!     cargo run --release --example packet_robust -- PACKETS.bin PACKET_LEN [TABLE_BITS]
//!
//! The first 10% of the packets play the spacecraft's history (used only to
//! prime the origin model); the remaining 90% are the test link. For each
//! configuration (key interval K, epoch length E, primed or not), prints the
//! compressed size of the test packets and, under simulated i.i.d. packet
//! loss, the fraction of all test packets the receiver decodes (every
//! decoded packet verified). Two link models: every packet sent once, and
//! key packets sent twice (both copies lost independently; the size then
//! counts the copies).

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

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let tb: u32 = args.get(2).map_or(16, |v| v.parse().expect("TABLE_BITS"));
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    let split = packets.len() / 10;
    let (history, test) = packets.split_at(split);
    println!(
        "history {} packets, test {} packets ({} bytes), tables 2^{tb}",
        history.len(),
        test.len(),
        test.len() * len
    );
    println!("| Key interval K | Epoch E | Primed | Test bytes | Decoded at 0.1% loss | at 1% loss | Key packets sent twice: bytes | decoded at 1% loss |");
    println!("|---:|---:|---|---:|---:|---:|---:|---:|");
    let configs: &[(u64, u64)] = &[
        (1, 0),
        (1, 1_000),
        (1, 100),
        (1, 10),
        (4, 0),
        (4, 1_024),
        (16, 0),
        (16, 1_024),
        (64, 0),
        (64, 1_024),
    ];
    for &(key, epoch) in configs {
        for &primed in &[false, true] {
            let mut base = PacketSession::new(len, tb).with_key_interval(key);
            if primed {
                base.prime(history.iter().copied());
            }
            let make = || {
                if epoch > 0 {
                    base.clone().with_epochs(epoch)
                } else {
                    base.clone()
                }
            };
            // Compress the test link once; keep payloads for loss runs.
            let mut tx = make();
            let payloads: Vec<Vec<u8>> = test.iter().map(|p| tx.compress(p)).collect();
            let size: usize = payloads.iter().map(Vec::len).sum();
            let key_bytes: usize = payloads.iter().step_by(key as usize).map(Vec::len).sum();
            let mut fractions = Vec::new();
            for &(loss_per_mille, twice) in &[(1u64, false), (10, false), (10, true)] {
                let mut rng = Rng(0x5eed + loss_per_mille);
                let mut rx = make();
                let mut decoded = 0usize;
                for (i, (payload, packet)) in payloads.iter().zip(test.iter()).enumerate() {
                    let mut lost = rng.next() % 1000 < loss_per_mille;
                    if twice && i as u64 % key == 0 {
                        lost &= rng.next() % 1000 < loss_per_mille; // the copy
                    }
                    if lost {
                        continue; // lost on the link
                    }
                    if let Ok(out) = rx.decompress_indexed(i as u64, payload) {
                        assert_eq!(&out[..], *packet, "wrong packet {i}");
                        decoded += 1;
                    }
                }
                fractions.push(100.0 * decoded as f64 / test.len() as f64);
            }
            println!(
                "| {key} | {} | {} | {size} | {:.2}% | {:.2}% | {} | {:.2}% |",
                if epoch == 0 {
                    "none".to_string()
                } else {
                    epoch.to_string()
                },
                if primed { "yes" } else { "no" },
                fractions[0],
                fractions[1],
                size + key_bytes,
                fractions[2]
            );
        }
    }
}
