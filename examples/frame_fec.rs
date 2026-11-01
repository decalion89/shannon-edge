//! Loss protection over transfer frames, the unit real links lose.
//!
//!     cargo run --release --example frame_fec -- PACKETS.bin PACKET_LEN [FRAME_LEN]
//!     cargo run --release --example frame_fec -- --sizes SIZES.txt FRAME_LEN LOSS MASK_OUT
//!
//! Space links carry packets inside fixed-length transfer frames and lose
//! whole frames. Here the compressed payloads of the test packets (the last
//! 90%, sedge packet profile v2 at 2^16 primed on the first 10% with epochs
//! of 4096, or the fast profile with SEDGE_PACKET_FAST=1) are packed back to
//! back into frames of FRAME_LEN bytes (default 223), each payload preceded
//! by a 1-byte length, each frame starting with a 2-byte first-header
//! pointer (as in CCSDS TM frames, so a receiver can resynchronise after a
//! lost frame). Groups of G frames get m Reed–Solomon parity frames
//! (`shannon_edge::fec`); every frame, data or parity, is lost i.i.d. A
//! packet is available if every frame it touches arrived or was rebuilt;
//! available packets are decoded in order (`decompress_indexed`) and
//! verified. Because all frames have the same length, parity needs no
//! padding: the overhead is m/G plus framing.
//!
//! `--sizes` mode does the same framing and loss for another codec given
//! only its per-packet payload sizes (e.g. CCSDS 124 from
//! `bench/c/ccsds124_loss.c`), without protection, and writes which packets
//! survived (one 0/1 per line) for that codec's own decoder.

use shannon_edge::fec;
use shannon_edge::packet::PacketSession;
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

const EPOCH: u64 = 4096;

/// Pack payloads (1-byte length + bytes) into frames of `flen` bytes with a
/// 2-byte first-header pointer. Returns the frames and, per payload, the
/// first and last frame it touches.
fn pack(
    sizes: &[usize],
    payloads: Option<&[Vec<u8>]>,
    flen: usize,
) -> (Vec<Vec<u8>>, Vec<(usize, usize)>) {
    let room = flen - 2;
    let mut stream = Vec::new();
    let mut starts = Vec::with_capacity(sizes.len());
    for (i, &s) in sizes.iter().enumerate() {
        assert!(s < 256, "payload too long for a 1-byte length");
        starts.push(stream.len());
        stream.push(s as u8);
        match payloads {
            Some(p) => stream.extend_from_slice(&p[i]),
            None => stream.resize(stream.len() + s, 0),
        }
    }
    let nframes = stream.len().div_ceil(room);
    let mut frames = Vec::with_capacity(nframes);
    let mut next = 0;
    for f in 0..nframes {
        let (a, b) = (f * room, ((f + 1) * room).min(stream.len()));
        while next < starts.len() && starts[next] < a {
            next += 1;
        }
        let fhp = if next < starts.len() && starts[next] < b {
            (starts[next] - a) as u16
        } else {
            0xffff
        };
        let mut fr = fhp.to_be_bytes().to_vec();
        fr.extend_from_slice(&stream[a..b]);
        fr.resize(flen, 0);
        frames.push(fr);
    }
    let span = sizes
        .iter()
        .zip(&starts)
        .map(|(&s, &st)| (st / room, (st + s) / room))
        .collect();
    (frames, span)
}

