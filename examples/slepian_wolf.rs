//! Slepian–Wolf prototype: an encoder that only XORs bits, a decoder that
//! does all the modelling.
//!
//!     cargo run --release --example slepian_wolf -- PACKETS.bin PACKET_LEN [STEP] [LIMIT] [DUMP.csv]
//!
//! On board, each packet is Gray-coded per byte and the encoder sends
//! syndrome bits: parity checks over pseudo-random subsets of the packet's
//! bits (a fixed sequence, the same on both ends), plus a CRC-24 to confirm
//! decoding. It keeps no state and computes no prediction.
//!
//! On the ground, the decoder predicts every bit of the packet from the
//! packets it already decoded (side information: per-bit adaptive
//! probabilities in contexts built from the previous two packets) and runs
//! belief propagation on the checks. Rateless with feedback: it asks for
//! more checks, STEP at a time, until the decoded packet satisfies every
//! check and the CRC. Reported: total bits sent (checks + CRC), the ideal
//! Slepian–Wolf cost under the same model (sum of -log2 p of the true bits)
//! and the number of feedback rounds. The first 10% of the packets only
//! train the model, as in `packet_robust`; LIMIT caps the test packets.
//!
//! Decoding: belief propagation, then ordered-statistics decoding (OSD-0
//! and OSD-1) on the BP posteriors. A candidate is accepted only if it
//! matches the CRC-24 *and* passes a typical-set test (its cost under the
//! model is at most m - 8 bits): without that test, a wrong but more likely
//! solution of the checks passed the CRC once in a few hundred thousand
//! candidates. DUMP.csv records, per packet, its index, the bits changed since the
//! previous packet (an encoder-side rate proxy), the checks needed and the
//! decoder's expected cost, for the no-feedback analysis.

use std::time::Instant;

const DEGREE: usize = 9;
const CRC_BITS: usize = 24;
const FLIPS: usize = 24;
const SLACK: f64 = -8.0;
const ITERS: usize = 60;

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 >> 12;
        self.0 ^= self.0 << 25;
        self.0 ^= self.0 >> 27;
        self.0.wrapping_mul(0x2545_f491_4f6c_dd1d)
    }
}

fn gray(b: u8) -> u8 {
    b ^ (b >> 1)
}

fn bits_of(p: &[u8]) -> Vec<u8> {
    p.iter()
        .flat_map(|&b| (0..8).rev().map(move |i| (b >> i) & 1))
        .collect()
}

/// Decoder-side model: per bit position and context, decayed counts.
struct SideInfo {
    c: Vec<[f64; 2]>,
    nctx: usize,
}

impl SideInfo {
    fn new(nbits: usize) -> Self {
        SideInfo {
            c: vec![[0.4, 0.4]; nbits * 16],
            nctx: 16,
        }
    }

    /// Contexts for each bit of packet t from packets t-1 and t-2 (raw bytes).
    fn contexts(prev: &[u8], prev2: &[u8]) -> Vec<usize> {
        let pred: Vec<u8> = prev
            .iter()
            .zip(prev2)
            .map(|(&a, &b)| gray((2 * a as i16 - b as i16) as u8))
            .collect();
        let plus1: Vec<u8> = prev.iter().map(|&a| gray(a.wrapping_add(1))).collect();
        let g1: Vec<u8> = prev.iter().map(|&a| gray(a)).collect();
        let g2: Vec<u8> = prev2.iter().map(|&a| gray(a)).collect();
        let (pb, p1, a1, a2) = (bits_of(&pred), bits_of(&plus1), bits_of(&g1), bits_of(&g2));
        (0..pb.len())
            .map(|k| {
                (pb[k] as usize) * 8 + (a1[k] as usize) * 4 + (p1[k] as usize) * 2 + a2[k] as usize
            })
            .collect()
    }

    fn p1(&self, k: usize, ctx: usize) -> f64 {
        let c = self.c[k * self.nctx + ctx];
        c[1] / (c[0] + c[1])
    }

