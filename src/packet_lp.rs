//! Numeric prediction for packet profile v2 (opt-in, [`crate::packet::PacketSession::v2_lp`]).
//!
//! Per column, a few integer predictors over the column's past values
//! (2W−WW, 3W−3WW+WWW, a fixed-point least-squares fit over recent deltas,
//! 16-bit extrapolations over the column and its left neighbour, ...).
//! Each one keeps residual histograms ("actual − predicted", mod 256)
//! selected by a bucket of its recent absolute error, in the manner of
//! paq8px's `LinearPredictionModel` + `ResidualMap`. While a changed byte
//! is coded bit by bit, each histogram gives P(next bit = 1) from the counts
//! of the residuals still compatible with the bits already coded (and with
//! "the byte changed"); those probabilities are mixed, per column and bit
//! depth, with the transition model's inputs.
//!
//! Everything is integer arithmetic with defined rounding, so both ends
//! agree bit for bit on any platform.

use crate::math::stretch;

/// Number of predictor ids.
pub(crate) const NPMAX: usize = 14;
const HIST: usize = 256;
const MAXORD: usize = 8;

/// Configuration of the numeric-prediction model. Both ends must use the
/// same one. Measurement knobs; [`LpConfig::default`] is the recommended set.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LpConfig {
    /// Bit mask of predictors over the column's values W (above), WW, ...:
    /// 0 W, 1 2W−WW, 2 3W−3WW+WWW, 3 W + OLS fit over the last deltas,
    /// 4 W + mean delta, 5 WW, 6 2WW−W4, 7 W + second OLS fit,
    /// 8 W + median of the last 3 deltas, 9 4W−6WW+4WWW−W4;
    /// over the 16-bit value formed with the left neighbour (already
    /// coded): 10 little-endian high byte from 2V−VV, 11 big-endian low
    /// byte from 2V−VV, 12 little-endian high byte from V, 13 big-endian
    /// low byte from V.
    pub preds: u32,
    /// Error buckets per predictor (1..=16).
    pub buckets: u32,
    /// Residual histograms per column (true) or shared by all columns.
    pub per_column: bool,
    /// If nonzero: a pool of 2^pool_bits histograms shared by hashing
    /// (column, predictor, bucket), instead of `per_column`'s layout.
    pub pool_bits: u32,
    /// Histogram total at which all counts are halved (adaptation speed).
    pub limit: u16,
    /// OLS order (number of past deltas, 1..=8) and forgetting shift (<= 8).
    pub ols_order: usize,
    pub ols_shift: u32,
    /// Second OLS: order and forgetting shift.
    pub ols2_order: usize,
    pub ols2_shift: u32,
    /// Ridge term added to the OLS diagonal (in units of one observation).
    pub ols_ridge: i64,
    /// Re-solve the OLS fits every this many updates.
    pub solve_every: u32,
    /// Skip OLS updates whose target and features are all zero (a constant
    /// column): faster, and the fit then describes the moving periods.
    pub skip_zero: bool,
    /// Add a numeric-prediction context to the "same as above" decision.
    pub flag: bool,
    /// Mixer weights per column and bit depth (true) or bit depth only.
    pub col_mixer: bool,
    /// SSE stage keyed by whether the bits so far agree with the most
    /// accurate predictor (and its error bucket).
    pub sse: bool,
    /// A second mixer, shared by all columns, selected by bit depth and
    /// the most accurate predictor's error bucket; averaged with the first.
    pub mix2: bool,
    /// Remove the "equal to the byte above" residual (already excluded by
    /// the flag) from the histogram counts.
    pub exclude_above: bool,
}

impl Default for LpConfig {
    fn default() -> Self {
        Self {
            // 2W−WW, 3W−3WW+WWW, OLS(4), WW, median slope, BE low, LE high.
            preds: 0b1_1001_0010_1110,
            buckets: 12,
            per_column: true,
            pool_bits: 11,
            limit: 4095,
            ols_order: 4,
            ols_shift: 7,
            ols2_order: 2,
            ols2_shift: 4,
            ols_ridge: 4,
            solve_every: 8,
            skip_zero: true,
            flag: false,
            col_mixer: true,
            exclude_above: true,
            sse: false,
            mix2: true,
        }
    }
}