/// Which frames are available after i.i.d. loss and recovery.
fn transmit(frames: &[Vec<u8>], g: usize, m: usize, loss: u64, seed: u64) -> (Vec<bool>, usize) {
    let mut rng = Rng(seed);
    let mut ok = vec![false; frames.len()];
    let mut parity_bytes = 0;
    for (k, group) in frames.chunks(g).enumerate() {
        let refs: Vec<&[u8]> = group.iter().map(Vec::as_slice).collect();
        let par = if m > 0 {
            fec::encode(&refs, m)
        } else {
            Vec::new()
        };
        parity_bytes += par.iter().map(Vec::len).sum::<usize>();
        let mut got: Vec<Option<Vec<u8>>> = group
            .iter()
            .map(|f| (rng.next() % 100_000 >= loss).then(|| f.clone()))
            .collect();
        let rp: Vec<Option<Vec<u8>>> = par
            .into_iter()
            .map(|p| (rng.next() % 100_000 >= loss).then_some(p))
            .collect();
        if m > 0 {
            fec::recover(&mut got, &rp);
        }
        for (j, f) in got.iter().enumerate() {
            if let Some(f) = f {
                assert_eq!(f, &group[j], "recovered frame differs");
                ok[k * g + j] = true;
            }
        }
    }
    (ok, parity_bytes)
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    if args[0] == "--sizes" {
        let sizes: Vec<usize> = std::fs::read_to_string(&args[1])
            .expect("sizes")
            .lines()
            .map(|l| l.trim().parse().expect("size"))
            .collect();
        let flen: usize = args[2].parse().expect("FRAME_LEN");
        let loss: u64 = args[3].parse().expect("LOSS in 1/100000");
        let (frames, span) = pack(&sizes, None, flen);
        let (ok, _) = transmit(&frames, 1, 0, loss, 0xf4a3 + loss);
        let mask: String = span
            .iter()
            .map(|&(a, b)| if (a..=b).all(|f| ok[f]) { "1\n" } else { "0\n" })
            .collect();
        std::fs::write(&args[4], &mask).expect("mask");
        let avail = mask.lines().filter(|l| *l == "1").count();
        println!(
            "{} packets, {} frames of {flen} bytes ({} bytes); {:.2}% of packets survive",
            sizes.len(),
            frames.len(),
            frames.len() * flen,
            100.0 * avail as f64 / sizes.len() as f64
        );
        return;
    }
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let flen: usize = args.get(2).map_or(223, |v| v.parse().expect("FRAME_LEN"));
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    let (history, test) = packets.split_at(packets.len() / 10);
    let fast = std::env::var_os("SEDGE_PACKET_FAST").is_some();
    enum C {
        V2(Box<PacketSession>),
        Fast(FastPacketSession),
    }
    let make = || {
        if fast {
            let mut s = FastPacketSession::new(len);
            s.prime(history.iter().copied());
            C::Fast(s.with_epochs(EPOCH))
        } else {
            let mut s = PacketSession::v2(len, 16);
            s.prime(history.iter().copied());
            C::V2(Box::new(s.with_epochs(EPOCH)))
        }
    };
    let mut tx = make();
    let payloads: Vec<Vec<u8>> = test
        .iter()
        .map(|p| match &mut tx {
            C::V2(s) => s.compress(p),
            C::Fast(s) => s.compress(p),
        })
        .collect();
    let sizes: Vec<usize> = payloads.iter().map(Vec::len).collect();
    let raw: usize = sizes.iter().sum();
    let (frames, span) = pack(&sizes, Some(&payloads), flen);
    let framed = frames.len() * flen;
    println!(
        "{}: {} test packets, payloads {raw} bytes; in {} frames of {flen} bytes: {framed} bytes \
         (+{:.1}% for lengths, frame pointers and the last frame)",
        if fast { "fast profile" } else { "v2, 2^16" },
        test.len(),
        frames.len(),
        100.0 * (framed as f64 / raw as f64 - 1.0)
    );
    println!("| Frame loss | G frames | m | Bytes sent | Overhead vs frames | Packets decoded |");
    println!("|---:|---:|---:|---:|---:|---:|");
    for &(loss, configs) in &[
        (100u64, &[(1usize, 0usize), (200, 2), (250, 3)][..]),
        (1_000, &[(1, 0), (200, 6), (240, 8), (240, 10)][..]),
        (5_000, &[(1, 0), (200, 22), (220, 26), (220, 30)][..]),
    ] {
        for &(g, m) in configs {
            let (ok, parity) = transmit(&frames, g, m, loss, 0xf4a3 + loss);
            let mut rx = make();
            let mut decoded = 0usize;
            for (i, &(a, b)) in span.iter().enumerate() {
                if (a..=b).all(|f| ok[f]) {
                    let r = match &mut rx {
                        C::V2(s) => s.decompress_indexed(i as u64, &payloads[i]),
                        C::Fast(s) => s.decompress_indexed(i as u64, &payloads[i]),
                    };
                    if let Ok(out) = r {
                        assert_eq!(&out[..], test[i], "packet {i}");
                        decoded += 1;
                    }
                }
            }
            println!(
                "| {:.1}% | {} | {m} | {} | +{:.1}% | {:.2}% |",
                loss as f64 / 1000.0,
                if m == 0 {
                    "none".to_string()
                } else {
                    g.to_string()
                },
                framed + parity,
                100.0 * parity as f64 / framed as f64,
                100.0 * decoded as f64 / test.len() as f64
            );
        }
    }
}
