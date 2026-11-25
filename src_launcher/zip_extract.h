#ifndef SPECTRA_ZIP_EXTRACT_H
#define SPECTRA_ZIP_EXTRACT_H

#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

#ifdef ZIP_EXTRACT_POSIX_TEST
#include <stdio.h>
#include <errno.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <wchar.h>
#ifndef MAX_PATH
#define MAX_PATH 4096
#endif
#else
#include <windows.h>
#include <wchar.h>
#endif

/* ============================================================================
 * CRC-32 (IEEE 802.3, polynomial 0xEDB88320)
 * ============================================================================ */
static uint32_t zip_crc32(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFu;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint32_t)data[i];
        for (int b = 0; b < 8; b++) {
            uint32_t mask = (uint32_t)(-(int32_t)(crc & 1u));
            crc = (crc >> 1) ^ (0xEDB88320u & mask);
        }
    }
    return ~crc;
}

static inline uint16_t zip_rd16(const uint8_t *p) {
    return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static inline uint32_t zip_rd32(const uint8_t *p) {
    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

/* ============================================================================
 * RFC 1951 DEFLATE Decompressor
 * ============================================================================ */
#define ZIP_MAX_BITS   15
#define ZIP_MAX_LCODES 286
#define ZIP_MAX_DCODES 30
#define ZIP_MAX_CODES  (ZIP_MAX_LCODES + ZIP_MAX_DCODES)
#define ZIP_FIX_LCODES 288

typedef struct {
    int16_t count[ZIP_MAX_BITS + 1];
    uint16_t symbol[ZIP_FIX_LCODES];
} ZipHuffTable;

typedef struct {
    const uint8_t *src;
    size_t src_len;
    size_t src_pos;
    uint32_t bit_buf;
    int bit_cnt;

    uint8_t *dst;
    size_t dst_cap;
    size_t dst_pos;
} ZipInflateState;

static int zip_bits(ZipInflateState *s, int need) {
    uint32_t val = s->bit_buf;
    while (s->bit_cnt < need) {
        if (s->src_pos >= s->src_len) {
            return -1;
        }
        val |= ((uint32_t)s->src[s->src_pos++]) << s->bit_cnt;
        s->bit_cnt += 8;
    }
    s->bit_buf = val >> need;
    s->bit_cnt -= need;
    return (int)(val & ((1u << need) - 1u));
}

static int zip_huff_construct(ZipHuffTable *h, const int16_t *lengths, int n) {
    for (int len = 0; len <= ZIP_MAX_BITS; len++) {
        h->count[len] = 0;
    }
    for (int sym = 0; sym < n; sym++) {
        if (lengths[sym] < 0 || lengths[sym] > ZIP_MAX_BITS) {
            return -1;
        }
        h->count[lengths[sym]]++;
    }
    if (h->count[0] == n) {
        return 0;
    }

    int left = 1;
    for (int len = 1; len <= ZIP_MAX_BITS; len++) {
        left <<= 1;
        left -= h->count[len];
        if (left < 0) {
            return -1;
        }
    }

    int16_t offs[ZIP_MAX_BITS + 1];
    offs[1] = 0;
    for (int len = 1; len < ZIP_MAX_BITS; len++) {
        offs[len + 1] = (int16_t)(offs[len] + h->count[len]);
    }

    for (int sym = 0; sym < n; sym++) {
        if (lengths[sym] != 0) {
            h->symbol[offs[lengths[sym]]++] = (uint16_t)sym;
        }
    }
    return 0;
}

static int zip_huff_decode(ZipInflateState *s, const ZipHuffTable *h) {
    int code = 0;
    int first = 0;
    int index = 0;
    uint32_t bitbuf = s->bit_buf;
    int left = s->bit_cnt;

    for (int len = 1; len <= ZIP_MAX_BITS; len++) {
        if (left == 0) {
            if (s->src_pos >= s->src_len) {
                return -1;
            }
            bitbuf = s->src[s->src_pos++];
            left = 8;
        }
        code |= (int)(bitbuf & 1u);
        bitbuf >>= 1;
        left--;

        int count = h->count[len];
        if (code - count < first) {
            s->bit_buf = bitbuf;
            s->bit_cnt = left;
            return (int)h->symbol[index + (code - first)];
        }
        index += count;
        first += count;
        first <<= 1;
        code <<= 1;
    }
    return -1;
}

static int zip_decode_codes(ZipInflateState *s, const ZipHuffTable *lencode, const ZipHuffTable *distcode) {
    static const uint16_t lens[29] = {
        3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31,
        35, 43, 51, 59, 67, 83, 99, 115, 131, 163, 195, 227, 258
    };
    static const uint8_t lext[29] = {
        0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2,
        3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0
    };
    static const uint16_t dists[30] = {
        1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193,
        257, 385, 513, 769, 1025, 1537, 2049, 3073, 4097, 6145,
        8193, 12289, 16385, 24577
    };
    static const uint8_t dext[30] = {
        0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6,
        7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13, 13
    };

    for (;;) {
        int sym = zip_huff_decode(s, lencode);
        if (sym < 0) return -1;
        if (sym < 256) {
            if (s->dst_pos >= s->dst_cap) return -1;
            s->dst[s->dst_pos++] = (uint8_t)sym;
        } else if (sym == 256) {
            return 0;
        } else {
            sym -= 257;
            if (sym >= 29) return -1;
            int extra_l = zip_bits(s, lext[sym]);
            if (extra_l < 0) return -1;
            size_t match_len = (size_t)lens[sym] + (size_t)extra_l;

            int dsym = zip_huff_decode(s, distcode);
            if (dsym < 0 || dsym >= 30) return -1;
            int extra_d = zip_bits(s, dext[dsym]);
            if (extra_d < 0) return -1;
            size_t dist = (size_t)dists[dsym] + (size_t)extra_d;

            if (dist == 0 || dist > s->dst_pos) return -1;
            if (s->dst_pos + match_len > s->dst_cap) return -1;

            for (size_t i = 0; i < match_len; i++) {
                s->dst[s->dst_pos] = s->dst[s->dst_pos - dist];
                s->dst_pos++;
            }
        }
    }
}

static int zip_inflate_raw(const uint8_t *src, size_t src_len, uint8_t *dst, size_t dst_cap, size_t *out_len) {
    ZipInflateState s;
    s.src = src;
    s.src_len = src_len;
    s.src_pos = 0;
    s.bit_buf = 0;
    s.bit_cnt = 0;
    s.dst = dst;
    s.dst_cap = dst_cap;
    s.dst_pos = 0;

    int bfinal = 0;
    do {
        bfinal = zip_bits(&s, 1);
        if (bfinal < 0) return -1;
        int btype = zip_bits(&s, 2);
        if (btype < 0) return -1;

        if (btype == 0) {
            /* Stored (uncompressed) block */
            int discard = s.bit_cnt & 7;
            s.bit_buf >>= discard;
            s.bit_cnt -= discard;
            s.src_pos -= (size_t)(s.bit_cnt / 8);
            s.bit_buf = 0;
            s.bit_cnt = 0;

            if (s.src_pos + 4 > s.src_len) return -1;
            uint16_t len = zip_rd16(s.src + s.src_pos);
            uint16_t nlen = zip_rd16(s.src + s.src_pos + 2);
            s.src_pos += 4;
            if (len != (uint16_t)(~nlen)) return -1;
            if (s.src_pos + len > s.src_len) return -1;
            if (s.dst_pos + len > s.dst_cap) return -1;
            if (len > 0) {
                memcpy(s.dst + s.dst_pos, s.src + s.src_pos, len);
                s.dst_pos += len;
                s.src_pos += len;
            }
        } else if (btype == 1) {
            /* Fixed Huffman */
            int16_t lengths[ZIP_FIX_LCODES];
            int sym;
            for (sym = 0; sym < 144; sym++) lengths[sym] = 8;
            for (; sym < 256; sym++) lengths[sym] = 9;
            for (; sym < 280; sym++) lengths[sym] = 7;
            for (; sym < 288; sym++) lengths[sym] = 8;

            ZipHuffTable lencode, distcode;
            if (zip_huff_construct(&lencode, lengths, ZIP_FIX_LCODES) != 0) return -1;
            for (sym = 0; sym < 30; sym++) lengths[sym] = 5;
            if (zip_huff_construct(&distcode, lengths, 30) != 0) return -1;

            if (zip_decode_codes(&s, &lencode, &distcode) != 0) return -1;
        } else if (btype == 2) {
            /* Dynamic Huffman */
            static const uint8_t order[19] = {
                16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15
            };
            int nlen = zip_bits(&s, 5);
            int ndist = zip_bits(&s, 5);
            int ncode = zip_bits(&s, 4);
            if (nlen < 0 || ndist < 0 || ncode < 0) return -1;
            nlen += 257;
            ndist += 1;
            ncode += 4;
            if (nlen > ZIP_MAX_LCODES || ndist > ZIP_MAX_DCODES) return -1;

            int16_t lengths[ZIP_MAX_CODES];
            for (int i = 0; i < ncode; i++) {
                int v = zip_bits(&s, 3);
                if (v < 0) return -1;
                lengths[order[i]] = (int16_t)v;
            }
            for (int i = ncode; i < 19; i++) {
                lengths[order[i]] = 0;
            }

            ZipHuffTable codelencode;
            if (zip_huff_construct(&codelencode, lengths, 19) != 0) return -1;

            int idx = 0;
            int total = nlen + ndist;
            while (idx < total) {
                int sym = zip_huff_decode(&s, &codelencode);
                if (sym < 0) return -1;
                if (sym < 16) {
                    lengths[idx++] = (int16_t)sym;
                } else {
                    int16_t rep_val = 0;
                    int rep_cnt = 0;
                    if (sym == 16) {
                        if (idx == 0) return -1;
                        rep_val = lengths[idx - 1];
                        int extra = zip_bits(&s, 2);
                        if (extra < 0) return -1;
                        rep_cnt = 3 + extra;
                    } else if (sym == 17) {
                        int extra = zip_bits(&s, 3);
                        if (extra < 0) return -1;
                        rep_cnt = 3 + extra;
                    } else {
                        int extra = zip_bits(&s, 7);
                        if (extra < 0) return -1;
                        rep_cnt = 11 + extra;
                    }
                    if (idx + rep_cnt > total) return -1;
                    while (rep_cnt-- > 0) {
                        lengths[idx++] = rep_val;
                    }
                }
            }

            if (lengths[256] == 0) return -1;

            ZipHuffTable lencode, distcode;
            if (zip_huff_construct(&lencode, lengths, nlen) != 0) return -1;
            if (zip_huff_construct(&distcode, lengths + nlen, ndist) != 0) return -1;

            if (zip_decode_codes(&s, &lencode, &distcode) != 0) return -1;
        } else {
            return -1;
        }
    } while (!bfinal);

    *out_len = s.dst_pos;
    return 0;
}

/* ============================================================================
 * Path Sanitization & Zip-Slip / Windows Reserved Device Guard
 * ============================================================================ */
static int zip_is_reserved_dos_segment(const uint8_t *seg, size_t seg_len) {
    if (seg_len == 0) return 1;
    /* Win32 silently strips trailing dots and spaces, enabling name-collision attacks */
    if (seg[seg_len - 1] == '.' || seg[seg_len - 1] == ' ') return 1;

    /* Extract stem before first '.' (Win32 treats CON.txt, NUL.exe, etc. as reserved devices) */
    size_t stem_len = seg_len;
    for (size_t i = 0; i < seg_len; i++) {
        uint8_t c = seg[i];
        if (c == '<' || c == '>' || c == ':' || c == '"' || c == '|' || c == '?' || c == '*') {
            return 1;
        }
        if (c == '.' && stem_len == seg_len) {
            stem_len = i;
        }
    }
    if (stem_len == 0) return 0; /* e.g. ".gitignore" is valid unless ending in '.' */

    if (stem_len == 3 || stem_len == 4) {
        char up[5];
        for (size_t i = 0; i < stem_len; i++) {
            uint8_t c = seg[i];
            up[i] = (char)((c >= 'a' && c <= 'z') ? (c - 'a' + 'A') : c);
        }
        up[stem_len] = '\0';
        if (stem_len == 3) {
            if (strcmp(up, "CON") == 0 || strcmp(up, "PRN") == 0 ||
                strcmp(up, "AUX") == 0 || strcmp(up, "NUL") == 0) {
                return 1;
            }
        } else if (stem_len == 4) {
            if ((strncmp(up, "COM", 3) == 0 || strncmp(up, "LPT", 3) == 0) &&
                up[3] >= '1' && up[3] <= '9') {
                return 1;
            }
        }
    }
    return 0;
}

static int zip_sanitize_rel_path(const uint8_t *raw_name, size_t raw_len, char *norm_out, size_t norm_cap, int *is_dir) {
    if (!raw_name || raw_len == 0 || raw_len >= norm_cap) return 0;

    /* Reject NUL bytes, control chars, leading separators, or drive letters */
    if (raw_name[0] == '/' || raw_name[0] == '\\') return 0;
    for (size_t i = 0; i < raw_len; i++) {
        uint8_t c = raw_name[i];
        if (c == 0 || c < 0x20 || c == ':') return 0;
    }

    int trailing_slash = (raw_name[raw_len - 1] == '/' || raw_name[raw_len - 1] == '\\');
    size_t out_pos = 0;
    size_t seg_start = 0;

    for (size_t i = 0; i <= raw_len; i++) {
        int at_sep = (i == raw_len || raw_name[i] == '/' || raw_name[i] == '\\');
        if (!at_sep) continue;

        size_t seg_len = i - seg_start;
        if (seg_len == 2 && raw_name[seg_start] == '.' && raw_name[seg_start + 1] == '.') {
            /* Strict Zip-Slip rejection of any '..' path segment */
            return 0;
        }
        if (seg_len > 0 && !(seg_len == 1 && raw_name[seg_start] == '.')) {
            if (zip_is_reserved_dos_segment(raw_name + seg_start, seg_len)) {
                return 0;
            }
            if (out_pos > 0) {
                if (out_pos + 1 >= norm_cap) return 0;
                norm_out[out_pos++] = '/';
            }
            if (out_pos + seg_len >= norm_cap) return 0;
            memcpy(norm_out + out_pos, raw_name + seg_start, seg_len);
            out_pos += seg_len;
        }
        seg_start = i + 1;
    }

    if (out_pos == 0) {
        /* Root '.' entry - harmless directory marker, skip safely */
        *is_dir = 1;
        norm_out[0] = '\0';
        return 1;
    }

    norm_out[out_pos] = '\0';
    *is_dir = trailing_slash ? 1 : 0;
    return 1;
}

/* ============================================================================
 * Platform Filesystem Helpers (Windows Native + POSIX Test Mode)
 * ============================================================================ */
#ifdef ZIP_EXTRACT_POSIX_TEST

static int zip_reject_symlink_posix(const char *path) {
    struct stat st;
    if (lstat(path, &st) == 0 && S_ISLNK(st.st_mode)) {
        return -1;
    }
    return 0;
}

static int zip_mkdir_recursive_posix(const char *dir) {
    char tmp[MAX_PATH];
    size_t len = strlen(dir);
    if (len == 0 || len >= sizeof(tmp)) return -1;
    memcpy(tmp, dir, len + 1);
    for (size_t i = 1; i < len; i++) {
        if (tmp[i] == '/') {
            tmp[i] = '\0';
            if (zip_reject_symlink_posix(tmp) != 0) return -1;
            if (mkdir(tmp, 0755) != 0 && errno != EEXIST) return -1;
            if (zip_reject_symlink_posix(tmp) != 0) return -1;
            tmp[i] = '/';
        }
    }
    if (zip_reject_symlink_posix(tmp) != 0) return -1;
    if (mkdir(tmp, 0755) != 0 && errno != EEXIST) return -1;
    if (zip_reject_symlink_posix(tmp) != 0) return -1;
    return 0;
}

static int zip_write_entry_file(const char *target_dir, const char *rel_norm, int is_dir, const uint8_t *data, size_t size) {
    if (rel_norm[0] == '\0') return zip_mkdir_recursive_posix(target_dir);

    char full_path[MAX_PATH];
    int n = snprintf(full_path, sizeof(full_path), "%s/%s", target_dir, rel_norm);
    if (n <= 0 || (size_t)n >= sizeof(full_path)) return -1;

    if (is_dir) {
        return zip_mkdir_recursive_posix(full_path);
    }

    char parent[MAX_PATH];
    memcpy(parent, full_path, (size_t)n + 1);
    char *slash = strrchr(parent, '/');
    if (slash) {
        *slash = '\0';
        if (zip_mkdir_recursive_posix(parent) != 0) return -1;
    }
    if (zip_reject_symlink_posix(full_path) != 0) return -1;

    char tmp_path[MAX_PATH];
    int tn = snprintf(tmp_path, sizeof(tmp_path), "%s.tmp", full_path);
    if (tn <= 0 || (size_t)tn >= sizeof(tmp_path)) return -1;

    FILE *fp = fopen(tmp_path, "wb");
    if (!fp) return -1;
    if (size > 0 && fwrite(data, 1, size, fp) != size) {
        fclose(fp);
        unlink(tmp_path);
        return -1;
    }
    if (fclose(fp) != 0) {
        unlink(tmp_path);
        return -1;
    }
    if (rename(tmp_path, full_path) != 0) {
        unlink(tmp_path);
        return -1;
    }
    return 0;
}

#else /* Windows Win32 */

static int zip_reject_reparse_point_w(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    if (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_REPARSE_POINT)) {
        return -1;
    }
    return 0;
}

static int zip_mkdir_recursive_w(const wchar_t *dir) {
    wchar_t tmp[MAX_PATH * 2];
    size_t len = wcslen(dir);
    if (len == 0 || len >= (MAX_PATH * 2)) return -1;
    memcpy(tmp, dir, (len + 1) * sizeof(wchar_t));

    for (size_t i = 1; i < len; i++) {
        if (tmp[i] == L'\\' || tmp[i] == L'/') {
            if (i == 2 && tmp[1] == L':') {
                tmp[i] = L'\\';
                continue;
            }
            tmp[i] = L'\0';
            if (zip_reject_reparse_point_w(tmp) != 0) return -1;
            if (!CreateDirectoryW(tmp, NULL)) {
                DWORD err = GetLastError();
                if (err != ERROR_ALREADY_EXISTS) {
                    DWORD attr = GetFileAttributesW(tmp);
                    if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
                        return -1;
                    }
                }
            }
            if (zip_reject_reparse_point_w(tmp) != 0) return -1;
            tmp[i] = L'\\';
        }
    }
    if (zip_reject_reparse_point_w(tmp) != 0) return -1;
    if (!CreateDirectoryW(tmp, NULL)) {
        DWORD err = GetLastError();
        if (err != ERROR_ALREADY_EXISTS) {
            DWORD attr = GetFileAttributesW(tmp);
            if (attr == INVALID_FILE_ATTRIBUTES || !(attr & FILE_ATTRIBUTE_DIRECTORY)) {
                return -1;
            }
        }
    }
    if (zip_reject_reparse_point_w(tmp) != 0) return -1;
    return 0;
}

