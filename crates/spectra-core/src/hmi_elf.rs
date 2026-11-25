//! High-speed zero-panic Rust acceleration primitives for Kalerm HMI ELF inspection and patching.

use std::collections::HashSet;

/// Dynamically encodes an ARMv7 8-byte little-endian movw + movt instruction pair
/// loading a 32-bit VMA into register `rd`.
#[inline]
pub fn encode_arm_movw_movt(rd: u8, vma: u32) -> [u8; 8] {
    let imm_low = (vma & 0xffff) as u16;
    let imm_high = ((vma >> 16) & 0xffff) as u16;
    let rd_nibble = (rd & 0x0f) << 4;
    [
        (imm_low & 0xff) as u8,
        rd_nibble | (((imm_low >> 8) & 0x0f) as u8),
        ((imm_low >> 12) & 0x0f) as u8,
        0xe3,
        (imm_high & 0xff) as u8,
        rd_nibble | (((imm_high >> 8) & 0x0f) as u8),
        0x40 | (((imm_high >> 12) & 0x0f) as u8),
        0xe3,
    ]
}

/// Checks whether `text_bytes` contains an 8-byte ARM movw+movt instruction pair
/// loading `target_vma` into ANY register (rd in 0..16).
/// Performs a single cache-friendly pass with zero heap allocations.
pub fn has_arm_movw_movt_any_reg(text_bytes: &[u8], target_vma: u32) -> bool {
    if text_bytes.len() < 8 {
        return false;
    }
    let imm_low = (target_vma & 0xffff) as u16;
    let imm_high = ((target_vma >> 16) & 0xffff) as u16;
    let b0 = (imm_low & 0xff) as u8;
    let b1_low = ((imm_low >> 8) & 0x0f) as u8;
    let b2 = ((imm_low >> 12) & 0x0f) as u8;
    let b4 = (imm_high & 0xff) as u8;
    let b5_low = ((imm_high >> 8) & 0x0f) as u8;
    let b6 = (0x40 | ((imm_high >> 12) & 0x0f)) as u8;

    let len = text_bytes.len() - 7;
    let mut i = 0;
    while i < len {
        if text_bytes[i + 3] == 0xe3
            && text_bytes[i + 7] == 0xe3
            && text_bytes[i] == b0
            && text_bytes[i + 4] == b4
            && text_bytes[i + 2] == b2
            && text_bytes[i + 6] == b6
            && (text_bytes[i + 1] & 0x0f) == b1_low
            && (text_bytes[i + 5] & 0x0f) == b5_low
        {
            let rd1 = (text_bytes[i + 1] >> 4) & 0x0f;
            let rd2 = (text_bytes[i + 5] >> 4) & 0x0f;
            if rd1 == rd2 {
                return true;
            }
        }
        i += 4;
    }
    false
}

/// Repoints all occurrences of ARM movw+movt pairs loading `orig_vma` to `new_vma`
/// for all registers (rd in 0..16) in a single pass over `text_bytes`.
/// Returns `(patched_bytes, total_repointed_count)`.
pub fn repoint_arm_movw_movt_all_regs(
    text_bytes: &[u8],
    orig_vma: u32,
    new_vma: u32,
) -> (Vec<u8>, usize) {
    let mut output = text_bytes.to_vec();
    if text_bytes.len() < 8 {
        return (output, 0);
    }
    let imm_low = (orig_vma & 0xffff) as u16;
    let imm_high = ((orig_vma >> 16) & 0xffff) as u16;
    let b0 = (imm_low & 0xff) as u8;
    let b1_low = ((imm_low >> 8) & 0x0f) as u8;
    let b2 = ((imm_low >> 12) & 0x0f) as u8;
    let b4 = (imm_high & 0xff) as u8;
    let b5_low = ((imm_high >> 8) & 0x0f) as u8;
    let b6 = (0x40 | ((imm_high >> 12) & 0x0f)) as u8;

    let mut repointed_count = 0;
    let len = output.len() - 7;
    let mut i = 0;
    while i < len {
        if output[i + 3] == 0xe3
            && output[i + 7] == 0xe3
            && output[i] == b0
            && output[i + 4] == b4
            && output[i + 2] == b2
            && output[i + 6] == b6
            && (output[i + 1] & 0x0f) == b1_low
            && (output[i + 5] & 0x0f) == b5_low
        {
            let rd1 = (output[i + 1] >> 4) & 0x0f;
            let rd2 = (output[i + 5] >> 4) & 0x0f;
            if rd1 == rd2 {
                let rep = encode_arm_movw_movt(rd1, new_vma);
                output[i..i + 8].copy_from_slice(&rep);
                repointed_count += 1;
                i += 8;
                continue;
            }
        }
        i += 4;
    }
    (output, repointed_count)
}

