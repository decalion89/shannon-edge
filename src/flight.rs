//! Flight profile: a small, integer-only codec for spacecraft telemetry.
//!
//! Telemetry is a stream of integer samples (sensor readings, up to 16 bits)
//! sent in packets over a link that already guarantees integrity and order
//! (CCSDS frames carry their own CRC, Reed-Solomon coding and counters). A
//! [`FlightSession`] runs on each side of that link and keeps learning from
//! every packet, like [`crate::Session`], but with a model sized for flight
//! computers:
//!
//! * a **residual model**: the difference from the previous sample, coded
//!   with adaptive binary contexts (where CCSDS 121 uses fixed Rice codes);
//! * a **transition model**: orders 0, 1 and 2 over sample values ("which
//!   value tends to follow which"), mixed by a small online logistic mixer;
//! * a **switch**: each sample is coded by whichever model was cheaper on the
//!   recent samples. Both sides already know those samples, so they make the
//!   same choice and nothing is transmitted for it.
//!
//! Everything is integer arithmetic (costs use a fixed-point log2 table
//! built at compile time), so the two ends agree bit for bit on any CPU.
//! Memory is `~3 * 4 * 2^table_bits` bytes (default 2^18: ~3 MiB).
//!
//! Frame: LEB128 sample count, then the arithmetic-coded payload with a
//! minimal flush. There is no checksum or sequence number (lean, by design):
//! a corrupted or lost frame desynchronises the two ends, exactly as it
//! would for any adaptive coder; the link layer must prevent that.

use crate::coder::{Decoder, Encoder};
use crate::math::{squash, stretch};
use crate::Error;

/// `LOG2[p]` = -log2(p / 4096) in 1/256 bits, for 12-bit probabilities.
static NEG_LOG2: [u32; 4097] = {
    let mut t = [0u32; 4097];
    let mut p = 1;
    while p <= 4096 {
        // log2(p) in Q8: integer part, then 8 fractional bits by squaring.
        let mut n = 0;
        while (p >> (n + 1)) != 0 {
            n += 1;
        }
        let mut y: u64 = ((p as u64) << 16) >> n; // y in [1, 2) as Q16
        let mut frac = 0u32;
        let mut bit = 128;
        while bit != 0 {
            y = (y * y) >> 16;
            if y >= 2 << 16 {
                y >>= 1;
                frac |= bit;
            }
            bit >>= 1;
        }
        let log2p = (n << 8) | frac;
        t[p as usize] = (12 << 8) - log2p;
        p += 1;
    }
    t
};

/// Cost in 1/256 bits of coding `bit` with 12-bit probability `p1` of a 1.
#[inline]
pub(crate) fn cost(p1: u32, bit: u32) -> u32 {
    NEG_LOG2[if bit != 0 { p1 } else { 4096 - p1 } as usize]
}

/// Adaptive probability (16-bit) with a hit count for a 1/n learning rate.
#[derive(Clone, Copy)]
pub(crate) struct Counter(pub(crate) u32); // p16 << 8 | n

impl Counter {
    pub(crate) const FRESH: Counter = Counter(0x8000 << 8);
    #[inline]
    pub(crate) fn p12(self) -> u32 {
        ((self.0 >> 12) & 0xfff).clamp(1, 4095)
    }
    #[inline]
    pub(crate) fn update(&mut self, bit: u32) {
        let p = (self.0 >> 8) as i32;
        let n = self.0 & 0xff;
        let target = if bit != 0 { 65535 } else { 0 };
        let p = p + (target - p) / (n as i32 + 2);
        self.0 = ((p as u32) << 8) | (n + 1).min(60);
    }
}

#[derive(Clone)]
pub(crate) struct Table {
    pub(crate) t: Vec<Counter>,
    shift: u32,
}

impl Table {
    pub(crate) fn new(bits: u32) -> Self {
        Self {
            t: vec![Counter::FRESH; 1 << bits],
            shift: 64 - bits,
        }
    }
    #[inline]
    pub(crate) fn slot(&self, h: u64) -> usize {
        (h.wrapping_mul(0x9E37_79B9_7F4A_7C15) >> self.shift) as usize
    }
}