    fn update(&mut self, ctx: &[usize], x: &[u8]) {
        for (k, (&cx, &b)) in ctx.iter().zip(x).enumerate() {
            let c = &mut self.c[k * self.nctx + cx];
            c[0] = c[0] * 0.98 + (b == 0) as u8 as f64;
            c[1] = c[1] * 0.98 + (b == 1) as u8 as f64;
        }
    }
}

/// Belief propagation for the syndrome: find x with H x = s, most likely
/// under the priors. Returns the hard decision.
fn bp(checks: &[Vec<usize>], s: &[u8], prior: &[f64]) -> Result<Vec<u8>, Vec<f64>> {
    let n = prior.len();
    // Edge lists.
    let mut var_edges: Vec<Vec<(usize, usize)>> = vec![Vec::new(); n];
    for (c, vs) in checks.iter().enumerate() {
        for (e, &v) in vs.iter().enumerate() {
            var_edges[v].push((c, e));
        }
    }
    let mut c2v: Vec<Vec<f64>> = checks.iter().map(|vs| vec![0.0; vs.len()]).collect();
    let mut x = vec![0u8; n];
    let mut total = prior.to_vec();
    for _ in 0..ITERS {
        // Variable totals.
        total = (0..n)
            .map(|v| prior[v] + var_edges[v].iter().map(|&(c, e)| c2v[c][e]).sum::<f64>())
            .collect();
        for v in 0..n {
            x[v] = (total[v] < 0.0) as u8;
        }
        if checks
            .iter()
            .zip(s)
            .all(|(vs, &sc)| vs.iter().fold(0u8, |a, &v| a ^ x[v]) == sc)
        {
            return Ok(x);
        }
        // Check update (tanh rule).
        for (c, vs) in checks.iter().enumerate() {
            let t: Vec<f64> = vs
                .iter()
                .enumerate()
                .map(|(e, &v)| {
                    ((total[v] - c2v[c][e]) / 2.0)
                        .tanh()
                        .clamp(-0.999_999_9, 0.999_999_9)
                })
                .collect();
            let sign = if s[c] == 1 { -1.0 } else { 1.0 };
            for (e, out) in c2v[c].iter_mut().enumerate() {
                let prod: f64 = t
                    .iter()
                    .enumerate()
                    .filter(|&(j, _)| j != e)
                    .map(|(_, &y)| y)
                    .product();
                *out = sign * 2.0 * prod.clamp(-0.999_999_9, 0.999_999_9).atanh();
            }
        }
    }
    Err(total)
}

const W: usize = (720 / 64) + 1;
type Row = [u64; W];