static int zip_write_entry_file_w(const wchar_t *target_dir, const char *rel_norm, int is_dir, const uint8_t *data, size_t size) {
    if (rel_norm[0] == '\0') return zip_mkdir_recursive_w(target_dir);

    /* Strict UTF-8 only — never silently fall back to CP_ACP codepage mapping */
    wchar_t rel_w[MAX_PATH * 2];
    int wlen = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, rel_norm, -1, rel_w, MAX_PATH * 2);
    if (wlen <= 0) return -1;
    for (int i = 0; rel_w[i] != L'\0'; i++) {
        if (rel_w[i] == L'/') rel_w[i] = L'\\';
    }

    wchar_t full_path[MAX_PATH * 2];
    size_t tlen = wcslen(target_dir);
    int need_sep = (tlen > 0 && target_dir[tlen - 1] != L'\\' && target_dir[tlen - 1] != L'/') ? 1 : 0;
    int fn = _snwprintf(full_path, MAX_PATH * 2, need_sep ? L"%ls\\%ls" : L"%ls%ls", target_dir, rel_w);
    if (fn <= 0 || fn >= MAX_PATH * 2) return -1;

    if (is_dir) {
        return zip_mkdir_recursive_w(full_path);
    }

    wchar_t parent[MAX_PATH * 2];
    memcpy(parent, full_path, (size_t)(fn + 1) * sizeof(wchar_t));
    wchar_t *slash = wcsrchr(parent, L'\\');
    if (slash) {
        *slash = L'\0';
        if (zip_mkdir_recursive_w(parent) != 0) return -1;
    }
    if (zip_reject_reparse_point_w(full_path) != 0) return -1;

    wchar_t tmp_path[MAX_PATH * 2];
    int tn = _snwprintf(tmp_path, MAX_PATH * 2, L"%ls.tmp", full_path);
    if (tn <= 0 || tn >= MAX_PATH * 2) return -1;
    if (zip_reject_reparse_point_w(tmp_path) != 0) return -1;

    HANDLE hFile = CreateFileW(tmp_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) return -1;

    size_t rem = size;
    const uint8_t *p = data;
    while (rem > 0) {
        DWORD chunk = (rem > 0x40000000u) ? 0x40000000u : (DWORD)rem;
        DWORD written = 0;
        if (!WriteFile(hFile, p, chunk, &written, NULL) || written != chunk) {
            CloseHandle(hFile);
            DeleteFileW(tmp_path);
            return -1;
        }
        p += written;
        rem -= written;
    }
    CloseHandle(hFile);

    SetFileAttributesW(full_path, FILE_ATTRIBUTE_NORMAL);
    if (!MoveFileExW(tmp_path, full_path, MOVEFILE_REPLACE_EXISTING)) {
        DeleteFileW(tmp_path);
        return -1;
    }
    return 0;
}