#[inline]
pub(crate) fn h2(a: u64, b: u64) -> u64 {
    (a.wrapping_mul(0x0000_0100_0000_01B3) ^ b).wrapping_mul(0xFF51_AFD7_ED55_8CCD)
}

/// Coding direction: encode a known bit, or decode one.
enum Io<'a, 'b> {
    Enc(&'a mut Encoder),
    Dec(&'a mut Decoder<'b>),
    /// Only measure the cost of a known bit (the model not chosen).
    Dry,
}

impl Io<'_, '_> {
    #[inline]
    fn bit(&mut self, p1: u32, bit: u32) -> u32 {
        match self {
            Io::Enc(e) => {
                e.encode(bit, p1);
                bit
            }
            Io::Dec(d) => d.decode(p1),
            Io::Dry => bit,
        }
    }
}

/// Orders 0/1/2 over sample values, mixed.
struct Transition {
    bits: u32,
    prev: u32,
    prev2: u32,
    t: [Table; 3],
    /// Mixer weights per tree depth, 1.0 = 65536.
    w: Vec<[i32; 4]>,
}

impl Transition {
    fn new(bits: u32, table_bits: u32) -> Self {
        Self {
            bits,
            prev: 0,
            prev2: 0,
            t: [
                Table::new(table_bits.min(bits + 1)),
                Table::new(table_bits),
                Table::new(table_bits),
            ],
            w: vec![[20_000; 4]; bits as usize],
        }
    }

    /// Code `value` (ignored when decoding); returns the value and its cost.
    fn code(&mut self, value: u32, io: &mut Io) -> (u32, u32) {
        let mut node = 1u32;
        let mut total = 0;
        for i in (0..self.bits).rev() {
            let ctx = [
                node as u64,
                h2(self.prev as u64 + 1, node as u64),
                h2(h2(self.prev2 as u64 + 7, self.prev as u64), node as u64),
            ];
            let s = [
                self.t[0].slot(ctx[0]),
                self.t[1].slot(ctx[1]),
                self.t[2].slot(ctx[2]),
            ];
            let x = [
                stretch(self.t[0].t[s[0]].p12() as i32),
                stretch(self.t[1].t[s[1]].p12() as i32),
                stretch(self.t[2].t[s[2]].p12() as i32),
                256,
            ];
            let w = &mut self.w[(self.bits - 1 - i) as usize];
            let dot: i64 = (0..4).map(|k| x[k] as i64 * w[k] as i64).sum();
            let p = squash(((dot >> 16) as i32).clamp(-2047, 2047)).clamp(1, 4095) as u32;
            let bit = io.bit(p, (value >> i) & 1);
            total += cost(p, bit);
            let err = ((bit as i32) << 12) - p as i32;
            for (wk, xk) in w.iter_mut().zip(x) {
                *wk += (xk * err) >> 10;
            }
            for (t, &sk) in self.t.iter_mut().zip(&s) {
                t.t[sk].update(bit);
            }
            node = (node << 1) | bit;
        }
        let v = node & ((1 << self.bits) - 1);
        self.prev2 = self.prev;
        self.prev = v;
        (v, total)
    }
}

/// Residual from the previous sample with adaptive contexts.
struct Residual {
    bits: u32,
    prev: u32,
    last_len: u32,
    t: Table,
}

impl Residual {
    fn new(bits: u32, table_bits: u32) -> Self {
        Self {
            bits,
            prev: 0,
            last_len: 0,
            t: Table::new(table_bits.min(16)),
        }
    }