/// Ordered-statistics decoding: treat the most reliable bits as known
/// (hard decisions), solve the checks exactly for the least reliable
/// independent ones (OSD-0), and also try flipping each of the `flips`
/// least reliable non-pivot bits (OSD-1). Returns the candidates.
fn osd(checks: &[Vec<usize>], s: &[u8], llr: &[f64], flips: usize) -> Vec<Vec<u8>> {
    let n = llr.len();
    let mut rows: Vec<(Row, u8)> = checks
        .iter()
        .zip(s)
        .map(|(vs, &sc)| {
            let mut r = [0u64; W];
            for &v in vs {
                r[v / 64] ^= 1 << (v % 64);
            }
            (r, sc)
        })
        .collect();
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&a, &b| llr[a].abs().partial_cmp(&llr[b].abs()).unwrap());
    let mut pivots: Vec<usize> = Vec::new();
    let mut is_pivot = vec![false; n];
    for &c in &order {
        let rank = pivots.len();
        if rank == rows.len() {
            break;
        }
        let bit = |r: &Row| (r[c / 64] >> (c % 64)) & 1 == 1;
        let Some(p) = (rank..rows.len()).find(|&r| bit(&rows[r].0)) else {
            continue;
        };
        rows.swap(rank, p);
        let (pr, ps) = rows[rank];
        for (i, (r, sv)) in rows.iter_mut().enumerate() {
            if i != rank && bit(r) {
                for (a, b) in r.iter_mut().zip(&pr) {
                    *a ^= b;
                }
                *sv ^= ps;
            }
        }
        pivots.push(c);
        is_pivot[c] = true;
    }
    let rank = pivots.len();
    // Rows beyond the rank must be consistent (all-zero rows, zero syndrome).
    if rows[rank..].iter().any(|(_, sv)| *sv == 1) {
        return Vec::new();
    }
    let mut x: Vec<u8> = llr.iter().map(|&l| (l < 0.0) as u8).collect();
    let solve = |x: &mut Vec<u8>| {
        let mut xb = [0u64; W];
        for v in 0..n {
            if !is_pivot[v] && x[v] == 1 {
                xb[v / 64] |= 1 << (v % 64);
            }
        }
        for (r, &pc) in pivots.iter().enumerate() {
            let par: u32 = rows[r]
                .0
                .iter()
                .zip(&xb)
                .map(|(a, b)| (a & b).count_ones())
                .sum();
            x[pc] = rows[r].1 ^ (par & 1) as u8;
        }
    };
    solve(&mut x);
    let mut out = vec![x.clone()];
    for &f in order.iter().filter(|&&v| !is_pivot[v]).take(flips) {
        let mut y = x.clone();
        y[f] ^= 1;
        solve(&mut y);
        out.push(y);
    }
    out
}

