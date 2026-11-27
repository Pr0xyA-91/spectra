//! Minimal zero-dependency PNG-in-ICO decoder (8-bit RGBA, RGB, and PLTE+tRNS)
//! for `spectra-shell` window/taskbar icon extraction across Linux, Windows, and macOS.

const PNG_SIG: [u8; 8] = [137, 80, 78, 71, 13, 10, 26, 10];
const MAX_DIMENSION: u32 = 4096;
const MAX_INFLATED_BYTES: usize = 16 * 1024 * 1024;

struct BitReader<'a> {
    data: &'a [u8],
    byte_pos: usize,
    bit_buf: u32,
    bit_count: u8,
}

impl<'a> BitReader<'a> {
    fn new(data: &'a [u8]) -> Self {
        Self {
            data,
            byte_pos: 0,
            bit_buf: 0,
            bit_count: 0,
        }
    }

    fn read_bits(&mut self, n: u8) -> Option<u32> {
        while self.bit_count < n {
            let b = *self.data.get(self.byte_pos)? as u32;
            self.byte_pos += 1;
            self.bit_buf |= b << self.bit_count;
            self.bit_count += 8;
        }
        let mask = if n == 32 { u32::MAX } else { (1u32 << n) - 1 };
        let val = self.bit_buf & mask;
        self.bit_buf >>= n;
        self.bit_count -= n;
        Some(val)
    }

    fn align_to_byte(&mut self) {
        let discard = self.bit_count % 8;
        self.bit_buf >>= discard;
        self.bit_count -= discard;
    }

    fn read_u16_le(&mut self) -> Option<u16> {
        let lo = self.read_bits(8)? as u16;
        let hi = self.read_bits(8)? as u16;
        Some(lo | (hi << 8))
    }

    fn copy_aligned_bytes(&mut self, mut len: usize, out: &mut Vec<u8>) -> Option<()> {
        while self.bit_count >= 8 && len > 0 {
            // Drain any buffered whole bytes first
            out.push((self.bit_buf & 0xFF) as u8);
            self.bit_buf >>= 8;
            self.bit_count -= 8;
            len -= 1;
        }
        if self.bit_count != 0 {
            return None;
        }
        let end = self.byte_pos.checked_add(len)?;
        let slice = self.data.get(self.byte_pos..end)?;
        out.extend_from_slice(slice);
        self.byte_pos = end;
        Some(())
    }
}

struct HuffTree {
    counts: [u16; 16],
    symbols: Vec<u16>,
}

impl HuffTree {
    fn from_lengths(lengths: &[u8]) -> Option<Self> {
        let mut counts = [0u16; 16];
        let mut total = 0usize;
        for &len in lengths {
            if len > 15 {
                return None;
            }
            if len > 0 {
                counts[len as usize] += 1;
                total += 1;
            }
        }
        let mut offsets = [0usize; 16];
        let mut sum = 0usize;
        for bits in 1..=15 {
            offsets[bits] = sum;
            sum += counts[bits] as usize;
        }
        let mut symbols = vec![0u16; total];
        for (sym, &len) in lengths.iter().enumerate() {
            if len > 0 {
                let idx = offsets[len as usize];
                symbols[idx] = sym as u16;
                offsets[len as usize] += 1;
            }
        }
        Some(Self { counts, symbols })
    }

    fn fixed_lit_len() -> Option<Self> {
        let mut lengths = [0u8; 288];
        lengths[..144].fill(8);
        lengths[144..256].fill(9);
        lengths[256..280].fill(7);
        lengths[280..288].fill(8);
        Self::from_lengths(&lengths)
    }

    fn fixed_dist() -> Option<Self> {
        let lengths = [5u8; 32];
        Self::from_lengths(&lengths)
    }

    fn decode(&self, br: &mut BitReader<'_>) -> Option<u16> {
        let mut code = 0i32;
        let mut first = 0i32;
        let mut index = 0usize;
        for bits in 1..=15 {
            let bit = br.read_bits(1)? as i32;
            code |= bit;
            let count = self.counts[bits] as i32;
            if code - count < first {
                let sym_idx = index + (code - first) as usize;
                return self.symbols.get(sym_idx).copied();
            }
            index += count as usize;
            first = (first + count) << 1;
            code <<= 1;
        }
        None
    }
}

