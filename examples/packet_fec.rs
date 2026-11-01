//! Separation experiment: the packet profile at full strength (every packet
//! teaches the model) plus a packet-level erasure code, under packet loss.
//!
//!     cargo run --release --example packet_fec -- PACKETS.bin PACKET_LEN [TABLE_BITS] [CCSDS_SIZES]
//!
//! Same split as `packet_robust`: the first 10% of the packets prime the
//! model, the remaining 90% are the test link. Payloads are grouped by G;
//! each group gets m Reed–Solomon parity packets (`shannon_edge::fec`).
//! Every packet on the link, data or parity, is lost i.i.d. with the given
//! probability. The receiver recovers what the group's parity allows, then
//! decodes in order (`decompress_indexed`); an unrecoverable group
//! desynchronises it until the next epoch (E = 4096 packets, primed origin).
//! Every decoded packet is verified.
//!
//! CCSDS_SIZES (optional): the per-packet sizes of CCSDS 124 on the same
//! test packets (`bench/c/ccsds124_loss.c`), to report its size with the
//! same erasure code. Set SEDGE_PACKET_V2=1 for version 2 of the profile,
//! SEDGE_PACKET_FAST=1 for the fast profile (`packet_fast`); SEDGE_SIZES_OUT=path
//! writes the payload sizes, one per line.

use shannon_edge::fec;
use shannon_edge::packet::PacketSession;
use shannon_edge::packet_fast::FastPacketSession;
use shannon_edge::Error;

/// Either packet profile, behind one interface.
#[derive(Clone)]
enum Codec {
    Cm(Box<PacketSession>),
    Fast(FastPacketSession),
}

impl Codec {
    fn prime(&mut self, packets: &[&[u8]]) {
        match self {
            Codec::Cm(s) => s.prime(packets.iter().copied()),
            Codec::Fast(s) => s.prime(packets.iter().copied()),
        }
    }
    fn with_epochs(self, every: u64) -> Self {
        match self {
            Codec::Cm(s) => Codec::Cm(Box::new(s.with_epochs(every))),
            Codec::Fast(s) => Codec::Fast(s.with_epochs(every)),
        }
    }
    fn compress(&mut self, p: &[u8]) -> Vec<u8> {
        match self {
            Codec::Cm(s) => s.compress(p),
            Codec::Fast(s) => s.compress(p),
        }
    }
    fn decompress_indexed(&mut self, i: u64, p: &[u8]) -> Result<Vec<u8>, Error> {
        match self {
            Codec::Cm(s) => s.decompress_indexed(i, p),
            Codec::Fast(s) => s.decompress_indexed(i, p),
        }
    }
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

const EPOCH: u64 = 4096;

fn parity_bytes(sizes: &[usize], g: usize, m: usize) -> usize {
    sizes
        .chunks(g)
        .map(|c| m * (2 + c.iter().max().unwrap()))
        .sum()
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let tb: u32 = args.get(2).map_or(16, |v| v.parse().expect("TABLE_BITS"));
    let ccsds: Option<Vec<usize>> = args.get(3).map(|p| {
        std::fs::read_to_string(p)
            .expect("read CCSDS sizes")
            .lines()
            .map(|l| l.trim().parse().expect("size"))
            .collect()
    });
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    let (history, test) = packets.split_at(packets.len() / 10);

    let v2 = std::env::var_os("SEDGE_PACKET_V2").is_some();
    let fast = std::env::var_os("SEDGE_PACKET_FAST").is_some();
    let mut base = if fast {
        Codec::Fast(FastPacketSession::new(len))
    } else if v2 {
        Codec::Cm(Box::new(PacketSession::v2(len, tb)))
    } else {
        Codec::Cm(Box::new(PacketSession::new(len, tb)))
    };
    base.prime(history);
    let make = || base.clone().with_epochs(EPOCH);
    let mut tx = make();
    let payloads: Vec<Vec<u8>> = test.iter().map(|p| tx.compress(p)).collect();
    let size: usize = payloads.iter().map(Vec::len).sum();
    let sizes: Vec<usize> = payloads.iter().map(Vec::len).collect();
    if let Some(path) = std::env::var_os("SEDGE_SIZES_OUT") {
        let text: String = sizes.iter().map(|s| format!("{s}\n")).collect();
        std::fs::write(path, text).expect("write sizes");
    }
    println!(
        "test {} packets ({} bytes), {}, primed, epochs of {EPOCH}: {size} bytes without parity",
        test.len(),
        test.len() * len,
        if fast {
            "fast profile".to_string()
        } else {
            format!("tables 2^{tb}{}", if v2 { ", v2" } else { "" })
        }
    );
    print!("| Group G | Parity m | sedge + parity: bytes |");
    if ccsds.is_some() {
        print!(" CCSDS 124 R=0 + same parity: bytes |");
    }
    println!(" Decoded at 0.1% loss | 1% | 5% |");
    println!(
        "|---:|---:|---:|{}---:|---:|---:|",
        if ccsds.is_some() { "---:|" } else { "" }
    );
    for &(g, m) in &[
        (16usize, 1usize),
        (16, 2),
        (16, 3),
        (32, 2),
        (32, 3),
        (32, 4),
        (32, 6),
        (32, 8),
        (64, 3),
        (64, 4),
        (64, 6),
        (64, 10),
        (64, 12),
        (128, 7),
        (128, 8),
        (250, 2),
        (250, 3),
        (240, 8),
        (240, 10),
        (240, 12),
        (232, 24),
        (226, 30),
    ] {
        let parities: Vec<Vec<Vec<u8>>> = payloads
            .chunks(g)
            .map(|c| {
                let refs: Vec<&[u8]> = c.iter().map(Vec::as_slice).collect();
                fec::encode(&refs, m)
            })
            .collect();
        let total = size + parity_bytes(&sizes, g, m);
        let mut fractions = Vec::new();
        for &loss in &[1u64, 10, 50] {
            let mut rng = Rng(0x5eed + loss);
            let mut rx = make();
            let mut decoded = 0usize;
            for (k, (group, par)) in payloads.chunks(g).zip(&parities).enumerate() {
                let mut got: Vec<Option<Vec<u8>>> = group
                    .iter()
                    .map(|p| (rng.next() % 1000 >= loss).then(|| p.clone()))
                    .collect();
                let rp: Vec<Option<Vec<u8>>> = par
                    .iter()
                    .map(|p| (rng.next() % 1000 >= loss).then(|| p.clone()))
                    .collect();
                fec::recover(&mut got, &rp);
                for (j, p) in got.iter().enumerate() {
                    let i = k * g + j;
                    if let Some(p) = p {
                        if let Ok(out) = rx.decompress_indexed(i as u64, p) {
                            assert_eq!(&out[..], test[i], "wrong packet {i}");
                            decoded += 1;
                        }
                    }
                }
            }
            fractions.push(100.0 * decoded as f64 / test.len() as f64);
        }
        print!("| {g} | {m} | {total} |");
        if let Some(c) = &ccsds {
            print!(" {} |", c.iter().sum::<usize>() + parity_bytes(c, g, m));
        }
        println!(
            " {:.2}% | {:.2}% | {:.2}% |",
            fractions[0], fractions[1], fractions[2]
        );
    }
}
