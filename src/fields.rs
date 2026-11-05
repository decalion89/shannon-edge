//! Record transforms learned on the ground: field relations and numeric deltas.
//!
//! A fixed-length record is a sequence of fields. Two reversible, integer-only
//! transforms run before a packet codec (and are undone after it):
//!
//! * **Relations** (within a record, no state): field `t` is replaced by
//!   `r = x_t − ⌊(a·x_i + b·x_j) / 2⌋ (mod 2^bits)`, with small integer `a`,
//!   `b`. When `t` is physically derived from `i` and `j`, as are the derived
//!   leads of a 12-lead ECG, `r` is (nearly) constant and costs almost nothing.
//!   Relations survive packet loss: a record is decoded from itself.
//! * **Field deltas** (optional, across records): a field is replaced by the
//!   zigzag of its difference from the previous record (mod 2^bits). This is
//!   numeric prediction of order 1, which a byte-level model cannot do across
//!   a carry. A lost record breaks the chain, so use it with lossless links
//!   or with epochs.
//!
//! [`RecordTransform::learn`] finds both from history (what the ground has
//! received); [`RecordTransform::to_bytes`] gives a few dozen bytes to uplink.
//! `bench/results/general_data.md` has the measurements.

use crate::Error;

/// One field of a record.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Field {
    /// Byte offset in the record.
    pub offset: usize,
    /// Width in bytes: 1, 2, 4 or 8.
    pub width: usize,
    /// Integer field (relations and deltas apply) or opaque bytes.
    pub integer: bool,
    /// Two's-complement signed (only for integer fields).
    pub signed: bool,
    /// Big-endian byte order.
    pub big_endian: bool,
}

/// The fields of a fixed-length record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Layout {
    fields: Vec<Field>,
    len: usize,
}

impl Layout {
    /// Parse a layout such as `"u32le,u16le*7"` or `"i16le*12"`. Types: `u8`,
    /// `i8`, `u16le`, `u16be`, `i16le`, `i16be`, `u32le`, `u32be`, `i32le`,
    /// `i32be`, `u64le`, `u64be`, `i64le`, `i64be`, and `bN` for N opaque bytes.
    /// `*n` repeats a type.
    pub fn parse(spec: &str) -> Option<Self> {
        let mut fields = Vec::new();
        let mut off = 0;
        for item in spec.split(',').map(str::trim).filter(|s| !s.is_empty()) {
            let (ty, n) = match item.split_once('*') {
                Some((t, n)) => (t, n.parse::<usize>().ok()?),
                None => (item, 1),
            };
            for _ in 0..n {
                let f = if let Some(w) = ty.strip_prefix('b') {
                    let width = w.parse::<usize>().ok()?;
                    Field {
                        offset: off,
                        width,
                        integer: false,
                        signed: false,
                        big_endian: false,
                    }
                } else {
                    let signed = ty.starts_with('i');
                    let rest = ty.get(1..)?;
                    let (bits, end) = match rest {
                        "8" => (8, None),
                        _ => (
                            rest.get(..rest.len() - 2)?.parse::<usize>().ok()?,
                            Some(&rest[rest.len() - 2..]),
                        ),
                    };
                    if !(ty.starts_with('u') || signed) || ![8, 16, 32, 64].contains(&bits) {
                        return None;
                    }
                    let big_endian = match end {
                        None => false,
                        Some("le") => false,
                        Some("be") => true,
                        _ => return None,
                    };
                    Field {
                        offset: off,
                        width: bits / 8,
                        integer: true,
                        signed,
                        big_endian,
                    }
                };
                if f.width == 0 {
                    return None;
                }
                off += f.width;
                fields.push(f);
            }
        }
        (!fields.is_empty()).then_some(Self { fields, len: off })
    }

    /// Record length in bytes.
    pub fn len(&self) -> usize {
        self.len
    }

