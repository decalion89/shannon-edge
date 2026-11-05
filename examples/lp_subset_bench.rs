//! Packet profile v2_lp with ground-learned predictor subsets.
//!
//! Usage: `lp_subset_bench FILE PACKET_LEN TABLE_BITS MODE...`
//! where MODE is `v2`, `lp` (every predictor) or `kN` (the N most useful
//! per column, N <= 4). Subsets are learned on the first 10% of the packets
//! (`learn_lp_subsets`, once, for the largest N; smaller N take a prefix).
//! Each mode compresses every packet with a fresh sender, decompresses with
//! a fresh receiver, verifies each packet, and prints the bytes on all
//! packets and on the last 90% (the held-out part), speed and memory.
//! Set SEDGE_SUBSETS=path to load/save the learned subsets.

use shannon_edge::packet::{LpConfig, PacketSession};
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let tb: u32 = args[2].parse().expect("TABLE_BITS");
    let modes = &args[3..];
    let ps: Vec<&[u8]> = data.chunks_exact(len).collect();
    let n = ps.len();
    let learn_n = n / 10;
    let kmax = modes
        .iter()
        .filter_map(|m| m.strip_prefix('k').map(|v| v.parse::<usize>().expect("kN")))
        .max();
    let subsets: Option<Vec<Vec<u8>>> = kmax.map(|k| {
        let path = std::env::var("SEDGE_SUBSETS").ok();
        if let Some(Ok(s)) = path.as_ref().map(std::fs::read_to_string) {
            let v: Vec<Vec<u8>> = s
                .lines()
                .map(|l| l.split_whitespace().map(|t| t.parse().unwrap()).collect())
                .collect();
            if v.len() == len {
                eprintln!("subsets loaded from {}", path.as_ref().unwrap());
                return v;
            }
        }
        let t = Instant::now();
        let v = PacketSession::learn_lp_subsets(&ps[..learn_n], len, tb, k);
        eprintln!(
            "learned k<={k} subsets on {learn_n} packets in {:.1}s",
            t.elapsed().as_secs_f64()
        );
        if let Some(p) = path {
            let s: String = v
                .iter()
                .map(|c| {
                    c.iter()
                        .map(|x| x.to_string())
                        .collect::<Vec<_>>()
                        .join(" ")
                        + "\n"
                })
                .collect();
            std::fs::write(p, s).expect("save subsets");
        }
        v
    });
    if let Some(s) = &subsets {
        let mut hist = [0usize; 14];
        for c in s {
            for &id in c {
                hist[id as usize] += 1;
            }
        }
        let sizes: Vec<usize> = (0..=kmax.unwrap())
            .map(|j| s.iter().filter(|c| c.len() == j).count())
            .collect();
        eprintln!("columns by subset size 0..: {sizes:?}; predictor use: {hist:?}");
    }
    let mb = (n * len) as f64 / 1e6;
    for mode in modes {
        let make = || match mode.as_str() {
            "v2" => PacketSession::v2(len, tb),
            "lp" => match std::env::var("SEDGE_LP") {
                Ok(c) => PacketSession::v2_lp_with(len, tb, LpConfig::parse(&c)),
                Err(_) => PacketSession::v2_lp(len, tb),
            },
            m => {
                let k: usize = m[1..].parse().unwrap();
                let s: Vec<Vec<u8>> = subsets
                    .as_ref()
                    .unwrap()
                    .iter()
                    .map(|c| c[..c.len().min(k)].to_vec())
                    .collect();
                match std::env::var("SEDGE_LP") {
                    Ok(c) => PacketSession::v2_lp_subsets_with(len, tb, LpConfig::parse(&c), &s),
                    Err(_) => PacketSession::v2_lp_with_subsets(len, tb, &s),
                }
            }
        };
        let (mut tx, mut rx) = (make(), make());
        let t = Instant::now();
        let payloads: Vec<Vec<u8>> = ps.iter().map(|p| tx.compress(p)).collect();
        let enc = t.elapsed().as_secs_f64();
        let t = Instant::now();
        for (p, pl) in ps.iter().zip(&payloads) {
            assert_eq!(&rx.decompress(pl).expect("decompress"), p, "round trip");
        }
        let dec = t.elapsed().as_secs_f64();
        let all: usize = payloads.iter().map(Vec::len).sum();
        let test: usize = payloads[learn_n..].iter().map(Vec::len).sum();
        println!(
            "{mode:>3} tb={tb} all {all} test {test} mem {:.0} KiB comp {:.2} MB/s dec {:.2} MB/s (verified)",
            tx.memory_bytes() as f64 / 1024.0,
            mb / enc,
            mb / dec
        );
    }
}