impl LpConfig {
    /// Parse `key=value,key=value` over the defaults (measurement helper).
    pub fn parse(s: &str) -> Self {
        let mut c = Self::default();
        for kv in s.split(',').filter(|t| !t.is_empty() && *t != "1") {
            let (k, v) = kv.split_once('=').expect("key=value");
            let num = || -> i64 {
                if let Some(b) = v.strip_prefix("0b") {
                    i64::from_str_radix(b, 2).unwrap()
                } else {
                    v.parse().unwrap()
                }
            };
            match k {
                "preds" => c.preds = num() as u32,
                "buckets" => c.buckets = num() as u32,
                "percol" => c.per_column = num() != 0,
                "pool" => c.pool_bits = num() as u32,
                "limit" => c.limit = num() as u16,
                "ord" => c.ols_order = num() as usize,
                "shift" => c.ols_shift = num() as u32,
                "ord2" => c.ols2_order = num() as usize,
                "shift2" => c.ols2_shift = num() as u32,
                "ridge" => c.ols_ridge = num(),
                "every" => c.solve_every = num() as u32,
                "skip" => c.skip_zero = num() != 0,
                "flag" => c.flag = num() != 0,
                "colmix" => c.col_mixer = num() != 0,
                "excl" => c.exclude_above = num() != 0,
                "sse" => c.sse = num() != 0,
                "mix2" => c.mix2 = num() != 0,
                _ => panic!("unknown LP key {k}"),
            }
        }
        c
    }
}

/// Fixed-point recursive least squares on deltas: y = a · (d1..dn, 16).
#[derive(Clone)]
struct Ols {
    m: usize,
    shift: u32,
    ridge: i64,
    r: [[i64; MAXORD + 1]; MAXORD + 1],
    b: [i64; MAXORD + 1],
    /// Coefficients, Q16.
    a: [i64; MAXORD + 1],
    n: u32,
}

impl Ols {
    fn new(order: usize, shift: u32, ridge: i64) -> Self {
        assert!(
            shift <= 8,
            "OLS forgetting shift <= 8 keeps sums below 2^30"
        );
        let order = order.clamp(1, MAXORD);
        Self {
            m: order + 1,
            shift,
            ridge,
            r: [[0; MAXORD + 1]; MAXORD + 1],
            b: [0; MAXORD + 1],
            a: [0; MAXORD + 1],
            n: 0,
        }
    }

    fn update(&mut self, x: &[i32; MAXORD + 1], y: i32, every: u32) {
        let m = self.m;
        let sh = self.shift;
        for i in 0..m {
            let xi = x[i] as i64;
            self.b[i] += ((xi * y as i64) << 8) - (self.b[i] >> sh);
            let row = &mut self.r[i][i..m];
            for (rij, &xj) in row.iter_mut().zip(&x[i..m]) {
                *rij += ((xi * xj as i64) << 8) - (*rij >> sh);
            }
        }
        self.n += 1;
        if self.n % every == 0 {
            self.solve();
        }
    }

    /// Gaussian elimination in i64 (no pivoting: the matrix is symmetric
    /// positive definite thanks to the ridge, so the Schur complements stay
    /// bounded by the diagonal, below 2^30; products stay below 2^60).
    /// Truncating integer division: the same result on every platform.
    #[allow(clippy::needless_range_loop)] // symmetric fill of a small matrix by index
    fn solve(&mut self) {
        let m = self.m;
        let mut a = [[0i64; MAXORD + 2]; MAXORD + 1];
        for i in 0..m {
            for j in 0..m {
                a[i][j] = if i <= j { self.r[i][j] } else { self.r[j][i] };
            }
            a[i][i] += self.ridge << 8;
            a[i][m] = self.b[i];
        }
        for i in 0..m {
            let piv = a[i][i];
            if piv <= 0 {
                return; // numerically singular: keep the previous coefficients
            }
            let (top, rest) = a.split_at_mut(i + 1);
            let ri = &top[i];
            for rj in rest.iter_mut().take(m - i - 1) {
                let f = rj[i];
                if f == 0 {
                    continue;
                }
                for k in i..=m {
                    rj[k] -= ri[k] * f / piv;
                }
            }
        }
        const LIM: i64 = 8 << 16;
        let mut sol = [0i64; MAXORD + 1];
        for i in (0..m).rev() {
            let mut s = a[i][m] << 16;
            for k in i + 1..m {
                s -= a[i][k] * sol[k];
            }
            sol[i] = (s / a[i][i]).clamp(-LIM, LIM);
        }
        self.a[..m].copy_from_slice(&sol[..m]);
    }

