//! Dictionary training: distil many samples into a small dictionary.
//!
//! A dictionary is only as good as what goes into it. Raw recent records
//! waste the budget on content that appears once; the useful part is what
//! recurs *across many samples* (field names, templates, common values).
//!
//! The method follows the idea of zstd's COVER trainer, implemented from
//! scratch:
//!
//! 1. Count, for every `d`-byte substring (d-mer), how many distinct samples
//!    contain it.
//! 2. Split the concatenated samples into `budget / k` epochs. In each epoch,
//!    pick the `k`-byte segment whose d-mers have the highest total sample
//!    frequency, then zero those d-mers so later picks favour new content.
//! 3. Concatenate the picked segments, **best last**: the context-mixing
//!    model weighs recent history most, so the most valuable knowledge goes
//!    where priming leaves it freshest.

use std::collections::HashMap;

/// Training parameters.
#[derive(Clone, Debug)]
pub struct TrainOptions {
    /// Dictionary size in bytes.
    pub budget: usize,
    /// Segment length: the unit of selection.
    pub segment: usize,
    /// Substring length used to measure what recurs across samples.
    pub dmer: usize,
}

impl Default for TrainOptions {
    fn default() -> Self {
        Self {
            budget: 112_640,
            segment: 1024,
            dmer: 8,
        }
    }
}

#[inline]
fn dmer_hash(w: &[u8]) -> u64 {
    // FNV-1a over the d-mer, then a final mix; collisions only blur scores.
    let mut h: u64 = 0xcbf2_9ce4_8422_2325;
    for &b in w {
        h = (h ^ b as u64).wrapping_mul(0x0000_0100_0000_01b3);
    }
    h ^ (h >> 29)
}

/// Build a dictionary of at most `opts.budget` bytes from `samples`.
/// Returns an empty vector if there is nothing to learn from.
pub fn train_dictionary(samples: &[&[u8]], opts: &TrainOptions) -> Vec<u8> {
    let d = opts.dmer.max(1);
    let k = opts.segment.max(d);
    let total: usize = samples.iter().map(|s| s.len()).sum();
    if total == 0 || opts.budget == 0 {
        return Vec::new();
    }
    if total <= opts.budget {
        // Everything fits: keep it all.
        return samples.concat();
    }

    // 1. Document frequency of every d-mer (counted once per sample).
    let mut freq: HashMap<u64, (u32, u32)> = HashMap::new(); // hash -> (count, last sample)
    for (si, s) in samples.iter().enumerate() {
        let tag = si as u32 + 1;
        for w in s.windows(d) {
            let e = freq.entry(dmer_hash(w)).or_insert((0, 0));
            if e.1 != tag {
                e.0 += 1;
                e.1 = tag;
            }
        }
    }
    let mut freq: HashMap<u64, u32> = freq
        .into_iter()
        .filter(|&(_, (c, _))| c > 1) // seen in one sample only: not knowledge
        .map(|(h, (c, _))| (h, c))
        .collect();

    // Concatenate samples; d-mers never span a sample boundary.
    let mut data = Vec::with_capacity(total);
    let mut starts = Vec::with_capacity(samples.len());
    for s in samples {
        starts.push(data.len());
        data.extend_from_slice(s);
    }
    let boundary_ok = {
        let mut ok = vec![true; data.len()];
        for (i, s) in samples.iter().enumerate() {
            let end = starts[i] + s.len();
            // A d-mer starting in the last d-1 bytes would cross into the next sample.
            for flag in &mut ok[end.saturating_sub(d - 1)..end] {
                *flag = false;
            }
        }
        ok
    };
    let hashes: Vec<u64> = (0..data.len())
        .map(|p| {
            if boundary_ok[p] && p + d <= data.len() {
                dmer_hash(&data[p..p + d])
            } else {
                0
            }
        })
        .collect();

    // 2. One segment per epoch.
    let epochs = (opts.budget / k).max(1);
    let epoch_len = (data.len() / epochs).max(k);
    let mut picks: Vec<(u64, usize)> = Vec::with_capacity(epochs); // (score, start)
    let score_at = |freq: &HashMap<u64, u32>, p: usize| -> u64 {
        if hashes[p] == 0 {
            0
        } else {
            *freq.get(&hashes[p]).unwrap_or(&0) as u64
        }
    };
    let mut e = 0;
    while e * epoch_len + k <= data.len() && picks.len() < epochs {
        let lo = e * epoch_len;
        let hi = ((e + 1) * epoch_len).min(data.len());
        // Sliding window over segment starts in [lo, hi - k].
        let last = hi.saturating_sub(k).max(lo);
        let mut sum: u64 = (lo..lo + k - d + 1).map(|p| score_at(&freq, p)).sum();
        let (mut best, mut best_at) = (sum, lo);
        for start in lo + 1..=last {
            sum -= score_at(&freq, start - 1);
            sum += score_at(&freq, start + k - d);
            if sum > best {
                best = sum;
                best_at = start;
            }
        }
        if best > 0 {
            picks.push((best, best_at));
            // Content now covered: stop rewarding it in later epochs.
            for &h in &hashes[best_at..best_at + k - d + 1] {
                if h != 0 {
                    freq.insert(h, 0);
                }
            }
        }
        e += 1;
    }

    // 3. Best last.
    picks.sort_by_key(|&(score, start)| (score, std::cmp::Reverse(start)));
    let mut dict = Vec::with_capacity(opts.budget);
    for &(_, start) in &picks {
        if dict.len() + k > opts.budget {
            break;
        }
        dict.extend_from_slice(&data[start..start + k]);
    }
    dict
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn respects_the_budget_and_prefers_shared_content() {
        // Every sample shares a template; each also has unique noise.
        let template = b"{\"type\":\"PushEvent\",\"repo\":{\"name\":\"";
        let mut owned = Vec::new();
        let mut x: u32 = 12345;
        for i in 0..400 {
            let mut s = template.to_vec();
            for _ in 0..200 {
                x ^= x << 13;
                x ^= x >> 17;
                x ^= x << 5;
                s.push(b'a' + (x % 26) as u8);
            }
            s.extend_from_slice(format!("\",\"id\":{i}}}").as_bytes());
            owned.push(s);
        }
        let samples: Vec<&[u8]> = owned.iter().map(|s| &s[..]).collect();
        let opts = TrainOptions {
            budget: 4096,
            segment: 256,
            dmer: 8,
        };
        let dict = train_dictionary(&samples, &opts);
        assert!(!dict.is_empty() && dict.len() <= 4096);
        let needle = &template[..20];
        assert!(
            dict.windows(needle.len()).any(|w| w == needle),
            "the shared template should be in the dictionary"
        );
    }

    #[test]
    fn small_inputs_are_kept_whole() {
        let a: &[u8] = b"hello";
        let b: &[u8] = b"world";
        assert_eq!(
            train_dictionary(&[a, b], &TrainOptions::default()),
            b"helloworld"
        );
        assert!(train_dictionary(&[], &TrainOptions::default()).is_empty());
    }
}