fn read_dynamic_trees(br: &mut BitReader<'_>) -> Option<(HuffTree, HuffTree)> {
    let hlit = br.read_bits(5)? as usize + 257;
    let hdist = br.read_bits(5)? as usize + 1;
    let hclen = br.read_bits(4)? as usize + 4;
    if hlit > 286 || hdist > 32 {
        return None;
    }

    const CL_ORDER: [usize; 19] = [
        16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15,
    ];
    let mut cl_lengths = [0u8; 19];
    for &slot in CL_ORDER.iter().take(hclen) {
        cl_lengths[slot] = br.read_bits(3)? as u8;
    }
    let cl_tree = HuffTree::from_lengths(&cl_lengths)?;

    let total_codes = hlit + hdist;
    let mut unpacked = Vec::with_capacity(total_codes);
    while unpacked.len() < total_codes {
        let sym = cl_tree.decode(br)?;
        match sym {
            0..=15 => unpacked.push(sym as u8),
            16 => {
                let prev = *unpacked.last()?;
                let repeat = br.read_bits(2)? as usize + 3;
                if unpacked.len() + repeat > total_codes {
                    return None;
                }
                unpacked.resize(unpacked.len() + repeat, prev);
            }
            17 => {
                let repeat = br.read_bits(3)? as usize + 3;
                if unpacked.len() + repeat > total_codes {
                    return None;
                }
                unpacked.resize(unpacked.len() + repeat, 0);
            }
            18 => {
                let repeat = br.read_bits(7)? as usize + 11;
                if unpacked.len() + repeat > total_codes {
                    return None;
                }
                unpacked.resize(unpacked.len() + repeat, 0);
            }
            _ => return None,
        }
    }

    let lit_tree = HuffTree::from_lengths(&unpacked[..hlit])?;
    let dist_tree = HuffTree::from_lengths(&unpacked[hlit..])?;
    Some((lit_tree, dist_tree))
}

fn inflate_zlib(zlib: &[u8], expected_len: usize) -> Option<Vec<u8>> {
    if zlib.len() < 6 || expected_len > MAX_INFLATED_BYTES {
        return None;
    }
    let cmf = zlib[0];
    let flg = zlib[1];
    if (cmf & 0x0F) != 8 || !((cmf as u16) << 8 | flg as u16).is_multiple_of(31) {
        return None;
    }
    let start = if (flg & 0x20) != 0 { 6 } else { 2 };
    if zlib.len() < start + 4 {
        return None;
    }
    let deflate = &zlib[start..zlib.len() - 4];

    const LEN_BASE: [u16; 29] = [
        3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115,
        131, 163, 195, 227, 258,
    ];
    const LEN_EXTRA: [u8; 29] = [
        0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0,
    ];
    const DIST_BASE: [u16; 30] = [
        1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537,
        2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
    ];
    const DIST_EXTRA: [u8; 30] = [
        0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12,
        13, 13,
    ];

    let mut br = BitReader::new(deflate);
    let mut out = Vec::with_capacity(expected_len);

    loop {
        let bfinal = br.read_bits(1)?;
        let btype = br.read_bits(2)?;
        match btype {
            0 => {
                br.align_to_byte();
                let len = br.read_u16_le()?;
                let nlen = br.read_u16_le()?;
                if len != !nlen {
                    return None;
                }
                if out.len().checked_add(len as usize)? > expected_len {
                    return None;
                }
                br.copy_aligned_bytes(len as usize, &mut out)?;
            }
            1 | 2 => {
                let (lit_tree, dist_tree) = if btype == 1 {
                    (HuffTree::fixed_lit_len()?, HuffTree::fixed_dist()?)
                } else {
                    read_dynamic_trees(&mut br)?
                };
                loop {
                    let sym = lit_tree.decode(&mut br)?;
                    if sym < 256 {
                        if out.len() >= expected_len {
                            return None;
                        }
                        out.push(sym as u8);
                    } else if sym == 256 {
                        break;
                    } else {
                        let l_idx = (sym as usize).checked_sub(257)?;
                        let base_len = *LEN_BASE.get(l_idx)? as usize;
                        let extra_len = br.read_bits(*LEN_EXTRA.get(l_idx)?)? as usize;
                        let copy_len = base_len + extra_len;

                        let d_sym = dist_tree.decode(&mut br)? as usize;
                        let base_dist = *DIST_BASE.get(d_sym)? as usize;
                        let extra_dist = br.read_bits(*DIST_EXTRA.get(d_sym)?)? as usize;
                        let dist = base_dist + extra_dist;

                        if dist == 0 || dist > out.len() || out.len() + copy_len > expected_len {
                            return None;
                        }
                        for _ in 0..copy_len {
                            let b = out[out.len() - dist];
                            out.push(b);
                        }
                    }
                }
            }
            _ => return None,
        }
        if bfinal == 1 {
            break;
        }
    }

    if out.len() != expected_len {
        return None;
    }
    Some(out)
}

fn paeth_predictor(a: u8, b: u8, c: u8) -> u8 {
    let p = a as i32 + b as i32 - c as i32;
    let pa = (p - a as i32).abs();
    let pb = (p - b as i32).abs();
    let pc = (p - c as i32).abs();
    if pa <= pb && pa <= pc {
        a
    } else if pb <= pc {
        b
    } else {
        c
    }
}