    /// Predicted delta, Q16, from the packed recent deltas (newest in the
    /// low byte).
    fn predict(&self, ds: u64) -> i64 {
        let o = self.m - 1;
        let mut s = self.a[o] * 16;
        for i in 0..o {
            s += self.a[i] * (ds >> (8 * i)) as u8 as i8 as i64;
        }
        s
    }
}

/// Per-column predictor state.
#[derive(Clone)]
struct LpCol {
    /// Last 4 values, newest in the low byte.
    vals: u32,
    /// Last 8 deltas (as i8), newest in the low byte.
    ds: u64,
    /// Last two 16-bit values with the left neighbour: little-endian
    /// (this byte high) and big-endian (this byte low).
    le: [i32; 2],
    be: [i32; 2],
    ema: [u32; NPMAX],
    pred: [u8; NPMAX],
    bucket: [u8; NPMAX],
    /// Mean delta, Q8.
    md: i32,
    /// OLS predicted delta (Q16), for the flag context.
    pd: i64,
    ols: Ols,
    ols2: Ols,
}

impl LpCol {
    /// Prediction of predictor `id` for the next value, given the current
    /// packet's left neighbour (only the pair predictors use it).
    #[inline]
    fn predict(&self, id: usize, left: u8) -> u8 {
        let l = left as i32;
        match id {
            10 | 12 => {
                // Little endian: this byte is the high byte of (this, left).
                let p = if id == 10 {
                    2 * self.le[0] - self.le[1]
                } else {
                    self.le[0]
                };
                ((p - l + 128) >> 8) as u8
            }
            11 | 13 => {
                // Big endian: this byte is the low byte of (left, this).
                let p = if id == 11 {
                    2 * self.be[0] - self.be[1]
                } else {
                    self.be[0]
                };
                let q = (p - (l << 8)) as i16 as i32;
                q.clamp(0, 255) as u8
            }
            _ => self.pred[id],
        }
    }
}

/// One predictor's state while a byte is coded.
#[derive(Clone, Copy, Default)]
struct Slot {
    /// Histogram index and prediction.
    hist: u32,
    pred: u32,
    /// The bin of "equal to the byte above" and its count (excluded).
    excl_bin: u32,
    excl_cnt: u32,
    /// The residual window of the bits coded so far ([`Lp::inputs`]): first
    /// bin, prefix sum before it, count (less the excluded bin if inside),
    /// and the last split (lower half's count, prefix sum at its end).
    a: u32,
    lo: u32,
    tot: u32,
    n0: u32,
    pm: u32,
}

/// Numeric-prediction state of a session.
#[derive(Clone)]
pub(crate) struct Lp {
    pub(crate) cfg: LpConfig,
    /// Predictor slots per column: every active predictor, or with
    /// subsets ([`Lp::with_subsets`]) the longest subset.
    npc: usize,
    /// Per column: predictor ids by slot (`k * npc + j`), how many are used,
    /// and their bit mask (the only ones whose state is updated).
    col_ids: Vec<u8>,
    col_np: Vec<u8>,
    col_mask: Vec<u32>,
    /// Slots used by the byte being coded.
    np_cur: usize,
    cols: Vec<LpCol>,
    /// Residual histograms, as prefix sums of 256 bins.
    hist: Vec<[u16; HIST]>,
    /// Mixer weights.
    pub(crate) w: Vec<i32>,
    /// Inputs per weight set: 4 transition + bias + one per predictor.
    pub(crate) ni: usize,
    /// Per predictor slot of the byte being coded.
    slots: [Slot; NPMAX],
    /// Most accurate predictor for the byte being coded: prediction, bucket.
    pub(crate) best_pred: u8,
    pub(crate) best_bucket: u8,
    /// Second mixer's weights (`mix2`).
    pub(crate) w2: Vec<i32>,
}

fn bucket(e: u32, n: u32) -> u8 {
    // e ~ 16 x mean absolute error; m ~ 2 x mean error, log-spaced.
    let m = e >> 3;
    let b = if m < 4 {
        m
    } else {
        let l = 31 - m.leading_zeros();
        2 * l + ((m >> (l - 1)) & 1)
    };
    b.min(n - 1) as u8
}

