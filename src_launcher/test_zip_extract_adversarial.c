#define ZIP_EXTRACT_POSIX_TEST
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef MAX_PATH
#define MAX_PATH 4096
#endif

#include "zip_extract.h"

static void wr16(uint8_t *p, uint16_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
}

static void wr32(uint8_t *p, uint32_t v) {
    p[0] = (uint8_t)(v & 0xFF);
    p[1] = (uint8_t)((v >> 8) & 0xFF);
    p[2] = (uint8_t)((v >> 16) & 0xFF);
    p[3] = (uint8_t)((v >> 24) & 0xFF);
}

/* Builds a minimal single-entry stored ZIP in `out_buf` (returns total bytes). */
static size_t build_single_entry_zip(
    uint8_t *out,
    const char *lfh_name,
    const char *cd_name,
    const uint8_t *payload,
    uint32_t payload_len,
    uint16_t cd_gp_flag,
    uint16_t lfh_gp_flag,
    uint16_t cd_method,
    uint16_t lfh_method,
    uint32_t fake_uncomp_size
) {
    size_t lfh_nlen = strlen(lfh_name);
    size_t cd_nlen = strlen(cd_name);
    uint32_t crc = zip_crc32(payload, payload_len);
    size_t pos = 0;

    /* Local File Header */
    wr32(out + pos, 0x04034B50u);
    wr16(out + pos + 4, 20);
    wr16(out + pos + 6, lfh_gp_flag);
    wr16(out + pos + 8, lfh_method);
    wr16(out + pos + 10, 0);
    wr16(out + pos + 12, 0);
    wr32(out + pos + 14, crc);
    wr32(out + pos + 18, payload_len);
    wr32(out + pos + 22, fake_uncomp_size);
    wr16(out + pos + 26, (uint16_t)lfh_nlen);
    wr16(out + pos + 28, 0);
    memcpy(out + pos + 30, lfh_name, lfh_nlen);
    pos += 30 + lfh_nlen;
    if (payload_len > 0) {
        memcpy(out + pos, payload, payload_len);
        pos += payload_len;
    }

    size_t cd_off = pos;
    /* Central Directory Header */
    wr32(out + pos, 0x02014B50u);
    wr16(out + pos + 4, 20);
    wr16(out + pos + 6, 20);
    wr16(out + pos + 8, cd_gp_flag);
    wr16(out + pos + 10, cd_method);
    wr16(out + pos + 12, 0);
    wr16(out + pos + 14, 0);
    wr32(out + pos + 16, crc);
    wr32(out + pos + 20, payload_len);
    wr32(out + pos + 24, fake_uncomp_size);
    wr16(out + pos + 28, (uint16_t)cd_nlen);
    wr16(out + pos + 30, 0);
    wr16(out + pos + 32, 0);
    wr16(out + pos + 34, 0);
    wr16(out + pos + 36, 0);
    wr32(out + pos + 38, 0);
    wr32(out + pos + 42, 0);
    memcpy(out + pos + 46, cd_name, cd_nlen);
    pos += 46 + cd_nlen;

    size_t cd_size = pos - cd_off;
    /* EOCD */
    wr32(out + pos, 0x06054B50u);
    wr16(out + pos + 4, 0);
    wr16(out + pos + 6, 0);
    wr16(out + pos + 8, 1);
    wr16(out + pos + 10, 1);
    wr32(out + pos + 12, (uint32_t)cd_size);
    wr32(out + pos + 16, (uint32_t)cd_off);
    wr16(out + pos + 20, 0);
    pos += 22;
    return pos;
}

/* Builds a 2-entry archive whose declared uncompressed sizes sum to > 512 MiB. */
static size_t build_zip_bomb_budget_test(uint8_t *out) {
    const uint32_t each_uncomp = 300u * 1024u * 1024u; /* 300 MiB x 2 = 600 MiB > 512 MiB */
    const char *names[2] = {"a.bin", "b.bin"};
    size_t lfh_offs[2];
    size_t pos = 0;

    for (int i = 0; i < 2; i++) {
        lfh_offs[i] = pos;
        size_t nlen = strlen(names[i]);
        wr32(out + pos, 0x04034B50u);
        wr16(out + pos + 4, 20);
        wr16(out + pos + 6, 0);
        wr16(out + pos + 8, 8); /* deflate */
        wr32(out + pos + 14, 0);
        wr32(out + pos + 18, 2);
        wr32(out + pos + 22, each_uncomp);
        wr16(out + pos + 26, (uint16_t)nlen);
        wr16(out + pos + 28, 0);
        memcpy(out + pos + 30, names[i], nlen);
        pos += 30 + nlen;
        out[pos++] = 0x03;
        out[pos++] = 0x00;
    }

    size_t cd_off = pos;
    for (int i = 0; i < 2; i++) {
        size_t nlen = strlen(names[i]);
        wr32(out + pos, 0x02014B50u);
        wr16(out + pos + 4, 20);
        wr16(out + pos + 6, 20);
        wr16(out + pos + 8, 0);
        wr16(out + pos + 10, 8);
        wr32(out + pos + 16, 0);
        wr32(out + pos + 20, 2);
        wr32(out + pos + 24, each_uncomp);
        wr16(out + pos + 28, (uint16_t)nlen);
        wr32(out + pos + 42, (uint32_t)lfh_offs[i]);
        memcpy(out + pos + 46, names[i], nlen);
        pos += 46 + nlen;
    }
    size_t cd_size = pos - cd_off;
    wr32(out + pos, 0x06054B50u);
    wr16(out + pos + 8, 2);
    wr16(out + pos + 10, 2);
    wr32(out + pos + 12, (uint32_t)cd_size);
    wr32(out + pos + 16, (uint32_t)cd_off);
    pos += 22;
    return pos;
}

