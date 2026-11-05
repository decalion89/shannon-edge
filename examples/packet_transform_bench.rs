//! Ground-learned record transforms (field relations, optional field deltas)
//! in front of a packet codec.
//!
//!     cargo run --release --example packet_transform_bench -- FILE LAYOUT [--delta] [--fast]
//!
//! LAYOUT is a `fields::Layout` spec, e.g. `i16le*12`. The transform is
//! learned on the first 10% of the records (what the ground has received),
//! then every record is transformed, compressed packet by packet (packet
//! profile v2 at 2^16, or the fast profile with `--fast`), decompressed,
//! inverted and checked against the original.

use shannon_edge::fields::{Layout, RecordTransform};
use shannon_edge::packet::PacketSession;
use shannon_edge::packet_fast::FastPacketSession;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read");
    let layout = Layout::parse(&args[1]).expect("layout");
    let delta = args.iter().any(|a| a == "--delta");
    let fast = args.iter().any(|a| a == "--fast");
    let len = layout.len();
    let recs: Vec<&[u8]> = data.chunks_exact(len).collect();
    let learn_n = recs.len() / 10;
    let t0 = std::time::Instant::now();
    let tf = RecordTransform::learn(layout, recs[..learn_n].iter().copied(), delta, 2.0);
    let learn_s = t0.elapsed().as_secs_f64();
    for r in tf.relations() {
        println!(
            "relation: field {} = floor(({}*f{} + {}*f{})/2) + r",
            r.target, r.a, r.i, r.b, r.j
        );
    }
    let up = tf.to_bytes();
    let (mut tx_t, mut rx_t) = (
        RecordTransform::from_bytes(&up).unwrap(),
        RecordTransform::from_bytes(&up).unwrap(),
    );
    let nd = tf.deltas().iter().filter(|&&d| d).count();
    let (mut v_tx, mut v_rx) = (PacketSession::v2(len, 16), PacketSession::v2(len, 16));
    let (mut f_tx, mut f_rx) = (FastPacketSession::new(len), FastPacketSession::new(len));
    let t1 = std::time::Instant::now();
    let mut bytes = 0usize;
    for r in &recs {
        let fwd = tx_t.forward(r);
        let payload = if fast {
            f_tx.compress(&fwd)
        } else {
            v_tx.compress(&fwd)
        };
        bytes += payload.len();
        let dec = if fast {
            f_rx.decompress(&payload)
        } else {
            v_rx.decompress(&payload)
        }
        .expect("decode");
        assert_eq!(&rx_t.inverse(&dec)[..], *r, "record mismatch");
    }
    let secs = t1.elapsed().as_secs_f64();
    println!(
        "{} records x {len} bytes ({} bytes) -> {bytes} bytes ({:.2}x), {}, {} relations, {nd} field deltas, \
         transform {} bytes to uplink, learned in {learn_s:.1}s; round trip {:.1} MB/s (verified)",
        recs.len(),
        data.len(),
        data.len() as f64 / bytes as f64,
        if fast { "fast profile" } else { "v2 2^16" },
        tf.relations().len(),
        up.len(),
        data.len() as f64 / secs / 1e6
    );
}