/// Scans `ro_bytes[start_rel_off..]` at `align`-byte boundaries for `min_size` consecutive `0x00` bytes.
/// Returns the absolute file offset `sh_offset + idx`.
pub fn find_free_zero_padding(
    ro_bytes: &[u8],
    sh_offset: usize,
    min_size: usize,
    align: usize,
    start_rel_off: usize,
) -> Option<usize> {
    if min_size == 0 || align == 0 || ro_bytes.is_empty() {
        return None;
    }
    let step = if align.is_power_of_two() { align } else { 1 };
    let initial_abs = sh_offset.checked_add(start_rel_off)?;
    let start_abs = if step > 1 {
        initial_abs.checked_add(step - 1)? & !(step - 1)
    } else {
        initial_abs
    };
    if start_abs < sh_offset {
        return None;
    }
    let mut off = start_abs - sh_offset;
    if off >= ro_bytes.len() || min_size > ro_bytes.len() - off {
        return None;
    }

    let end = ro_bytes.len() - min_size;
    while off <= end {
        let slice = &ro_bytes[off..off + min_size];
        if slice.iter().all(|&b| b == 0) {
            return sh_offset.checked_add(off);
        }
        off = off.checked_add(step)?;
    }
    None
}

/// Scans `ro_bytes` for orphaned, unreferenced null-terminated UTF-8 strings.
/// Computes `cur_vma = (search_start_off + chunk_offset) as u32 + vma_minus_off`.
/// Filters out referenced VMAs and checks for presence of common words and diacritics.
pub fn scan_rodata_orphaned_string(
    ro_bytes: &[u8],
    search_start_off: usize,
    vma_minus_off: u32,
    referenced_vmas: &[u32],
    common_words: &[String],
    target_diacritics: &str,
) -> Option<(u32, String)> {
    let referenced_set: HashSet<u32> = referenced_vmas.iter().copied().collect();
    let lower_common_words: Vec<String> = common_words.iter().map(|w| w.to_lowercase()).collect();

    let mut chunk_start = 0;
    while chunk_start < ro_bytes.len() {
        let chunk_end = match ro_bytes[chunk_start..].iter().position(|&b| b == 0) {
            Some(pos) => chunk_start + pos,
            None => ro_bytes.len(),
        };

        let chunk = &ro_bytes[chunk_start..chunk_end];
        if chunk.len() >= 4 {
            if let Ok(s_txt) = std::str::from_utf8(chunk) {
                if let Some(cur_off) = search_start_off.checked_add(chunk_start) {
                    if let Ok(cur_off_u32) = u32::try_from(cur_off) {
                        if let Some(cur_vma) = cur_off_u32.checked_add(vma_minus_off) {
                            if !referenced_set.contains(&cur_vma) {
                                let has_diacritics = target_diacritics.is_empty()
                                    || s_txt.chars().any(|c| target_diacritics.contains(c));
                                if has_diacritics {
                                    let matches_siblings = if lower_common_words.is_empty() {
                                        true
                                    } else {
                                        let s_lower = s_txt.to_lowercase();
                                        let words: Vec<&str> = s_lower.split_whitespace().collect();
                                        lower_common_words.iter().any(|cw| words.contains(&cw.as_str()))
                                    };
                                    if matches_siblings {
                                        return Some((cur_vma, s_txt.to_string()));
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }

        chunk_start = chunk_end + 1;
    }

    None
}

/// Runs the bipartite cross-key token swap detection algorithm in compiled Rust.
/// Returns a list of `(i, j)` index pairs of detected token swaps.
pub fn detect_bipartite_token_swaps(
    keys: Vec<String>,
    key_tokens: Vec<Vec<String>>,
    val_tokens: Vec<Vec<String>>,
) -> Vec<(usize, usize)> {
    let n = keys.len();
    if n == 0 || key_tokens.len() != n || val_tokens.len() != n {
        return Vec::new();
    }

    let key_sets: Vec<HashSet<&str>> = key_tokens
        .iter()
        .map(|tokens| tokens.iter().map(|s| s.as_str()).collect())
        .collect();

    let val_sets: Vec<HashSet<&str>> = val_tokens
        .iter()
        .map(|tokens| tokens.iter().map(|s| s.as_str()).collect())
        .collect();

    let mut swaps = Vec::new();

    for i in 0..n {
        let tok_k1 = &key_sets[i];
        let tok_v1 = &val_sets[i];
        for j in (i + 1)..n {
            let tok_k2 = &key_sets[j];

            if tok_k1.intersection(tok_k2).next().is_none() {
                continue;
            }

            let tok_v2 = &val_sets[j];
            let mut has_d1 = false;
            let mut has_d2 = false;
            let mut v1_has_d1 = false;
            let mut v1_has_d2 = false;
            let mut v2_has_d1 = false;
            let mut v2_has_d2 = false;

            for &t in tok_k1 {
                if !tok_k2.contains(t) {
                    has_d1 = true;
                    if tok_v1.contains(t) {
                        v1_has_d1 = true;
                        break;
                    }
                    if tok_v2.contains(t) {
                        v2_has_d1 = true;
                    }
                }
            }
            if !has_d1 || v1_has_d1 || !v2_has_d1 {
                continue;
            }

            for &t in tok_k2 {
                if !tok_k1.contains(t) {
                    has_d2 = true;
                    if tok_v2.contains(t) {
                        v2_has_d2 = true;
                        break;
                    }
                    if tok_v1.contains(t) {
                        v1_has_d2 = true;
                    }
                }
            }
            if !has_d2 || v2_has_d2 || !v1_has_d2 {
                continue;
            }

            swaps.push((i, j));
        }
    }

    swaps
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encode_arm_movw_movt() {
        let enc_r0 = encode_arm_movw_movt(0, 0x03567fdc);
        assert_eq!(enc_r0.len(), 8);
        assert_eq!(enc_r0[3], 0xe3);
        assert_eq!(enc_r0[7], 0xe3);

        let enc_r3 = encode_arm_movw_movt(3, 0x0678624c);
        assert_eq!((enc_r3[1] >> 4) & 0x0f, 3);
        assert_eq!((enc_r3[5] >> 4) & 0x0f, 3);
    }

    #[test]
    fn test_has_and_repoint_arm_movw_movt() {
        let mut text_buf = vec![0x90; 128];
        let vma1 = 0x0678624c;
        let vma2 = 0x067876ac;

        assert!(!has_arm_movw_movt_any_reg(&text_buf, vma1));

        let pat_r2 = encode_arm_movw_movt(2, vma1);
        text_buf[20..28].copy_from_slice(&pat_r2);
        let pat_r7 = encode_arm_movw_movt(7, vma1);
        text_buf[64..72].copy_from_slice(&pat_r7);

        assert!(has_arm_movw_movt_any_reg(&text_buf, vma1));
        assert!(!has_arm_movw_movt_any_reg(&text_buf, vma2));

        let (patched, count) = repoint_arm_movw_movt_all_regs(&text_buf, vma1, vma2);
        assert_eq!(count, 2);
        assert!(!has_arm_movw_movt_any_reg(&patched, vma1));
        assert!(has_arm_movw_movt_any_reg(&patched, vma2));
    }

    #[test]
    fn test_find_free_zero_padding() {
        let mut ro_bytes = vec![0xff; 256];
        ro_bytes[64..96].fill(0x00); // 32 bytes of zeros at 64

        let found = find_free_zero_padding(&ro_bytes, 0x1000, 24, 16, 0);
        assert_eq!(found, Some(0x1040)); // 0x1000 + 64

        let not_found = find_free_zero_padding(&ro_bytes, 0x1000, 48, 16, 0);
        assert_eq!(not_found, None);
    }

    #[test]
    fn test_detect_bipartite_token_swaps() {
        let keys = vec![
            "common_outside_milk_tube_rinse".to_string(),
            "common_milk_frother_system_rinse".to_string(),
        ];
        let key_tokens = vec![
            vec!["external".to_string(), "milk".to_string(), "tube".to_string(), "rinse".to_string()],
            vec!["milk".to_string(), "system".to_string(), "rinse".to_string()],
        ];
        // Swapped translations: key 0 got system, key 1 got tube/external
        let val_tokens = vec![
            vec!["milk".to_string(), "system".to_string(), "rinse".to_string()],
            vec!["external".to_string(), "tube".to_string(), "milk".to_string()],
        ];

        let swaps = detect_bipartite_token_swaps(keys, key_tokens, val_tokens);
        assert_eq!(swaps.len(), 1);
        assert_eq!(swaps[0], (0, 1));
    }
}
