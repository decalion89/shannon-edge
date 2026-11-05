//! Research prototype: how small can a telemetry model be and still beat
//! CCSDS 121? Light models over 16-bit sample codes, each run as a learning
//! session over 256-sample packets (every packet closed with the minimal
//! flush, plus 3 bytes of lean framing), every packet decoded and verified.
//!
//!     cargo run --release --example telemetry_lite -- CODES.u16 [CODEBOOK_BYTES]
//!
//! * `o1`: each sample predicted from the previous sample's code (binary
//!   decomposition of the code, one adaptive counter per previous code and
//!   tree node).
//! * `o1o2`: orders 0, 1 and 2 over codes, mixed by a small logistic mixer.
//! * `delta`: residual from the previous sample (like CCSDS 121), coded with
//!   adaptive binary contexts instead of Rice codes.
//! * `a|b`: per sample, whichever of two models has been cheaper recently
//!   (decayed cost, computed identically on both sides, nothing sent).
//!
//! Prototype only: it uses floating point for mixing and cost tracking, so
//! its output is only guaranteed to decode on the same platform. A library
//! version must be integer-only like the main model.

use shannon_edge::coder::{Decoder, Encoder};
use std::time::Instant;

const PACKET: usize = 256;
const FRAME: usize = 3; // lean frame: kind + 2-byte length

/// Adaptive probability: 16-bit p(1) and a count for a 1/n learning rate.
#[derive(Clone, Copy)]
struct Counter {
    p: u16,
    n: u8,
}

impl Default for Counter {
    fn default() -> Self {
        Self { p: 32768, n: 0 }
    }
}

impl Counter {
    #[inline]
    fn p12(self) -> u32 {
        ((self.p >> 4) as u32).clamp(1, 4095)
    }
    #[inline]
    fn update(&mut self, bit: u32, limit: u8) {
        let target = if bit != 0 { 65535i32 } else { 0 };
        let p = self.p as i32;
        let rate = self.n as i32 + 2;
        self.p = (p + (target - p) / rate) as u16;
        if self.n < limit {
            self.n += 1;
        }
    }
}

/// Hashed table of counters.
struct Table {
    t: Vec<Counter>,
    mask: usize,
}

impl Table {
    fn new(bits: u32) -> Self {
        Self {
            t: vec![Counter::default(); 1 << bits],
            mask: (1 << bits) - 1,
        }
    }
    #[inline]
    fn slot(&self, h: u64) -> usize {
        (h.wrapping_mul(0x9E37_79B9_7F4A_7C15) >> 40) as usize & self.mask
    }
}

#[inline]
fn h2(a: u64, b: u64) -> u64 {
    (a.wrapping_mul(0x100_0000_01B3) ^ b).wrapping_mul(0xFF51_AFD7_ED55_8CCD)
}

/// Something that codes one sample at a time, identically on both sides.
trait Model {
    fn code(&mut self, value: u32, io: &mut dyn BitIo) -> u32;
}

/// Either an encoder (bit known) or a decoder (bit read).
trait BitIo {
    fn bit(&mut self, p12: u32, bit: u32) -> u32;
}

struct Enc(Encoder);
impl BitIo for Enc {
    fn bit(&mut self, p12: u32, bit: u32) -> u32 {
        self.0.encode(bit, p12);
        bit
    }
}

struct Dec<'a>(Decoder<'a>);
impl BitIo for Dec<'_> {
    fn bit(&mut self, p12: u32, _bit: u32) -> u32 {
        self.0.decode(p12)
    }
}

/// Runs a model on a known value without coding, measuring its cost in bits
/// (both sides can do this after the value is known).
struct Cost(f64);
impl BitIo for Cost {
    fn bit(&mut self, p12: u32, bit: u32) -> u32 {
        let p = p12 as f64 / 4096.0;
        self.0 -= if bit != 0 { p.log2() } else { (1.0 - p).log2() };
        bit
    }
}

/// Wraps an IO and also measures cost.
struct Measured<'a> {
    io: &'a mut dyn BitIo,
    cost: f64,
}
impl BitIo for Measured<'_> {
    fn bit(&mut self, p12: u32, bit: u32) -> u32 {
        let b = self.io.bit(p12, bit);
        let p = p12 as f64 / 4096.0;
        self.cost -= if b != 0 { p.log2() } else { (1.0 - p).log2() };
        b
    }
}