pub(crate) fn decode_png_to_rgba(png: &[u8]) -> Option<(Vec<u8>, u32, u32)> {
    if png.len() < 33 || png[..8] != PNG_SIG {
        return None;
    }

    let mut pos = 8usize;
    let mut width = 0u32;
    let mut height = 0u32;
    let mut color_type = 0u8;
    let mut saw_ihdr = false;
    let mut plte: Option<&[u8]> = None;
    let mut trns: Option<&[u8]> = None;
    let mut idat = Vec::new();

    while pos.checked_add(12)? <= png.len() {
        let len = u32::from_be_bytes([png[pos], png[pos + 1], png[pos + 2], png[pos + 3]]) as usize;
        let ctype = &png[pos + 4..pos + 8];
        let data_start = pos + 8;
        let data_end = data_start.checked_add(len)?;
        let chunk_end = data_end.checked_add(4)?;
        if chunk_end > png.len() {
            return None;
        }
        let chunk_data = &png[data_start..data_end];
        match ctype {
            b"IHDR" => {
                if len != 13 || saw_ihdr {
                    return None;
                }
                width = u32::from_be_bytes([
                    chunk_data[0],
                    chunk_data[1],
                    chunk_data[2],
                    chunk_data[3],
                ]);
                height = u32::from_be_bytes([
                    chunk_data[4],
                    chunk_data[5],
                    chunk_data[6],
                    chunk_data[7],
                ]);
                let bit_depth = chunk_data[8];
                color_type = chunk_data[9];
                let compression = chunk_data[10];
                let filter = chunk_data[11];
                let interlace = chunk_data[12];
                if width == 0
                    || height == 0
                    || width > MAX_DIMENSION
                    || height > MAX_DIMENSION
                    || bit_depth != 8
                    || !matches!(color_type, 2 | 3 | 6)
                    || compression != 0
                    || filter != 0
                    || interlace != 0
                {
                    return None;
                }
                saw_ihdr = true;
            }
            b"PLTE" => {
                if len == 0 || len > 768 || !len.is_multiple_of(3) {
                    return None;
                }
                plte = Some(chunk_data);
            }
            b"tRNS" => {
                trns = Some(chunk_data);
            }
            b"IDAT" => {
                if idat.len().checked_add(len)? > MAX_INFLATED_BYTES {
                    return None;
                }
                idat.extend_from_slice(chunk_data);
            }
            b"IEND" => break,
            _ => {}
        }
        pos = chunk_end;
    }

    if !saw_ihdr || idat.is_empty() {
        return None;
    }

    let bpp: usize = match color_type {
        6 => 4,
        2 => 3,
        3 => 1,
        _ => return None,
    };
    let stride = (width as usize).checked_mul(bpp)?;
    let scanline_len = stride.checked_add(1)?;
    let expected_raw = scanline_len.checked_mul(height as usize)?;
    let raw = inflate_zlib(&idat, expected_raw)?;

    let mut recon = vec![0u8; stride.checked_mul(height as usize)?];
    for y in 0..height as usize {
        let src_base = y * scanline_len;
        let filter_type = raw[src_base];
        let src_row = &raw[src_base + 1..src_base + 1 + stride];
        let (prev_rows, curr_and_rest) = recon.split_at_mut(y * stride);
        let curr_row = &mut curr_and_rest[..stride];
        let prev_row = if y > 0 {
            Some(&prev_rows[(y - 1) * stride..y * stride])
        } else {
            None
        };

        for i in 0..stride {
            let x = src_row[i];
            let a = if i >= bpp { curr_row[i - bpp] } else { 0 };
            let b = prev_row.map_or(0, |p| p[i]);
            let c = if i >= bpp {
                prev_row.map_or(0, |p| p[i - bpp])
            } else {
                0
            };
            curr_row[i] = match filter_type {
                0 => x,
                1 => x.wrapping_add(a),
                2 => x.wrapping_add(b),
                3 => x.wrapping_add(((a as u16 + b as u16) >> 1) as u8),
                4 => x.wrapping_add(paeth_predictor(a, b, c)),
                _ => return None,
            };
        }
    }

    let pixel_count = (width as usize).checked_mul(height as usize)?;
    let mut rgba = Vec::with_capacity(pixel_count.checked_mul(4)?);
    match color_type {
        6 => rgba.extend_from_slice(&recon),
        2 => {
            for rgb in recon.as_chunks::<3>().0 {
                rgba.push(rgb[0]);
                rgba.push(rgb[1]);
                rgba.push(rgb[2]);
                rgba.push(255);
            }
        }
        3 => {
            let palette = plte?;
            let alpha_table = trns.unwrap_or(&[]);
            for &idx in &recon {
                let base = (idx as usize).checked_mul(3)?;
                let rgb = palette.get(base..base + 3)?;
                let alpha = alpha_table.get(idx as usize).copied().unwrap_or(255);
                rgba.push(rgb[0]);
                rgba.push(rgb[1]);
                rgba.push(rgb[2]);
                rgba.push(alpha);
            }
        }
        _ => return None,
    }

    Some((rgba, width, height))
}
