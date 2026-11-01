//! Packet-level erasure code: every pattern of up to `m` losses recovers.

use shannon_edge::fec::{encode, recover};

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

#[test]
fn recovers_any_m_losses() {
    let mut rng = Rng(42);
    for &(g, m) in &[(1usize, 1usize), (4, 1), (8, 2), (16, 3), (32, 4), (200, 8)] {
        for _ in 0..30 {
            let data: Vec<Vec<u8>> = (0..g)
                .map(|_| {
                    let n = (rng.next() % 40) as usize;
                    (0..n).map(|_| rng.next() as u8).collect()
                })
                .collect();
            let refs: Vec<&[u8]> = data.iter().map(Vec::as_slice).collect();
            let par = encode(&refs, m);
            // Lose up to m of the g + m packets, data or parity.
            let lost_n = (rng.next() % (m as u64 + 1)) as usize;
            let mut lost = Vec::new();
            while lost.len() < lost_n {
                let i = (rng.next() % (g + m) as u64) as usize;
                if !lost.contains(&i) {
                    lost.push(i);
                }
            }
            let mut rx: Vec<Option<Vec<u8>>> = (0..g)
                .map(|i| (!lost.contains(&i)).then(|| data[i].clone()))
                .collect();
            let rp: Vec<Option<Vec<u8>>> = (0..m)
                .map(|j| (!lost.contains(&(g + j))).then(|| par[j].clone()))
                .collect();
            assert!(recover(&mut rx, &rp), "g={g} m={m} lost={lost:?}");
            let rx: Vec<Vec<u8>> = rx.into_iter().map(Option::unwrap).collect();
            assert_eq!(rx, data);
        }
    }
}

#[test]
fn too_many_losses_is_reported() {
    let data = [b"abc".as_slice(), b"de", b"", b"fghij"];
    let par = encode(&data, 2);
    let mut rx = vec![None, None, None, Some(b"fghij".to_vec())];
    let rp = vec![Some(par[0].clone()), Some(par[1].clone())];
    assert!(!recover(&mut rx, &rp));
    assert!(rx[0].is_none());
}