    /// Always false: a parsed layout has at least one field.
    pub fn is_empty(&self) -> bool {
        self.fields.is_empty()
    }

    /// The fields.
    pub fn fields(&self) -> &[Field] {
        &self.fields
    }

    fn get(&self, rec: &[u8], k: usize) -> u64 {
        let f = &self.fields[k];
        let b = &rec[f.offset..f.offset + f.width];
        let mut v = 0u64;
        for i in 0..f.width {
            let byte = if f.big_endian {
                b[i]
            } else {
                b[f.width - 1 - i]
            };
            v = (v << 8) | byte as u64;
        }
        v
    }

    fn put(&self, rec: &mut [u8], k: usize, v: u64) {
        let f = &self.fields[k];
        for i in 0..f.width {
            let byte = (v >> (8 * i)) as u8;
            let at = if f.big_endian { f.width - 1 - i } else { i };
            rec[f.offset + at] = byte;
        }
    }

    /// Value as a signed integer (sign-extended if the field is signed).
    fn value(&self, rec: &[u8], k: usize) -> i64 {
        let f = &self.fields[k];
        let v = self.get(rec, k);
        let bits = 8 * f.width as u32;
        if f.signed && bits < 64 {
            ((v << (64 - bits)) as i64) >> (64 - bits)
        } else {
            v as i64
        }
    }

    fn mask(&self, k: usize) -> u64 {
        let bits = 8 * self.fields[k].width as u32;
        if bits == 64 {
            u64::MAX
        } else {
            (1u64 << bits) - 1
        }
    }
}

/// `x_target = ⌊(a·x_i + b·x_j) / 2⌋ + r`.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Relation {
    pub target: usize,
    pub i: usize,
    pub j: usize,
    pub a: i8,
    pub b: i8,
}

/// A learned, reversible record transform (see the module docs).
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RecordTransform {
    layout: Layout,
    relations: Vec<Relation>,
    delta: Vec<bool>,
    prev_fwd: Option<Vec<u8>>,
    prev_inv: Option<Vec<u8>>,
}

/// Magic of a serialised [`RecordTransform`].
pub const TRANSFORM_MAGIC: [u8; 8] = *b"SEDGREL1";

fn zigzag(d: i64, mask: u64) -> u64 {
    (((d << 1) ^ (d >> 63)) as u64) & mask
}

fn unzigzag(z: u64) -> i64 {
    ((z >> 1) as i64) ^ -((z & 1) as i64)
}

/// Sign-extend `v & mask` to i64 (two's complement of the field's width).
fn signed_mod(v: i64, mask: u64) -> i64 {
    if mask == u64::MAX {
        return v;
    }
    let bits = 64 - mask.leading_zeros();
    ((v as u64 & mask) << (64 - bits)) as i64 >> (64 - bits)
}

/// Empirical entropy in bits per value.
fn entropy(v: &mut [u64]) -> f64 {
    if v.is_empty() {
        return 0.0;
    }
    v.sort_unstable();
    let n = v.len() as f64;
    let mut h = 0.0;
    let mut i = 0;
    while i < v.len() {
        let mut j = i + 1;
        while j < v.len() && v[j] == v[i] {
            j += 1;
        }
        let p = (j - i) as f64 / n;
        h -= p * p.log2();
        i = j;
    }
    h
}

impl RecordTransform {
    /// The identity transform for `layout`.
    pub fn identity(layout: Layout) -> Self {
        let n = layout.fields.len();
        Self {
            layout,
            relations: Vec::new(),
            delta: vec![false; n],
            prev_fwd: None,
            prev_inv: None,
        }
    }

