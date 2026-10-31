//! Integer-only logistic helpers.
//!
//! The encoder and decoder must make bit-identical predictions on every
//! platform, so nothing in the modelling path touches floating point.
//! Probabilities are 12-bit integers in `1..=4095` (P(bit = 1) * 4096) and the
//! "stretched" (logit) domain is `-2047..=2047`, i.e. ln(p / (1 - p)) * 256.

/// `4096 / (1 + exp(-x / 256))` sampled at x = -2048, -1920, ..., 2048.
const SQUASH_POINTS: [i32; 33] = [
    1, 2, 4, 6, 10, 17, 27, 45, 74, 120, 194, 311, 488, 747, 1102, 1546, 2048, 2550, 2994, 3349,
    3608, 3785, 3902, 3976, 4022, 4051, 4069, 4079, 4086, 4090, 4092, 4094, 4095,
];

/// Logistic function: stretched domain -> 12-bit probability.
#[inline]
pub fn squash(x: i32) -> i32 {
    if x >= 2047 {
        return 4095;
    }
    if x <= -2047 {
        return 1;
    }
    let w = x & 127;
    let i = ((x >> 7) + 16) as usize;
    (SQUASH_POINTS[i] * (128 - w) + SQUASH_POINTS[i + 1] * w + 64) >> 7
}

/// Inverse of [`squash`], tabulated once at compile time.
static STRETCH: [i16; 4096] = build_stretch();

const fn squash_const(x: i32) -> i32 {
    if x >= 2047 {
        return 4095;
    }
    if x <= -2047 {
        return 1;
    }
    let w = x & 127;
    let i = ((x >> 7) + 16) as usize;
    (SQUASH_POINTS[i] * (128 - w) + SQUASH_POINTS[i + 1] * w + 64) >> 7
}

const fn build_stretch() -> [i16; 4096] {
    let mut t = [0i16; 4096];
    let mut pi: i32 = 0;
    let mut x: i32 = -2047;
    while x <= 2047 {
        let v = squash_const(x);
        let mut j = pi;
        while j <= v {
            t[j as usize] = x as i16;
            j += 1;
        }
        pi = v + 1;
        x += 1;
    }
    let mut j = pi;
    while j < 4096 {
        t[j as usize] = 2047;
        j += 1;
    }
    t
}

/// Logit: 12-bit probability -> stretched domain.
#[inline]
pub fn stretch(p: i32) -> i32 {
    STRETCH[p as usize] as i32
}

/// Fast, well-mixed 32-bit hash finaliser (lowbias32).
#[inline]
pub fn mix32(mut x: u32) -> u32 {
    x ^= x >> 16;
    x = x.wrapping_mul(0x7feb_352d);
    x ^= x >> 15;
    x = x.wrapping_mul(0x846c_a68b);
    x ^= x >> 16;
    x
}

/// Combine two words into a hash.
#[inline]
pub fn hash2(a: u32, b: u32) -> u32 {
    mix32(a.wrapping_mul(0x9e37_79b1) ^ mix32(b.wrapping_add(0x632b_e5ab)))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn squash_is_monotone_and_bounded() {
        let mut prev = 0;
        for x in -2047..=2047 {
            let p = squash(x);
            assert!((1..=4095).contains(&p));
            assert!(p >= prev);
            prev = p;
        }
        assert_eq!(squash(0), 2048);
    }

    #[test]
    fn stretch_inverts_squash() {
        // Where squash is not saturated, stretch recovers x closely.
        for x in (-1500..=1500).step_by(7) {
            let back = stretch(squash(x));
            assert!((back - x).abs() <= 48, "x={x} back={back}");
        }
        // Everywhere, squash(stretch(p)) lands back on (or right next to) p.
        for p in 1..4096 {
            let q = squash(stretch(p));
            assert!((q - p).abs() <= 1 + p.min(4096 - p) / 32, "p={p} q={q}");
        }
    }
}