impl Lp {
    /// Every column uses every predictor of `cfg.preds`.
    pub(crate) fn new(cfg: LpConfig, len: usize) -> Self {
        assert!(cfg.preds < 1 << NPMAX, "unknown predictor");
        let ids: Vec<u8> = (0..NPMAX as u8)
            .filter(|&i| cfg.preds >> i & 1 != 0)
            .collect();
        Self::build(cfg, len, &vec![ids; len])
    }

    /// Column `k` uses only the predictors `subsets[k]` (ids, in slot
    /// order; `cfg.preds` is ignored). The others cost nothing: no
    /// histograms, no mixer inputs, no state updates.
    pub(crate) fn with_subsets(cfg: LpConfig, subsets: &[Vec<u8>]) -> Self {
        Self::build(cfg, subsets.len(), subsets)
    }

    fn build(cfg: LpConfig, len: usize, subsets: &[Vec<u8>]) -> Self {
        assert!((1..=16).contains(&cfg.buckets), "buckets in 1..=16");
        assert_eq!(subsets.len(), len, "one predictor subset per column");
        let npc = subsets.iter().map(Vec::len).max().unwrap_or(0);
        let mut col_ids = vec![0u8; len * npc];
        let mut col_mask = vec![0u32; len];
        for (k, sub) in subsets.iter().enumerate() {
            for (j, &id) in sub.iter().enumerate() {
                assert!((id as usize) < NPMAX, "unknown predictor");
                assert!(col_mask[k] >> id & 1 == 0, "predictor listed twice");
                col_mask[k] |= 1 << id;
                col_ids[k * npc + j] = id;
            }
        }
        let col_np = subsets.iter().map(|s| s.len() as u8).collect();
        let np = npc.max(1);
        let groups = if cfg.per_column { len } else { 1 };
        let ni = 5 + npc;
        let wsets = (if cfg.col_mixer { len * 8 } else { 8 }).max(8 * 16);
        let mut w = vec![0i32; wsets * ni];
        for set in w.chunks_mut(ni) {
            for (i, wi) in set.iter_mut().enumerate() {
                *wi = if i < 5 { 16_000 } else { 65536 / np as i32 / 2 };
            }
        }
        let col = LpCol {
            vals: 0,
            ds: 0,
            le: [0; 2],
            be: [0; 2],
            ema: [0; NPMAX],
            pred: [0; NPMAX],
            bucket: [0; NPMAX],
            md: 0,
            pd: 0,
            ols: Ols::new(cfg.ols_order, cfg.ols_shift, cfg.ols_ridge),
            ols2: Ols::new(cfg.ols2_order, cfg.ols2_shift, cfg.ols_ridge),
        };
        Self {
            w: w.clone(),
            hist: vec![
                [0; HIST];
                if cfg.pool_bits > 0 {
                    1 << cfg.pool_bits
                } else {
                    groups * npc * cfg.buckets as usize
                }
            ],
            cols: vec![col; len],
            npc,
            col_ids,
            col_np,
            col_mask,
            np_cur: 0,
            ni,
            slots: [Slot::default(); NPMAX],
            best_pred: 0,
            best_bucket: 0,
            w2: if cfg.mix2 {
                w[..8 * 16 * ni].to_vec()
            } else {
                Vec::new()
            },
            cfg,
        }
    }

    pub(crate) fn memory_bytes(&self) -> usize {
        self.hist.len() * HIST * 2
            + self.w.len() * 4
            + self.cols.len() * std::mem::size_of::<LpCol>()
    }

    /// Weight set offset for column `k` at bit depth `d`.
    #[inline]
    pub(crate) fn wset(&self, k: usize, d: usize) -> usize {
        (if self.cfg.col_mixer { k * 8 + d } else { d }) * self.ni
    }

    /// Mixer inputs used by the byte being coded (the others are zero).
    #[inline]
    pub(crate) fn ni_cur(&self) -> usize {
        5 + self.np_cur
    }

