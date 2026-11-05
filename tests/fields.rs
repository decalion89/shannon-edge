//! Record transforms: exact inversion, learning a planted relation, uplink format.

use shannon_edge::fields::{Layout, RecordTransform};

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

/// ECG-like records: two random walks, a derived field (III = II - I + c) and
/// a half-sum one (aVR = -(I+II)/2 + c), an unrelated noisy field.
fn records(n: usize) -> Vec<Vec<u8>> {
    let mut rng = Rng(7);
    let (mut a, mut b) = (0i64, 100i64);
    (0..n)
        .map(|_| {
            a += (rng.next() % 21) as i64 - 10;
            b += (rng.next() % 21) as i64 - 10;
            let iii = b - a + 611;
            let avr = (-(a + b)) >> 1;
            let noise = (rng.next() % 50_000) as i64 - 25_000;
            let mut r = Vec::new();
            for v in [a, b, iii, avr, noise] {
                r.extend_from_slice(&(v as i16).to_le_bytes());
            }
            r.extend_from_slice(&(rng.next() as u32).to_be_bytes());
            r
        })
        .collect()
}

#[test]
fn learns_the_planted_relations_and_inverts_exactly() {
    let recs = records(20_000);
    let lay = Layout::parse("i16le*5, u32be").unwrap();
    assert_eq!(lay.len(), 14);
    for deltas in [false, true] {
        let tf = RecordTransform::learn(
            lay.clone(),
            recs[..2000].iter().map(Vec::as_slice),
            deltas,
            2.0,
        );
        let targets: Vec<usize> = tf.relations().iter().map(|r| r.target).collect();
        assert_eq!(tf.relations().len(), 2, "{:?}", tf.relations());
        assert!(
            targets.iter().all(|t| [0, 1, 2, 3].contains(t)),
            "{targets:?}"
        );
        let up = tf.to_bytes();
        let (mut tx, mut rx) = (
            RecordTransform::from_bytes(&up).unwrap(),
            RecordTransform::from_bytes(&up).unwrap(),
        );
        for r in &recs {
            let f = tx.forward(r);
            assert_eq!(&rx.inverse(&f), r);
        }
    }
}

#[test]
fn random_layouts_and_values_round_trip() {
    let mut rng = Rng(99);
    for spec in [
        "u8,i8,u16be,i16be,u32le,i32be,u64le,i64be",
        "b3,i16le*4,b1,u32be*2",
        "i64le*3",
    ] {
        let lay = Layout::parse(spec).unwrap();
        let recs: Vec<Vec<u8>> = (0..3000)
            .map(|_| (0..lay.len()).map(|_| rng.next() as u8).collect())
            .collect();
        let tf = RecordTransform::learn(lay, recs[..300].iter().map(Vec::as_slice), true, 64.0);
        let up = tf.to_bytes();
        let (mut tx, mut rx) = (
            RecordTransform::from_bytes(&up).unwrap(),
            RecordTransform::from_bytes(&up).unwrap(),
        );
        for r in &recs {
            assert_eq!(&rx.inverse(&tx.forward(r)), r, "{spec}");
        }
    }
}

#[test]
fn garbage_uplinks_are_rejected_not_trusted() {
    assert!(RecordTransform::from_bytes(b"").is_err());
    assert!(RecordTransform::from_bytes(b"SEDGREL1").is_err());
    let lay = Layout::parse("i16le*5, u32be").unwrap();
    let recs = records(3000);
    let good = RecordTransform::learn(lay, recs.iter().map(Vec::as_slice), true, 2.0).to_bytes();
    let mut rng = Rng(3);
    for _ in 0..2000 {
        let mut b = good.clone();
        let i = (rng.next() as usize) % b.len();
        b[i] ^= 1 << (rng.next() % 8);
        if b.len() > 8 && rng.next() % 4 == 0 {
            b.truncate((rng.next() as usize) % b.len());
        }
        // Either rejected, or a valid transform that still inverts its own output.
        if let Ok(mut tx) = RecordTransform::from_bytes(&b) {
            let mut rx = RecordTransform::from_bytes(&b).unwrap();
            let len = tx.layout().len();
            let r: Vec<u8> = (0..len).map(|_| rng.next() as u8).collect();
            assert_eq!(rx.inverse(&tx.forward(&r)), r);
        }
    }
    assert!(
        Layout::parse("").is_none()
            && Layout::parse("u12").is_none()
            && Layout::parse("x8").is_none()
    );
}
