//! Benchmark a sedge session over a stream of records (one per line).
//!
//!     cargo run --release --example session_bench -- RECORDS.jsonl [N] [DICT|-] [HISTORY_KIB]
//!
//! Sends the first N records through a sender session and a receiver
//! session, verifies every record, and prints the total framed size and time.

use shannon_edge::{Options, PrimedModel, Session};
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let path = args
        .first()
        .expect("usage: session_bench RECORDS [N] [DICT]");
    let n: usize = args.get(1).map_or(1000, |v| v.parse().expect("N"));
    let data = std::fs::read(path).expect("read records");
    let records: Vec<&[u8]> = data
        .split(|&b| b == b'\n')
        .filter(|l| !l.is_empty())
        .take(n)
        .collect();
    let opts = Options::default();
    let (tx, rx) = match args.get(2).filter(|d| *d != "-") {
        Some(d) => {
            let dict = std::fs::read(d).expect("read dictionary");
            let model = PrimedModel::new(&dict, &opts);
            (
                Session::from_model(model.clone()),
                Session::from_model(model),
            )
        }
        None => (Session::new(&opts), Session::new(&opts)),
    };
    let (mut tx, mut rx) = match args.get(3) {
        Some(kib) => {
            let limit = kib.parse::<usize>().expect("HISTORY_KIB") << 10;
            (tx.with_history_limit(limit), rx.with_history_limit(limit))
        }
        None => (tx, rx),
    };
    let t = Instant::now();
    let (mut raw, mut packed) = (0usize, 0usize);
    for r in &records {
        let p = tx.compress(r);
        let back = rx.decompress(&p).expect("decode");
        assert_eq!(&back[..], *r, "round-trip mismatch");
        raw += r.len();
        packed += p.len();
    }
    let secs = t.elapsed().as_secs_f64();
    println!(
        "{} records, {} bytes -> {} bytes ({:.2}%), {:.1} s, {:.2} ms/record (both directions, verified)",
        records.len(),
        raw,
        packed,
        100.0 * packed as f64 / raw as f64,
        secs,
        1e3 * secs / records.len() as f64
    );
}