    /// Select column `k`'s histograms before coding its (changed) byte.
    pub(crate) fn begin(&mut self, k: usize, above: u8, left: u8) {
        let c = &self.cols[k];
        let g = if self.cfg.per_column { k } else { 0 };
        let nb = self.cfg.buckets as usize;
        let npc = self.npc;
        let np = self.col_np[k] as usize;
        self.np_cur = np;
        if np == 0 {
            self.best_pred = 0;
            self.best_bucket = 0;
        }
        let mut best = u32::MAX;
        for j in 0..np {
            let id = self.col_ids[k * npc + j] as usize;
            let base = if self.cfg.pool_bits > 0 {
                let h = crate::flight::h2(
                    crate::flight::h2(k as u64 + 1, id as u64 + 1),
                    c.bucket[id] as u64 + 1,
                );
                (h >> (64 - self.cfg.pool_bits)) as usize
            } else {
                (g * npc + j) * nb + c.bucket[id] as usize
            };
            let pred = c.predict(id, left);
            if c.ema[id] < best {
                best = c.ema[id];
                self.best_pred = pred;
                self.best_bucket = c.bucket[id];
            }
            let ba = (192 + above as usize + 256 - pred as usize) & 255;
            let excl_cnt = if self.cfg.exclude_above {
                let s = &self.hist[base];
                s[ba] as u32 - if ba == 0 { 0 } else { s[ba - 1] as u32 }
            } else {
                0
            };
            self.slots[j] = Slot {
                hist: base as u32,
                pred: pred as u32,
                excl_bin: ba as u32,
                excl_cnt,
                ..Slot::default()
            };
        }
    }

    /// Mixer inputs for the next bit, given the partial byte `node`
    /// (leading 1, then the `depth` bits already coded). Called for depths
    /// 0, 1, ..., 7 in order: each bit's residual window is one half of the
    /// previous one, so one prefix sum per predictor gives both halves.
    /// `out` has one entry per slot of the byte being coded.
    #[inline(always)]
    pub(crate) fn inputs(&mut self, node: u32, depth: u32, out: &mut [i32]) {
        debug_assert_eq!(out.len(), self.np_cur);
        let r = 1u32 << (7 - depth);
        let up = node & 1 != 0;
        let n = out.len().min(NPMAX);
        for (sl, o) in self.slots[..n].iter_mut().zip(out.iter_mut()) {
            let s = &self.hist[sl.hist as usize];
            if depth == 0 {
                // The whole circle, starting at residual 0's bin offset.
                sl.a = (192 + 256 - sl.pred) & 255;
                sl.lo = if sl.a == 0 {
                    0
                } else {
                    s[(sl.a - 1) as usize & 255] as u32
                };
                sl.tot = s[HIST - 1] as u32 - sl.excl_cnt;
            } else if !up {
                sl.tot = sl.n0;
            } else {
                sl.tot -= sl.n0;
                sl.a = (sl.a + 2 * r) & 255;
                sl.lo = if sl.a == 0 { 0 } else { sl.pm };
            }
            // Lower half [a, a + r), mod 256.
            let pm = s[(sl.a + r - 1) as usize & 255] as u32;
            let mut n0 = if sl.a + r <= HIST as u32 {
                pm - sl.lo
            } else {
                s[HIST - 1] as u32 - sl.lo + pm
            };
            if (sl.excl_bin.wrapping_sub(sl.a) & 255) < r {
                n0 -= sl.excl_cnt;
            }
            sl.n0 = n0;
            sl.pm = pm;
            *o = stretch(ratio(n0, sl.tot - n0) as i32);
        }
    }

    /// Learn the coded byte `v` (after [`Lp::begin`]).
    pub(crate) fn learn_byte(&mut self, v: u8) {
        let limit = self.cfg.limit;
        let n = self.np_cur.min(NPMAX);
        for sl in &self.slots[..n] {
            let bin = (192 + v as usize + 256 - sl.pred as usize) & 255;
            let s = &mut self.hist[sl.hist as usize];
            for x in &mut s[bin..] {
                *x += 1;
            }
            if s[HIST - 1] >= limit {
                for x in s.iter_mut() {
                    *x >>= 1;
                }
            }
        }
    }

    /// Flag context for column `k`: OLS predicted delta and its error.
    pub(crate) fn flag_ctx(&self, k: usize) -> u64 {
        let c = &self.cols[k];
        let pd = c.pd.unsigned_abs() >> 12; // 1/16 units
        let q = if pd < 8 {
            pd
        } else {
            8 + (64 - pd.leading_zeros() as u64).min(7)
        };
        q * 2 * 16 + (c.pd < 0) as u64 * 16 + c.bucket[3].min(15) as u64
    }

