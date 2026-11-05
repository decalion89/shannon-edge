//! Packet-level erasure coding: a systematic Reed–Solomon code over GF(2^8)
//! with a Cauchy generator matrix.
//!
//! A group of `G` variable-length payloads (e.g. compressed packets) gets
//! `m` parity packets; the receiver recovers **any** `m` lost packets of
//! the group (data or parity) from the rest. The payloads themselves are
//! sent unchanged, so with no loss nothing waits for the parity.
//!
//! This is the channel-coding half of Shannon's separation principle: let
//! the compressor remove all redundancy and add back exactly the redundancy
//! the link needs, in one place, instead of making the source code weaker
//! (shorter context, frozen models) to tolerate loss.
//!
//! Each payload is treated as a symbol of `2 + max_len` bytes (a 16-bit
//! length, the payload, zero padding), so every parity packet is
//! `2 + max_len` bytes, where `max_len` is the longest payload of the group.

const POLY: u16 = 0x11d;

struct Gf {
    exp: [u8; 512],
    log: [u8; 256],
}

const GF: Gf = {
    let mut exp = [0u8; 512];
    let mut log = [0u8; 256];
    let mut x: u16 = 1;
    let mut i = 0;
    while i < 255 {
        exp[i] = x as u8;
        exp[i + 255] = x as u8;
        log[x as usize] = i as u8;
        x <<= 1;
        if x & 0x100 != 0 {
            x ^= POLY;
        }
        i += 1;
    }
    Gf { exp, log }
};

fn mul(a: u8, b: u8) -> u8 {
    if a == 0 || b == 0 {
        0
    } else {
        GF.exp[GF.log[a as usize] as usize + GF.log[b as usize] as usize]
    }
}

fn inv(a: u8) -> u8 {
    debug_assert!(a != 0);
    GF.exp[255 - GF.log[a as usize] as usize]
}

/// `dst ^= c * src`
fn mul_add(dst: &mut [u8], c: u8, src: &[u8]) {
    if c == 0 {
        return;
    }
    let lc = GF.log[c as usize] as usize;
    for (d, &s) in dst.iter_mut().zip(src) {
        if s != 0 {
            *d ^= GF.exp[lc + GF.log[s as usize] as usize];
        }
    }
}

/// Cauchy matrix entry for parity row `j` and data column `i`.
fn coef(j: usize, i: usize, parity: usize) -> u8 {
    inv((j as u8) ^ ((parity + i) as u8))
}

fn symbol(payload: &[u8], len: usize) -> Vec<u8> {
    let mut s = Vec::with_capacity(len);
    s.extend_from_slice(&(payload.len() as u16).to_le_bytes());
    s.extend_from_slice(payload);
    s.resize(len, 0);
    s
}

/// The `parity` parity packets for a group of payloads.
///
/// # Panics
/// If `group.len() + parity > 256`, or a payload is longer than 65,535 bytes.
pub fn encode(group: &[&[u8]], parity: usize) -> Vec<Vec<u8>> {
    assert!(group.len() + parity <= 256, "group too large");
    let max = group.iter().map(|p| p.len()).max().unwrap_or(0);
    assert!(max <= u16::MAX as usize, "payload too long");
    let len = 2 + max;
    let mut out = vec![vec![0u8; len]; parity];
    for (i, p) in group.iter().enumerate() {
        let s = symbol(p, len);
        for (j, o) in out.iter_mut().enumerate() {
            mul_add(o, coef(j, i, parity), &s);
        }
    }
    out
}

/// Fill in the lost payloads of a group (`None` entries) from the received
/// payloads and parity packets (`None` = lost). Returns `false`, leaving
/// `group` unchanged, if too many packets of the group were lost or the
/// parity is inconsistent.
pub fn recover(group: &mut [Option<Vec<u8>>], parity: &[Option<Vec<u8>>]) -> bool {
    let m = parity.len();
    let lost: Vec<usize> = (0..group.len()).filter(|&i| group[i].is_none()).collect();
    if lost.is_empty() {
        return true;
    }
    let rows: Vec<usize> = (0..m)
        .filter(|&j| parity[j].is_some())
        .take(lost.len())
        .collect();
    if rows.len() < lost.len() || group.len() + m > 256 {
        return false;
    }
    let len = parity[rows[0]].as_ref().map_or(0, Vec::len);
    if len < 2
        || rows
            .iter()
            .any(|&j| parity[j].as_ref().map_or(0, Vec::len) != len)
    {
        return false;
    }
    // Syndromes: each parity minus the contribution of the received data.
    let mut rhs: Vec<Vec<u8>> = rows.iter().map(|&j| parity[j].clone().unwrap()).collect();
    for (i, d) in group.iter().enumerate() {
        if let Some(d) = d {
            if d.len() > len - 2 {
                return false;
            }
            let s = symbol(d, len);
            for (r, &j) in rows.iter().enumerate() {
                mul_add(&mut rhs[r], coef(j, i, m), &s);
            }
        }
    }
    // Solve A x = rhs, A[r][c] = coef(rows[r], lost[c]) (Cauchy: invertible).
    let k = lost.len();
    let mut a: Vec<Vec<u8>> = rows
        .iter()
        .map(|&j| lost.iter().map(|&i| coef(j, i, m)).collect())
        .collect();
    for c in 0..k {
        let p = (c..k)
            .find(|&r| a[r][c] != 0)
            .expect("Cauchy submatrix is invertible");
        a.swap(c, p);
        rhs.swap(c, p);
        let f = inv(a[c][c]);
        for x in a[c].iter_mut() {
            *x = mul(*x, f);
        }
        let pivot = std::mem::take(&mut rhs[c]);
        let mut pivot_scaled = vec![0u8; len];
        mul_add(&mut pivot_scaled, f, &pivot);
        for r in 0..k {
            if r != c && a[r][c] != 0 {
                let g = a[r][c];
                let row = a[c].clone();
                for (x, y) in a[r].iter_mut().zip(&row) {
                    *x ^= mul(g, *y);
                }
                mul_add(&mut rhs[r], g, &pivot_scaled);
            }
        }
        rhs[c] = pivot_scaled;
    }
    let mut out = Vec::with_capacity(k);
    for s in &rhs {
        let n = u16::from_le_bytes([s[0], s[1]]) as usize;
        if n > len - 2 || s[2 + n..].iter().any(|&b| b != 0) {
            return false;
        }
        out.push(s[2..2 + n].to_vec());
    }
    for (&i, p) in lost.iter().zip(out) {
        group[i] = Some(p);
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn field_inverse() {
        for a in 1..=255u8 {
            assert_eq!(mul(a, inv(a)), 1);
        }
    }
}