    fn code(&mut self, value: u32, io: &mut Io) -> (u32, u32) {
        let r = value as i64 - self.prev as i64;
        let z = ((r << 1) ^ (r >> 63)) as u64; // zigzag
        let n = 64 - z.leading_zeros();
        let ctx = self.last_len.min(17) as u64;
        let mut total = 0;
        // Length in unary, then mantissa bits below the leading one.
        let mut len = 0u32;
        loop {
            let s = self.t.slot(h2(ctx * 64 + len as u64, 1));
            let c = &mut self.t.t[s];
            let p = c.p12();
            let bit = io.bit(p, (len < n) as u32);
            total += cost(p, bit);
            c.update(bit);
            if bit == 0 || len > self.bits + 1 {
                break;
            }
            len += 1;
        }
        let mut v: u64 = (len != 0) as u64;
        for i in (0..len.saturating_sub(1)).rev() {
            let depth = len - 1 - i;
            let key = if depth <= 3 {
                h2(len as u64 * 64 + depth as u64, v)
            } else {
                h2(len as u64, 999)
            };
            let s = self.t.slot(h2(key, 2));
            let c = &mut self.t.t[s];
            let p = c.p12();
            let bit = io.bit(p, ((z >> i) & 1) as u32);
            total += cost(p, bit);
            c.update(bit);
            v = (v << 1) | bit as u64;
        }
        let r = ((v >> 1) as i64) ^ -((v & 1) as i64);
        let out = ((self.prev as i64 + r) as u32) & ((1u32 << self.bits) - 1);
        self.prev = out;
        self.last_len = len;
        (out, total)
    }
}

/// One end of a telemetry link: compresses (or decompresses) packets of
/// integer samples, learning from every packet. Both ends must be created
/// with the same parameters and must process the same packets in order.
pub struct FlightSession {
    bits: u32,
    transition: Transition,
    residual: Residual,
    /// Exponentially decayed recent cost of each model (1/256 bits).
    cost_t: u64,
    cost_r: u64,
    last_other: u32,
}

impl FlightSession {
    /// A session for samples of `bits_per_sample` bits (1..=16), with model
    /// tables of `2^table_bits` entries (12..=24; memory ≈ 12 × 2^table_bits
    /// bytes).
    ///
    /// # Panics
    /// If a parameter is out of range.
    pub fn new(bits_per_sample: u32, table_bits: u32) -> Self {
        assert!(
            (1..=16).contains(&bits_per_sample),
            "1..=16 bits per sample"
        );
        assert!((12..=24).contains(&table_bits), "table_bits in 12..=24");
        Self {
            bits: bits_per_sample,
            transition: Transition::new(bits_per_sample, table_bits),
            residual: Residual::new(bits_per_sample, table_bits),
            cost_t: 0,
            cost_r: 0,
            last_other: 0,
        }
    }

    /// Bits per sample this session was created with.
    pub fn bits_per_sample(&self) -> u32 {
        self.bits
    }

    /// Code one sample; returns it and the cost actually paid for it, in
    /// 1/256 bits (the "surprise" of the chosen model).
    fn sample(&mut self, value: u32, io: &mut Io) -> (u32, u32) {
        let use_t = self.cost_t <= self.cost_r;
        let (v, ct, cr) = if use_t {
            let (v, ct) = self.transition.code(value, io);
            let (_, cr) = self.residual.code(v, &mut Io::Dry);
            (v, ct, cr)
        } else {
            let (v, cr) = self.residual.code(value, io);
            let (_, ct) = self.transition.code(v, &mut Io::Dry);
            (v, ct, cr)
        };
        self.cost_t = self.cost_t - (self.cost_t >> 6) + ct as u64;
        self.cost_r = self.cost_r - (self.cost_r >> 6) + cr as u64;
        self.last_other = if use_t { cr } else { ct };
        (v, if use_t { ct } else { cr })
    }