fn crc24(bits: &[u8]) -> u32 {
    let mut c: u32 = 0xb7_04ce;
    for &b in bits {
        let top = ((c >> 23) as u8 & 1) ^ b;
        c = (c << 1) & 0xff_ffff;
        if top == 1 {
            c ^= 0x86_4cfb;
        }
    }
    c
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let data = std::fs::read(&args[0]).expect("read packets");
    let len: usize = args[1].parse().expect("PACKET_LEN");
    let step: usize = args.get(2).map_or(8, |v| v.parse().expect("STEP"));
    let limit: usize = args
        .get(3)
        .map_or(usize::MAX, |v| v.parse().expect("LIMIT"));
    let packets: Vec<&[u8]> = data.chunks_exact(len).collect();
    let n = len * 8;
    let split = packets.len() / 10;

    // The fixed check sequence, shared by both ends.
    let mut rng = Rng(0x51e9_1a2b);
    // Quasi-regular and rate-adaptive: check j takes the next DEGREE
    // variables of a sequence that runs through fresh random permutations
    // of all bits, so in every prefix of the checks each bit appears
    // floor or ceil(m * DEGREE / n) times.
    let mut seq: Vec<usize> = Vec::new();
    while seq.len() < n * DEGREE + DEGREE {
        let mut perm: Vec<usize> = (0..n).collect();
        for i in (1..n).rev() {
            perm.swap(i, (rng.next() % (i as u64 + 1)) as usize);
        }
        seq.extend(perm);
    }
    let all_checks: Vec<Vec<usize>> = (0..n)
        .map(|j| {
            let mut vs: Vec<usize> = seq[j * DEGREE..(j + 1) * DEGREE].to_vec();
            vs.sort_unstable();
            vs.dedup();
            vs
        })
        .collect();
    let mut dump = args
        .get(4)
        .map(|p| std::io::BufWriter::new(std::fs::File::create(p).expect("dump file")));
    let mut model = SideInfo::new(n);
    let (mut sent, mut ideal, mut rounds, mut raw_fallback, mut tested) =
        (0usize, 0f64, 0usize, 0usize, 0usize);
    let t0 = Instant::now();
    for t in 2..packets.len().min(split + limit) {
        let ctx = SideInfo::contexts(packets[t - 1], packets[t - 2]);
        let g: Vec<u8> = packets[t].iter().map(|&b| gray(b)).collect();
        let x = bits_of(&g);
        if t >= split {
            tested += 1;
            // --- Encoder (on board): syndromes of x; no model, no state.
            let syndrome: Vec<u8> = all_checks
                .iter()
                .map(|vs| vs.iter().fold(0u8, |a, &v| a ^ x[v]))
                .collect();
            let crc = crc24(&x);
            // --- Decoder (ground): priors from side information.
            let p1: Vec<f64> = (0..n).map(|k| model.p1(k, ctx[k])).collect();
            let prior: Vec<f64> = p1
                .iter()
                .map(|&p| ((1.0 - p) / p).ln().clamp(-30.0, 30.0))
                .collect();
            let h: f64 = x
                .iter()
                .zip(&p1)
                .map(|(&b, &p)| -(if b == 1 { p } else { 1.0 - p }).max(1e-12).log2())
                .sum();
            ideal += h;
            // Expected entropy (decoder knows it without knowing x).
            let expect: f64 = p1
                .iter()
                .map(|&p| {
                    let p = p.clamp(1e-12, 1.0 - 1e-12);
                    -(p * p.log2() + (1.0 - p) * (1.0 - p).log2())
                })
                .sum();
            let mut m = ((expect as usize) / step) * step;
            m = m.max(step);
            loop {
                rounds += 1;
                if m >= n {
                    raw_fallback += 1;
                    sent += n + CRC_BITS;
                    if let Some(f) = dump.as_mut() {
                        use std::io::Write;
                        writeln!(f, "{t},-1,{n},{expect:.1}").unwrap();
                    }
                    break;
                }
                let candidates = match bp(&all_checks[..m], &syndrome[..m], &prior) {
                    Ok(y) => vec![y],
                    Err(post) => osd(&all_checks[..m], &syndrome[..m], &post, FLIPS),
                };
                // Typical-set test: a candidate must be describable in about
                // the m bits received (its cost under the model), besides
                // matching the CRC; wrong solutions of the checks are far
                // costlier, which keeps false positives rare.
                let cost = |y: &[u8]| -> f64 {
                    y.iter()
                        .zip(&p1)
                        .map(|(&b, &p)| -(if b == 1 { p } else { 1.0 - p }).max(1e-12).log2())
                        .sum()
                };
                if let Some(y) = candidates
                    .into_iter()
                    .find(|y| cost(y) <= m as f64 + SLACK && crc24(y) == crc)
                {
                    if y != x {
                        let diff: Vec<usize> = (0..n).filter(|&k| y[k] != x[k]).collect();
                        panic!(
                            "false positive at packet {t}, m={m}: cost {:.1} vs true {:.1}, crc {:06x} {:06x}, diff {diff:?}",
                            cost(&y), cost(&x), crc24(&y), crc24(&x)
                        );
                    }
                    sent += m + CRC_BITS;
                    if let Some(f) = dump.as_mut() {
                        // Encoder-side rate proxy: bits changed since the
                        // previous packet (Gray domain).
                        let d: u32 = packets[t]
                            .iter()
                            .zip(packets[t - 1])
                            .map(|(&a, &b)| (gray(a) ^ gray(b)).count_ones())
                            .sum();
                        use std::io::Write;
                        writeln!(f, "{t},{d},{m},{expect:.1}").unwrap();
                    }
                    break;
                }
                m += step;
            }
        }
        model.update(&ctx, &x);
    }
    println!(
        "{tested} packets: sent {} bytes (checks + CRC-24), ideal Slepian-Wolf {:.0} bytes, \
         gap {:+.1}%, {:.2} rounds/packet, {raw_fallback} raw, {:.0}s",
        sent / 8,
        ideal / 8.0,
        100.0 * (sent as f64 / ideal - 1.0),
        rounds as f64 / tested as f64,
        t0.elapsed().as_secs_f64()
    );
}