#endif

/* ============================================================================
 * ZIP Central Directory Parser & In-Memory Extractor
 * Returns 1 (TRUE) on full verified extraction, 0 (FALSE) on any error.
 * ============================================================================ */
#define SPECTRA_ZIP_MAX_TOTAL_UNCOMP (512ULL * 1024ULL * 1024ULL)

#ifdef ZIP_EXTRACT_POSIX_TEST
static int extract_zip_from_memory(const unsigned char *buf, size_t len, const char *target_dir)
#else
static BOOL extract_zip_from_memory(const unsigned char *buf, size_t len, const wchar_t *target_dir)
#endif
{
    if (!buf || len < 22 || !target_dir || !target_dir[0]) return 0;

#ifdef ZIP_EXTRACT_POSIX_TEST
    if (zip_mkdir_recursive_posix(target_dir) != 0) return 0;
#else
    if (zip_mkdir_recursive_w(target_dir) != 0) return 0;
#endif

    /* Locate End of Central Directory (EOCD: 0x06054b50) */
    size_t min_off = (len > 22 + 65535) ? (len - 22 - 65535) : 0;
    size_t eocd_off = (size_t)-1;
    for (size_t i = len - 22; ; i--) {
        if (zip_rd32(buf + i) == 0x06054B50u) {
            uint16_t cmt_len = zip_rd16(buf + i + 20);
            if (i + 22 + cmt_len == len) {
                eocd_off = i;
                break;
            }
        }
        if (i == min_off) break;
    }
    if (eocd_off == (size_t)-1) return 0;

    uint16_t disk_num = zip_rd16(buf + eocd_off + 4);
    uint16_t cd_disk = zip_rd16(buf + eocd_off + 6);
    uint16_t entries_disk = zip_rd16(buf + eocd_off + 8);
    uint16_t entries_total = zip_rd16(buf + eocd_off + 10);
    uint32_t cd_size = zip_rd32(buf + eocd_off + 12);
    uint32_t cd_offset = zip_rd32(buf + eocd_off + 16);

    if (disk_num != 0 || cd_disk != 0 || entries_disk != entries_total) return 0;
    if (cd_offset == 0xFFFFFFFFu || cd_size == 0xFFFFFFFFu || entries_total == 0xFFFFu) return 0;
    if ((size_t)cd_offset > len || (size_t)cd_size > len - (size_t)cd_offset) return 0;

    size_t pos = (size_t)cd_offset;
    size_t cd_end = pos + (size_t)cd_size;
    uint64_t total_uncomp = 0;

    for (uint16_t idx = 0; idx < entries_total; idx++) {
        if (pos + 46 > cd_end) return 0;
        if (zip_rd32(buf + pos) != 0x02014B50u) return 0;

        uint16_t cd_gp_flag = zip_rd16(buf + pos + 8);
        uint16_t method = zip_rd16(buf + pos + 10);
        uint32_t crc32_expected = zip_rd32(buf + pos + 16);
        uint32_t comp_size = zip_rd32(buf + pos + 20);
        uint32_t uncomp_size = zip_rd32(buf + pos + 24);
        uint16_t fname_len = zip_rd16(buf + pos + 28);
        uint16_t extra_len = zip_rd16(buf + pos + 30);
        uint16_t cmt_len = zip_rd16(buf + pos + 32);
        uint32_t ext_attr = zip_rd32(buf + pos + 38);
        uint32_t lfh_offset = zip_rd32(buf + pos + 42);

        /* Reject encrypted ZIP entries */
        if (cd_gp_flag & 0x0001u) return 0;

        size_t next_pos = pos + 46 + (size_t)fname_len + (size_t)extra_len + (size_t)cmt_len;
        if (next_pos > cd_end) return 0;

        /* Reject symlinks (POSIX S_IFLNK = 0120000 = 0xA000 in upper 16 bits) */
        if (((ext_attr >> 16) & 0xF000u) == 0xA000u) return 0;

        const uint8_t *cd_fname = buf + pos + 46;
        char norm_path[1024];
        int is_dir = 0;
        if (!zip_sanitize_rel_path(cd_fname, fname_len, norm_path, sizeof(norm_path), &is_dir)) {
            return 0;
        }
        if ((ext_attr & 0x10u) && uncomp_size == 0) {
            is_dir = 1;
        }

        /* Validate Local File Header (LFH) matches Central Directory (CD) */
        if ((size_t)lfh_offset + 30 > len) return 0;
        const uint8_t *lfh = buf + lfh_offset;
        if (zip_rd32(lfh) != 0x04034B50u) return 0;
        uint16_t lfh_gp_flag = zip_rd16(lfh + 6);
        uint16_t lfh_method = zip_rd16(lfh + 8);
        uint16_t lfh_fname_len = zip_rd16(lfh + 26);
        uint16_t lfh_extra_len = zip_rd16(lfh + 28);
        if (lfh_gp_flag & 0x0001u) return 0;
        if (lfh_method != method) return 0;
        if (lfh_fname_len != fname_len) return 0;
        size_t lfh_name_end = (size_t)lfh_offset + 30 + (size_t)lfh_fname_len;
        if (lfh_name_end > len) return 0;
        if (memcmp(lfh + 30, cd_fname, fname_len) != 0) return 0;
        if ((lfh_gp_flag & 0x0008u) == 0) {
            if (zip_rd32(lfh + 14) != crc32_expected ||
                zip_rd32(lfh + 18) != comp_size ||
                zip_rd32(lfh + 22) != uncomp_size) {
                return 0;
            }
        }

        size_t data_off = lfh_name_end + (size_t)lfh_extra_len;
        if (data_off > len || (size_t)comp_size > len - data_off) return 0;

        if (is_dir) {
            if (uncomp_size != 0) return 0;
#ifdef ZIP_EXTRACT_POSIX_TEST
            if (zip_write_entry_file(target_dir, norm_path, 1, NULL, 0) != 0) return 0;
#else
            if (zip_write_entry_file_w(target_dir, norm_path, 1, NULL, 0) != 0) return 0;
#endif
        } else {
            /* Enforce cumulative uncompressed zip-bomb budget across entire archive */
            if ((uint64_t)uncomp_size > SPECTRA_ZIP_MAX_TOTAL_UNCOMP ||
                total_uncomp > SPECTRA_ZIP_MAX_TOTAL_UNCOMP - (uint64_t)uncomp_size) {
                return 0;
            }
            total_uncomp += (uint64_t)uncomp_size;

            uint8_t *out_buf = NULL;
            const uint8_t *write_ptr = NULL;

            if (method == 0) {
                if (comp_size != uncomp_size) return 0;
                write_ptr = buf + data_off;
            } else if (method == 8) {
                size_t alloc_sz = uncomp_size > 0 ? (size_t)uncomp_size : 1u;
                out_buf = (uint8_t *)malloc(alloc_sz);
                if (!out_buf) return 0;
                size_t actual_out = 0;
                if (zip_inflate_raw(buf + data_off, comp_size, out_buf, uncomp_size, &actual_out) != 0 ||
                    actual_out != (size_t)uncomp_size) {
                    free(out_buf);
                    return 0;
                }
                write_ptr = out_buf;
            } else {
                return 0;
            }

            uint32_t actual_crc = zip_crc32(write_ptr, uncomp_size);
            if (actual_crc != crc32_expected) {
                free(out_buf);
                return 0;
            }

            int wr_rc;
#ifdef ZIP_EXTRACT_POSIX_TEST
            wr_rc = zip_write_entry_file(target_dir, norm_path, 0, write_ptr, uncomp_size);
#else
            wr_rc = zip_write_entry_file_w(target_dir, norm_path, 0, write_ptr, uncomp_size);
#endif
            free(out_buf);
            if (wr_rc != 0) return 0;
        }

        pos = next_pos;
    }

    return 1;
}

#endif /* SPECTRA_ZIP_EXTRACT_H */