    /// Like [`Self::compress_scored`], and also appends to `other` the cost
    /// the *unused* model would have paid for each sample (both models
    /// evaluate every sample; only the cheaper one on recent samples codes
    /// it). Same frame as `compress`.
    pub fn compress_scored_both(
        &mut self,
        samples: &[u16],
        surprise: &mut Vec<u32>,
        other: &mut Vec<u32>,
    ) -> Vec<u8> {
        let mut out = Vec::with_capacity(4 + samples.len());
        put_varint(&mut out, samples.len() as u64);
        let mut enc = Encoder::new(samples.len());
        {
            let mut io = Io::Enc(&mut enc);
            for &s in samples {
                assert!(
                    (s as u32) >> self.bits == 0,
                    "sample {s} does not fit in {} bits",
                    self.bits
                );
                surprise.push(self.sample(s as u32, &mut io).1);
                other.push(self.last_other);
            }
        }
        out.extend_from_slice(&enc.finish_short());
        out
    }

    /// Compress one packet and learn from it.
    ///
    /// # Panics
    /// If a sample does not fit in `bits_per_sample` bits.
    pub fn compress(&mut self, samples: &[u16]) -> Vec<u8> {
        self.compress_scored(samples, &mut Vec::new())
    }

    /// Like [`Self::compress`], and also appends to `surprise` the cost of
    /// every sample in 1/256 bits: how unexpected it was to the model, given
    /// everything learned so far. It is an anomaly score that costs nothing
    /// extra to compute, and the receiver gets the very same values from
    /// [`Self::decompress_scored`] without anything being transmitted.
    ///
    /// # Panics
    /// If a sample does not fit in `bits_per_sample` bits.
    pub fn compress_scored(&mut self, samples: &[u16], surprise: &mut Vec<u32>) -> Vec<u8> {
        let mut out = Vec::with_capacity(4 + samples.len());
        put_varint(&mut out, samples.len() as u64);
        let mut enc = Encoder::new(samples.len());
        {
            let mut io = Io::Enc(&mut enc);
            for &s in samples {
                assert!(
                    (s as u32) >> self.bits == 0,
                    "sample {s} does not fit in {} bits",
                    self.bits
                );
                surprise.push(self.sample(s as u32, &mut io).1);
            }
        }
        out.extend_from_slice(&enc.finish_short());
        out
    }

    /// Decompress one packet and learn from it.
    pub fn decompress(&mut self, frame: &[u8]) -> Result<Vec<u16>, Error> {
        self.decompress_scored(frame, &mut Vec::new())
    }

    /// Like [`Self::decompress`], and also appends the per-sample surprise
    /// (identical to what the sender's [`Self::compress_scored`] computed).
    pub fn decompress_scored(
        &mut self,
        frame: &[u8],
        surprise: &mut Vec<u32>,
    ) -> Result<Vec<u16>, Error> {
        let mut pos = 0;
        let n = get_varint(frame, &mut pos)?;
        if n > (frame.len() as u64 + 16) * 8 * 64 {
            // Far more samples than any coder could fit in this frame.
            return Err(Error::TooLarge(n));
        }
        let mut dec = Decoder::new(&frame[pos..]);
        let mut io = Io::Dec(&mut dec);
        Ok((0..n)
            .map(|_| {
                let (v, c) = self.sample(0, &mut io);
                surprise.push(c);
                v as u16
            })
            .collect())
    }
}

pub(crate) fn put_varint(out: &mut Vec<u8>, mut v: u64) {
    while v >= 0x80 {
        out.push((v as u8) | 0x80);
        v >>= 7;
    }
    out.push(v as u8);
}

fn get_varint(b: &[u8], pos: &mut usize) -> Result<u64, Error> {
    let mut v = 0u64;
    for shift in (0..35).step_by(7) {
        let byte = *b.get(*pos).ok_or(Error::Truncated)?;
        *pos += 1;
        v |= ((byte & 0x7f) as u64) << shift;
        if byte < 0x80 {
            return Ok(v);
        }
    }
    Err(Error::TooLarge(v))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn neg_log2_table_is_accurate() {
        for p in 1..=4096u32 {
            let exact = -(p as f64 / 4096.0).log2() * 256.0;
            assert!((NEG_LOG2[p as usize] as f64 - exact).abs() <= 1.5, "p={p}");
        }
        assert_eq!(NEG_LOG2[4096], 0);
        assert_eq!(NEG_LOG2[2048], 256);
    }
}