/// Codes each sample with whichever model has been cheaper recently
/// (exponentially decayed cost). Both sides compute the same choice from
/// already-known samples, so no selector is transmitted; the other model is
/// still trained on every sample.
struct Switch {
    a: Box<dyn Model>,
    b: Box<dyn Model>,
    cost_a: f64,
    cost_b: f64,
}

impl Model for Switch {
    fn code(&mut self, value: u32, io: &mut dyn BitIo) -> u32 {
        let use_a = self.cost_a <= self.cost_b;
        let (first, second) = if use_a {
            (&mut self.a, &mut self.b)
        } else {
            (&mut self.b, &mut self.a)
        };
        let mut m = Measured { io, cost: 0.0 };
        let v = first.code(value, &mut m);
        let mut c = Cost(0.0);
        second.code(v, &mut c);
        let (ca, cb) = if use_a { (m.cost, c.0) } else { (c.0, m.cost) };
        self.cost_a = self.cost_a * 0.98 + ca;
        self.cost_b = self.cost_b * 0.98 + cb;
        v
    }
}

// --- o1: P(code | previous code) by binary decomposition -------------------

struct O1 {
    bits: u32,
    prev: u32,
    t: Table,
}

impl Model for O1 {
    fn code(&mut self, value: u32, io: &mut dyn BitIo) -> u32 {
        let mut node = 1u32;
        for i in (0..self.bits).rev() {
            let s = self.t.slot(h2(self.prev as u64, node as u64));
            let c = &mut self.t.t[s];
            let bit = io.bit(c.p12(), (value >> i) & 1);
            c.update(bit, 60);
            node = (node << 1) | bit;
        }
        let v = node & ((1 << self.bits) - 1);
        self.prev = v;
        v
    }
}

// --- o1o2: orders 0/1/2 mixed ------------------------------------------------

fn stretch(p: f32) -> f32 {
    (p / (1.0 - p)).ln()
}
fn squash(x: f32) -> f32 {
    1.0 / (1.0 + (-x).exp())
}

struct O1O2 {
    bits: u32,
    prev: u32,
    prev2: u32,
    t: [Table; 3],
    w: Vec<[f32; 4]>,
}

impl Model for O1O2 {
    fn code(&mut self, value: u32, io: &mut dyn BitIo) -> u32 {
        let mut node = 1u32;
        for i in (0..self.bits).rev() {
            let ctx = [
                node as u64,
                h2(self.prev as u64 + 1, node as u64),
                h2(h2(self.prev2 as u64 + 7, self.prev as u64), node as u64),
            ];
            let slots: Vec<usize> = (0..3).map(|k| self.t[k].slot(ctx[k])).collect();
            let x: Vec<f32> = (0..3)
                .map(|k| stretch(self.t[k].t[slots[k]].p12() as f32 / 4096.0))
                .chain(std::iter::once(0.3))
                .collect();
            let wi = (self.bits - 1 - i) as usize;
            let dot: f32 = (0..4).map(|k| x[k] * self.w[wi][k]).sum();
            let p = squash(dot).clamp(1.0 / 4096.0, 4095.0 / 4096.0);
            let bit = io.bit(((p * 4096.0) as u32).clamp(1, 4095), (value >> i) & 1);
            let err = bit as f32 - p;
            for (w, xk) in self.w[wi].iter_mut().zip(&x) {
                *w += 0.02 * err * xk;
            }
            for (t, &s) in self.t.iter_mut().zip(&slots) {
                t.t[s].update(bit, 60);
            }
            node = (node << 1) | bit;
        }
        let v = node & ((1 << self.bits) - 1);
        self.prev2 = self.prev;
        self.prev = v;
        v
    }
}

// --- delta: adaptive coding of the residual from the previous sample ---------

struct Delta {
    prev: u32,
    last_mag: u32,
    t: Table,
}

