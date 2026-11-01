//! Benchmark the fast packet profile on a file of fixed-length packets.
//!
//!     cargo run --release --example packet_fast_bench -- PACKETS.bin PACKET_LEN
//!
//! Compresses every packet, then decompresses and verifies every one, and
//! prints the total payload size, the model memory and both speeds.
//!
//! With SEDGE_FAST_RECIPES=1: the first 10% of the packets play the
//! history held on the ground; it chooses per-column context recipes
//! (`learn_recipes`) and both ends are primed with it. Reported on the
//! remaining 90%: default recipes, learned recipes, and learned recipes
//! plus coding classes (`learn_classes`; thresholds from
//! SEDGE_FAST_CLASSES=static_max,always_min, default 0.01,0.9), each also
//! with ground-chosen adaptation windows (`learn_windows`).

use shannon_edge::packet_fast::FastPacketSession;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    if std::env::var_os("SEDGE_FAST_RECIPES").is_some() {
        let (history, test) = packets.split_at(packets.len() / 10);
        let t = Instant::now();
        let recipes = FastPacketSession::learn_recipes(len, history);
        let learn = t.elapsed().as_secs_f64();
        let mut counts = [0usize; 5];
        for &r in &recipes {
            counts[r as usize] += 1;
        }
        let (smax, amin) = std::env::var("SEDGE_FAST_CLASSES")
            .ok()
            .and_then(|v| {
                let (a, b) = v.split_once(',')?;
                Some((a.parse().ok()?, b.parse().ok()?))
            })
            .unwrap_or((0.01, 0.9));
        let classes = FastPacketSession::learn_classes(len, history, smax, amin);
        let normal = vec![0u8; len];
        let t = Instant::now();
        let win_n = FastPacketSession::learn_windows(history, &recipes, &normal);
        let win_c = FastPacketSession::learn_windows(history, &recipes, &classes);
        let learn_w = t.elapsed().as_secs_f64() / 2.0;
        let dw = vec![0u8; len];
        let runs = [
            (
                "default recipes",
                vec![0u8; len],
                normal.clone(),
                dw.clone(),
            ),
            (
                "learned recipes",
                recipes.clone(),
                normal.clone(),
                dw.clone(),
            ),
            (
                "learned recipes + classes",
                recipes.clone(),
                classes.clone(),
                dw,
            ),
            (
                "learned recipes + windows",
                recipes.clone(),
                normal,
                win_n.clone(),
            ),
            (
                "learned recipes + classes + windows",
                recipes,
                classes.clone(),
                win_c,
            ),
        ];
        let only: Option<usize> = std::env::var("SEDGE_FAST_ONLY")
            .ok()
            .and_then(|v| v.parse().ok());
        for (i, (name, r, cl, w)) in runs.into_iter().enumerate() {
            if only.is_some_and(|o| o != i) {
                continue;
            }
            let mut base = FastPacketSession::with_layout_windows(&r, &cl, &w);
            base.prime(history.iter().copied());
            let (mut tx, mut rx) = (base.clone(), base);
            let t = Instant::now();
            let payloads: Vec<Vec<u8>> = test.iter().map(|p| tx.compress(p)).collect();
            let enc = t.elapsed().as_secs_f64();
            for (payload, packet) in payloads.iter().zip(test) {
                assert_eq!(&rx.decompress(payload).unwrap(), packet);
            }
            let total: usize = payloads.iter().map(Vec::len).sum();
            println!(
                "{name}: test {} packets -> {total} bytes, memory {:.0} KiB, compress {:.1} MB/s (verified)",
                test.len(),
                tx.memory_bytes() as f64 / 1024.0,
                (test.len() * len) as f64 / enc / 1e6
            );
        }
        let ccount = [0u8, 1, 2].map(|c| classes.iter().filter(|&&x| x == c).count());
        println!(
            "recipes per kind {counts:?}, learned in {learn:.2}s; classes normal/static/always \
             {ccount:?} (SEDGE_FAST_CLASSES={smax},{amin}); windows per kind {:?}, learned in {learn_w:.2}s",
            (0..7u8).map(|w| win_n.iter().filter(|&&x| x == w).count()).collect::<Vec<_>>()
        );
        return;
    }
    let (mut tx, mut rx) = (FastPacketSession::new(len), FastPacketSession::new(len));
    let t = Instant::now();
    let payloads: Vec<Vec<u8>> = packets.iter().map(|p| tx.compress(p)).collect();
    let enc = t.elapsed().as_secs_f64();
    let t = Instant::now();
    for (n, (payload, packet)) in payloads.iter().zip(&packets).enumerate() {
        assert_eq!(&rx.decompress(payload).unwrap(), packet, "packet {n}");
    }
    let dec = t.elapsed().as_secs_f64();
    let n = packets.len();
    let total: usize = payloads.iter().map(Vec::len).sum();
    let mb = (n * len) as f64 / 1e6;
    println!(
        "{n} packets x {len} bytes ({} bytes) -> {total} bytes ({:.2}x), fast profile, \
         memory {:.0} KiB, compress {:.1} MB/s, decompress {:.1} MB/s (verified)",
        n * len,
        (n * len) as f64 / total as f64,
        tx.memory_bytes() as f64 / 1024.0,
        mb / enc,
        mb / dec
    );
}