    /// Learn relations (and, if `deltas`, per-field deltas) from `history`.
    ///
    /// For each integer field (most expensive first) and each pair of other
    /// integer fields that are not targets, fit `x_t ≈ (a·x_i + b·x_j)/2` by
    /// least squares on up to 4096 records, round `a`, `b` to −4..4, and keep
    /// the pair whose residual has the lowest entropy (on up to 65536
    /// records), if it is below `max_bits` and below the field's own delta
    /// entropy. A field gets a delta if its zigzag delta has lower entropy
    /// than its value, after relations.
    pub fn learn<'a>(
        layout: Layout,
        history: impl IntoIterator<Item = &'a [u8]>,
        deltas: bool,
        max_bits: f64,
    ) -> Self {
        let recs: Vec<&[u8]> = history
            .into_iter()
            .filter(|r| r.len() == layout.len)
            .take(65536)
            .collect();
        let mut t = Self::identity(layout);
        if recs.len() < 16 {
            return t;
        }
        let lay = t.layout.clone();
        let nf = lay.fields.len();
        let ints: Vec<usize> = (0..nf).filter(|&k| lay.fields[k].integer).collect();
        let vals: Vec<Vec<i64>> = (0..nf)
            .map(|k| {
                if lay.fields[k].integer {
                    recs.iter().map(|r| lay.value(r, k)).collect()
                } else {
                    Vec::new()
                }
            })
            .collect();
        let delta_h = |k: usize| {
            let m = lay.mask(k);
            let mut z: Vec<u64> = vals[k]
                .windows(2)
                .map(|w| zigzag(w[1].wrapping_sub(w[0]), m))
                .collect();
            entropy(&mut z)
        };
        let mut cost: Vec<(f64, usize)> = ints.iter().map(|&k| (delta_h(k), k)).collect();
        cost.sort_by(|x, y| y.0.total_cmp(&x.0));
        let mut targets = vec![false; nf];
        let mut predictors = vec![false; nf];
        let fit_n = recs.len().min(4096);
        for &(own_h, k) in &cost {
            if predictors[k] {
                continue;
            }
            let mut best: Option<(f64, Relation)> = None;
            for (pi, &i) in ints.iter().enumerate() {
                for &j in &ints[pi + 1..] {
                    if i == k || j == k || targets[i] || targets[j] {
                        continue;
                    }
                    // Least squares for y = p*xi + q*xj (centred).
                    let (xi, xj, y) = (&vals[i][..fit_n], &vals[j][..fit_n], &vals[k][..fit_n]);
                    let mean =
                        |v: &[i64]| v.iter().map(|&x| x as f64).sum::<f64>() / v.len() as f64;
                    let (mi, mj, my) = (mean(xi), mean(xj), mean(y));
                    let (mut sii, mut sjj, mut sij, mut siy, mut sjy) = (0.0, 0.0, 0.0, 0.0, 0.0);
                    for n in 0..fit_n {
                        let (a, b, c) = (xi[n] as f64 - mi, xj[n] as f64 - mj, y[n] as f64 - my);
                        sii += a * a;
                        sjj += b * b;
                        sij += a * b;
                        siy += a * c;
                        sjy += b * c;
                    }
                    let det = sii * sjj - sij * sij;
                    if det.abs() < 1e-9 {
                        continue;
                    }
                    let p = (siy * sjj - sjy * sij) / det;
                    let q = (sjy * sii - siy * sij) / det;
                    let (a, b) = ((2.0 * p).round(), (2.0 * q).round());
                    if !(-4.0..=4.0).contains(&a)
                        || !(-4.0..=4.0).contains(&b)
                        || (a == 0.0 && b == 0.0)
                    {
                        continue;
                    }
                    let rel = Relation {
                        target: k,
                        i,
                        j,
                        a: a as i8,
                        b: b as i8,
                    };
                    let m = lay.mask(k);
                    let mut r: Vec<u64> = (0..vals[k].len())
                        .map(|n| {
                            let pred = (rel.a as i64)
                                .wrapping_mul(vals[i][n])
                                .wrapping_add((rel.b as i64).wrapping_mul(vals[j][n]))
                                >> 1;
                            (vals[k][n].wrapping_sub(pred)) as u64 & m
                        })
                        .collect();
                    let h = entropy(&mut r);
                    if best.as_ref().map_or(true, |(bh, _)| h < *bh) {
                        best = Some((h, rel));
                    }
                }
            }
            if let Some((h, rel)) = best {
                if h < max_bits && h < own_h {
                    targets[k] = true;
                    predictors[rel.i] = true;
                    predictors[rel.j] = true;
                    t.relations.push(rel);
                }
            }
        }
        if deltas {
            // Decide deltas on the relation-transformed values.
            let tr: Vec<Vec<u8>> = {
                let mut tmp = t.clone();
                tmp.delta = vec![false; nf];
                recs.iter().map(|r| tmp.forward(r)).collect()
            };
            for &k in &ints {
                let m = lay.mask(k);
                let v: Vec<i64> = tr.iter().map(|r| lay.value(r, k)).collect();
                let mut raw: Vec<u64> = v.iter().map(|&x| x as u64 & m).collect();
                let mut z: Vec<u64> = v
                    .windows(2)
                    .map(|w| zigzag(w[1].wrapping_sub(w[0]), m))
                    .collect();
                t.delta[k] = entropy(&mut z) + 0.05 < entropy(&mut raw);
            }
        }
        t
    }

    /// The learned relations.
    pub fn relations(&self) -> &[Relation] {
        &self.relations
    }

    /// Which fields carry a delta.
    pub fn deltas(&self) -> &[bool] {
        &self.delta
    }

    /// The layout.
    pub fn layout(&self) -> &Layout {
        &self.layout
    }

    /// Transform one record (sender side). Records must be fed in order.
    ///
    /// # Panics
    /// If `rec` is not one record long.
    pub fn forward(&mut self, rec: &[u8]) -> Vec<u8> {
        assert_eq!(rec.len(), self.layout.len, "record length");
        let lay = &self.layout;
        let mut out = rec.to_vec();
        for r in &self.relations {
            let pred = (r.a as i64)
                .wrapping_mul(lay.value(rec, r.i))
                .wrapping_add((r.b as i64).wrapping_mul(lay.value(rec, r.j)))
                >> 1;
            let v = lay.value(rec, r.target).wrapping_sub(pred) as u64 & lay.mask(r.target);
            lay.put(&mut out, r.target, v);
        }
        if self.delta.iter().any(|&d| d) {
            let cur = out.clone();
            if let Some(prev) = &self.prev_fwd {
                for k in (0..lay.fields.len()).filter(|&k| self.delta[k]) {
                    let m = lay.mask(k);
                    let d = signed_mod(lay.value(&cur, k).wrapping_sub(lay.value(prev, k)), m);
                    lay.put(&mut out, k, zigzag(d, m));
                }
            }
            self.prev_fwd = Some(cur);
        }
        out
    }

    /// Undo [`Self::forward`] (receiver side), records in the same order.
    ///
    /// # Panics
    /// If `rec` is not one record long.
    pub fn inverse(&mut self, rec: &[u8]) -> Vec<u8> {
        assert_eq!(rec.len(), self.layout.len, "record length");
        let lay = &self.layout;
        let mut out = rec.to_vec();
        if self.delta.iter().any(|&d| d) {
            if let Some(prev) = &self.prev_inv {
                for k in (0..lay.fields.len()).filter(|&k| self.delta[k]) {
                    let m = lay.mask(k);
                    let v = lay.value(prev, k).wrapping_add(unzigzag(lay.get(rec, k))) as u64 & m;
                    lay.put(&mut out, k, v);
                }
            }
            self.prev_inv = Some(out.clone());
        }
        for r in self.relations.iter().rev() {
            let pred = (r.a as i64)
                .wrapping_mul(lay.value(&out, r.i))
                .wrapping_add((r.b as i64).wrapping_mul(lay.value(&out, r.j)))
                >> 1;
            let v = lay.value(&out, r.target).wrapping_add(pred) as u64 & lay.mask(r.target);
            lay.put(&mut out, r.target, v);
        }
        out
    }

    /// Forget the previous record on both sides (e.g. at an epoch boundary).
    pub fn reset(&mut self) {
        self.prev_fwd = None;
        self.prev_inv = None;
    }

    /// Serialise for uplink.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut b = TRANSFORM_MAGIC.to_vec();
        b.extend_from_slice(&(self.layout.fields.len() as u16).to_le_bytes());
        for (k, f) in self.layout.fields.iter().enumerate() {
            b.push(f.width as u8);
            b.push(
                f.integer as u8
                    | (f.signed as u8) << 1
                    | (f.big_endian as u8) << 2
                    | (self.delta[k] as u8) << 3,
            );
        }
        b.extend_from_slice(&(self.relations.len() as u16).to_le_bytes());
        for r in &self.relations {
            b.extend_from_slice(&(r.target as u16).to_le_bytes());
            b.extend_from_slice(&(r.i as u16).to_le_bytes());
            b.extend_from_slice(&(r.j as u16).to_le_bytes());
            b.push(r.a as u8);
            b.push(r.b as u8);
        }
        b
    }

    /// Load a transform written by [`Self::to_bytes`], checking every index.
    pub fn from_bytes(b: &[u8]) -> Result<Self, Error> {
        let bad = Error::BadModel;
        if b.get(..8) != Some(&TRANSFORM_MAGIC[..]) {
            return Err(bad);
        }
        let u16_at = |at: usize| {
            b.get(at..at + 2)
                .map(|s| u16::from_le_bytes([s[0], s[1]]) as usize)
        };
        let nf = u16_at(8).ok_or(Error::BadModel)?;
        let mut at = 10;
        let (mut fields, mut delta, mut off) = (Vec::new(), Vec::new(), 0);
        for _ in 0..nf {
            let (w, fl) = (
                *b.get(at).ok_or(Error::BadModel)? as usize,
                *b.get(at + 1).ok_or(Error::BadModel)?,
            );
            at += 2;
            let integer = fl & 1 != 0;
            if w == 0 || (integer && ![1, 2, 4, 8].contains(&w)) || fl >> 4 != 0 {
                return Err(Error::BadModel);
            }
            fields.push(Field {
                offset: off,
                width: w,
                integer,
                signed: fl & 2 != 0,
                big_endian: fl & 4 != 0,
            });
            delta.push(fl & 8 != 0 && integer);
            off += w;
        }
        if fields.is_empty() {
            return Err(Error::BadModel);
        }
        let nr = u16_at(at).ok_or(Error::BadModel)?;
        at += 2;
        let mut relations = Vec::new();
        let mut targets = vec![false; nf];
        for _ in 0..nr {
            let (t, i, j) = (
                u16_at(at).ok_or(Error::BadModel)?,
                u16_at(at + 2).ok_or(Error::BadModel)?,
                u16_at(at + 4).ok_or(Error::BadModel)?,
            );
            let (a, bb) = (
                *b.get(at + 6).ok_or(Error::BadModel)? as i8,
                *b.get(at + 7).ok_or(Error::BadModel)? as i8,
            );
            at += 8;
            let ok = |k: usize| k < nf && fields[k].integer;
            if !ok(t) || !ok(i) || !ok(j) || t == i || t == j || targets[t] {
                return Err(Error::BadModel);
            }
            targets[t] = true;
            relations.push(Relation {
                target: t,
                i,
                j,
                a,
                b: bb,
            });
        }
        // Predictors must not be targets, so the inverse never reads a field it has not restored.
        if relations.iter().any(|r| targets[r.i] || targets[r.j]) || at != b.len() {
            return Err(Error::BadModel);
        }
        Ok(Self {
            layout: Layout { fields, len: off },
            relations,
            delta,
            prev_fwd: None,
            prev_inv: None,
        })
    }
}
