//! CRC-32 (IEEE 802.3, reflected, polynomial 0xEDB88320) — the same checksum
//! used by gzip, zip and PNG.

static TABLE: [u32; 256] = {
    let mut t = [0u32; 256];
    let mut i = 0;
    while i < 256 {
        let mut c = i as u32;
        let mut k = 0;
        while k < 8 {
            c = if c & 1 != 0 {
                0xedb8_8320 ^ (c >> 1)
            } else {
                c >> 1
            };
            k += 1;
        }
        t[i] = c;
        i += 1;
    }
    t
};

pub fn crc32(data: &[u8]) -> u32 {
    let mut c = u32::MAX;
    for &b in data {
        c = TABLE[((c ^ b as u32) & 0xff) as usize] ^ (c >> 8);
    }
    !c
}

#[cfg(test)]
mod tests {
    #[test]
    fn known_vector() {
        assert_eq!(super::crc32(b"123456789"), 0xcbf4_3926);
        assert_eq!(super::crc32(b""), 0);
    }
}