impl Model for Delta {
    fn code(&mut self, value: u32, io: &mut dyn BitIo) -> u32 {
        // zigzag residual
        let r = value as i64 - self.prev as i64;
        let z = ((r << 1) ^ (r >> 63)) as u64;
        let n = 64 - z.leading_zeros(); // significant bits, 0 for z == 0
        let ctx = self.last_mag.min(17) as u64;
        // unary length: n ones then a zero, each with context (ctx, position)
        let mut len = 0u32;
        loop {
            let s = self.t.slot(h2(ctx * 64 + len as u64, 1));
            let c = &mut self.t.t[s];
            let bit = io.bit(c.p12(), (len < n) as u32);
            c.update(bit, 60);
            if bit == 0 {
                break;
            }
            len += 1;
        }
        // mantissa below the leading 1, top bits with context
        let mut v: u64 = if len == 0 { 0 } else { 1 };
        for i in (0..len.saturating_sub(1)).rev() {
            let depth = len - 1 - i;
            let key = if depth <= 3 {
                h2(len as u64 * 64 + depth as u64, v)
            } else {
                h2(len as u64, 999)
            };
            let s = self.t.slot(h2(key, 2));
            let c = &mut self.t.t[s];
            let bit = io.bit(c.p12(), ((z >> i) & 1) as u32);
            c.update(bit, 60);
            v = (v << 1) | bit as u64;
        }
        let r = ((v >> 1) as i64) ^ -((v & 1) as i64);
        let out = (self.prev as i64 + r) as u32;
        self.prev = out;
        self.last_mag = len;
        out
    }
}

fn run(
    name: &str,
    codes: &[u16],
    mut enc_model: Box<dyn Model>,
    mut dec_model: Box<dyn Model>,
    extra: usize,
) {
    let t = Instant::now();
    let mut total = extra;
    for packet in codes.chunks_exact(PACKET) {
        let mut io = Enc(Encoder::new(PACKET));
        for &v in packet {
            enc_model.code(v as u32, &mut io);
        }
        let bytes = io.0.finish_short();
        total += bytes.len() + FRAME;
        let mut io = Dec(Decoder::new(&bytes));
        for &v in packet {
            let got = dec_model.code(0, &mut io);
            assert_eq!(got, v as u32, "{name}: mismatch");
        }
    }
    let secs = t.elapsed().as_secs_f64();
    let n = codes.len() / PACKET * PACKET;
    println!(
        "{name:6} {total:>9} bytes  {:6.2} Msamples/s (encode+decode, verified)",
        n as f64 / secs / 1e6
    );
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let raw = std::fs::read(&args[0]).expect("read codes");
    let extra: usize = args.get(1).map_or(0, |v| v.parse().unwrap());
    let codes: Vec<u16> = raw
        .chunks_exact(2)
        .map(|c| u16::from_le_bytes([c[0], c[1]]))
        .collect();
    let max = *codes.iter().max().unwrap() as u32;
    let bits = (32 - max.leading_zeros()).max(1);
    println!("{}: {} samples, codes < 2^{bits}", args[0], codes.len());
    let o1 = || {
        Box::new(O1 {
            bits,
            prev: 0,
            t: Table::new(22),
        }) as Box<dyn Model>
    };
    run("o1", &codes, o1(), o1(), extra);
    let o12 = || {
        Box::new(O1O2 {
            bits,
            prev: 0,
            prev2: 0,
            t: [Table::new(16), Table::new(22), Table::new(22)],
            w: vec![[0.3; 4]; bits as usize],
        }) as Box<dyn Model>
    };
    run("o1o2", &codes, o12(), o12(), extra);
    let d = || {
        Box::new(Delta {
            prev: 0,
            last_mag: 0,
            t: Table::new(16),
        }) as Box<dyn Model>
    };
    run("delta", &codes, d(), d(), extra);
    let sw = |a: Box<dyn Model>, b: Box<dyn Model>| {
        Box::new(Switch {
            a,
            b,
            cost_a: 0.0,
            cost_b: 0.0,
        }) as Box<dyn Model>
    };
    run("o1|dlt", &codes, sw(o1(), d()), sw(o1(), d()), extra);
    run("o12|dl", &codes, sw(o12(), d()), sw(o12(), d()), extra);
}