int main(void) {
    char norm[1024];
    int is_dir = 0;

    /* 1. Reject DOS reserved names, trailing dots/spaces, illegal chars, Zip-Slip */
    const char *bad_paths[] = {
        "CON", "con.txt", "NUL.exe", "PRN", "AUX", "COM1", "com9.dll", "LPT1", "lpt4.txt",
        "a/PRN/x.txt", "foo.", "foo ", "dir /a.txt", "dir./a.txt",
        "a<b.txt", "a>b.txt", "a|b.txt", "a?b.txt", "a*b.txt", "a\"b.txt",
        "../escape.txt", "a/../../escape.txt", "/abs/path.txt", "\\abs\\path.txt", "C:drive.txt"
    };
    for (size_t i = 0; i < sizeof(bad_paths) / sizeof(bad_paths[0]); i++) {
        int ok = zip_sanitize_rel_path((const uint8_t *)bad_paths[i], strlen(bad_paths[i]), norm, sizeof(norm), &is_dir);
        if (ok != 0) {
            fprintf(stderr, "FAIL: expected rejection for '%s', got accepted as '%s'\n", bad_paths[i], norm);
            return 1;
        }
    }

    /* 2. Accept valid relative paths including dotfiles and nested paths */
    const char *good_paths[] = {"spectra.exe", "web/dist/index.html", ".gitignore", "console.py", "COM10.txt"};
    for (size_t i = 0; i < sizeof(good_paths) / sizeof(good_paths[0]); i++) {
        int ok = zip_sanitize_rel_path((const uint8_t *)good_paths[i], strlen(good_paths[i]), norm, sizeof(norm), &is_dir);
        if (ok != 1) {
            fprintf(stderr, "FAIL: expected acceptance for '%s'\n", good_paths[i]);
            return 1;
        }
    }

    /* 3. Valid extraction + adversarial archive rejection */
    char tmp_tmpl[] = "/tmp/spectra_zip_asan_XXXXXX";
    char *tmp_dir = mkdtemp(tmp_tmpl);
    assert(tmp_dir != NULL);

    uint8_t zip_buf[4096];
    const uint8_t msg[] = "SPECTRA_OK_DATA";

    /* 3a. Valid stored archive succeeds */
    size_t zlen = build_single_entry_zip(zip_buf, "sub/ok.txt", "sub/ok.txt", msg, (uint32_t)(sizeof(msg) - 1), 0, 0, 0, 0, (uint32_t)(sizeof(msg) - 1));
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 1);

    /* 3b. Encrypted entry (gp_flag & 1) rejected */
    zlen = build_single_entry_zip(zip_buf, "enc.txt", "enc.txt", msg, (uint32_t)(sizeof(msg) - 1), 1, 1, 0, 0, (uint32_t)(sizeof(msg) - 1));
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 0);

    /* 3c. LFH <-> CD filename mismatch rejected */
    zlen = build_single_entry_zip(zip_buf, "evil.txt", "good.txt", msg, (uint32_t)(sizeof(msg) - 1), 0, 0, 0, 0, (uint32_t)(sizeof(msg) - 1));
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 0);

    /* 3d. LFH <-> CD method mismatch rejected */
    zlen = build_single_entry_zip(zip_buf, "m.txt", "m.txt", msg, (uint32_t)(sizeof(msg) - 1), 0, 0, 0, 8, (uint32_t)(sizeof(msg) - 1));
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 0);

    /* 3e. Cumulative Zip-Bomb > 512 MiB rejected */
    memset(zip_buf, 0, sizeof(zip_buf));
    zlen = build_zip_bomb_budget_test(zip_buf);
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 0);

    /* 3f. Symlink directory inside target_dir rejected */
    char sym_path[MAX_PATH];
    snprintf(sym_path, sizeof(sym_path), "%s/linkdir", tmp_dir);
    assert(symlink("/tmp", sym_path) == 0);
    zlen = build_single_entry_zip(zip_buf, "linkdir/escape.txt", "linkdir/escape.txt", msg, (uint32_t)(sizeof(msg) - 1), 0, 0, 0, 0, (uint32_t)(sizeof(msg) - 1));
    assert(extract_zip_from_memory(zip_buf, zlen, tmp_dir) == 0);

    printf("[OK] All ASan+UBSan adversarial zip_extract.h tests passed!\n");
    return 0;
}