    /// End of a key packet: column `k` took value `v`, its left neighbour
    /// in the packet `left`.
    pub(crate) fn end_column(&mut self, k: usize, v: u8, left: u8) {
        let preds = self.col_mask[k] | if self.cfg.flag { 1 << 3 } else { 0 };
        if preds == 0 {
            return; // no predictor reads this column's state
        }
        let every = self.cfg.solve_every.max(1);
        let nb = self.cfg.buckets;
        let c = &mut self.cols[k];
        // Errors of the predictions made for this packet.
        let mut bits = preds;
        while bits != 0 {
            let id = bits.trailing_zeros() as usize;
            bits &= bits - 1;
            let e = (v.wrapping_sub(c.predict(id, left)) as i8).unsigned_abs() as u32;
            c.ema[id] = c.ema[id] - (c.ema[id] >> 4) + e;
            c.bucket[id] = bucket(c.ema[id], nb);
        }
        let y = v.wrapping_sub(c.vals as u8) as i8 as i32;
        // OLS on deltas: target is the new delta, features the previous ones.
        if preds & (1 << 3 | 1 << 7) != 0 && !(self.cfg.skip_zero && y == 0 && c.ds == 0) {
            let mut x = [0i32; MAXORD + 1];
            for (i, xi) in x.iter_mut().enumerate().take(MAXORD) {
                *xi = (c.ds >> (8 * i)) as u8 as i8 as i32;
            }
            for (id, ols) in [(3, &mut c.ols), (7, &mut c.ols2)] {
                if preds >> id & 1 != 0 {
                    let mut xo = x;
                    xo[ols.m - 1] = 16;
                    ols.update(&xo, y, every);
                }
            }
        }
        if preds >> 4 & 1 != 0 {
            c.md += ((y << 8) - c.md) >> 5;
        }
        // Push v.
        c.vals = c.vals << 8 | v as u32;
        c.ds = c.ds << 8 | y as u8 as u64;
        let (l, vi) = (left as i32, v as i32);
        c.le = [vi << 8 | l, c.le[0]];
        c.be = [l << 8 | vi, c.be[0]];
        // Predictions for the next packet.
        let v1 = (c.vals & 255) as i32;
        let v2 = (c.vals >> 8 & 255) as i32;
        let v3 = (c.vals >> 16 & 255) as i32;
        let v4 = (c.vals >> 24) as i32;
        let d = |j: usize| (c.ds >> (8 * j)) as u8 as i8 as i32;
        let rnd = |q: i64| ((q + (1 << 15)) >> 16).clamp(-128, 127) as i32;
        let mut bits = preds & 0x3ff;
        while bits != 0 {
            let id = bits.trailing_zeros() as usize;
            bits &= bits - 1;
            let p = match id {
                0 => v1,
                1 => 2 * v1 - v2,
                2 => 3 * v1 - 3 * v2 + v3,
                3 => {
                    c.pd = c.ols.predict(c.ds);
                    v1 + rnd(c.pd)
                }
                4 => v1 + ((c.md + 128) >> 8),
                5 => v2,
                6 => 2 * v2 - v4,
                7 => v1 + rnd(c.ols2.predict(c.ds)),
                8 => {
                    let (a, b, cc) = (d(0), d(1), d(2));
                    v1 + a.max(b).min(a.min(b).max(cc))
                }
                _ => 4 * v1 - 6 * v2 + 4 * v3 - v4,
            };
            c.pred[id] = p as u8;
        }
    }
}

/// `RECIP[s]` = 2^28 / (s + 2).
static RECIP: [u32; 1 << 13] = {
    let mut t = [0u32; 1 << 13];
    let mut i = 0;
    while i < 1 << 13 {
        t[i] = ((1u64 << 28) / (i as u64 + 2)) as u32;
        i += 1;
    }
    t
};

/// 4096 (n1 + 1) / (n0 + n1 + 2) without a division, clamped to 1..=4095.
#[inline]
fn ratio(n0: u32, n1: u32) -> u32 {
    let sum = n0 + n1;
    if sum < 1 << 13 {
        // Always, unless `limit` > 8192: the general case with sh = 0.
        let p = ((n1 + 1) as u64 * RECIP[sum as usize] as u64) >> 16;
        return (p as u32).clamp(1, 4095);
    }
    let sh = (32 - sum.leading_zeros()).saturating_sub(13);
    let p = (((n1 >> sh) + 1) as u64 * RECIP[(sum >> sh) as usize & ((1 << 13) - 1)] as u64) >> 16;
    (p as u32).clamp(1, 4095)
}
