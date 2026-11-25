#ifndef SPECTRA_WIN_SAFE_H
#define SPECTRA_WIN_SAFE_H

#include <windows.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>
#include <wchar.h>

#ifndef LOAD_LIBRARY_SEARCH_SYSTEM32
#define LOAD_LIBRARY_SEARCH_SYSTEM32 0x00000800
#endif

static inline void enable_safe_dll_search(void) {
    HMODULE hKernel32 = GetModuleHandleW(L"kernel32.dll");
    if (hKernel32) {
        typedef BOOL (WINAPI *PFN_SetDefaultDllDirectories)(DWORD);
        PFN_SetDefaultDllDirectories pfn =
            (PFN_SetDefaultDllDirectories)(void *)GetProcAddress(hKernel32, "SetDefaultDllDirectories");
        if (pfn) {
            pfn(LOAD_LIBRARY_SEARCH_SYSTEM32);
        }
    }
}

static inline void safe_wcopy(wchar_t *dst, size_t cap, const wchar_t *src) {
    if (!dst || cap == 0) return;
    if (!src) {
        dst[0] = L'\0';
        return;
    }
    size_t i = 0;
    while (i + 1 < cap && src[i] != L'\0') {
        dst[i] = src[i];
        i++;
    }
    dst[i] = L'\0';
}

static inline BOOL safe_wappendf(wchar_t *dst, size_t cap, size_t *pos, const wchar_t *fmt, ...) {
    if (!dst || !pos || *pos >= cap || cap == 0) return FALSE;
    size_t avail = cap - *pos;
    va_list args;
    va_start(args, fmt);
    int n = _vsnwprintf(dst + *pos, avail, fmt, args);
    va_end(args);
    if (n < 0 || (size_t)n >= avail) {
        dst[cap - 1] = L'\0';
        return FALSE;
    }
    *pos += (size_t)n;
    return TRUE;
}

static inline BOOL safe_append_win32_arg(wchar_t *dst, size_t cap, size_t *pos, const wchar_t *arg) {
    if (!dst || !pos || !arg) return FALSE;
    if (!safe_wappendf(dst, cap, pos, L" \"")) return FALSE;

    size_t backslashes = 0;
    for (const wchar_t *p = arg; *p != L'\0'; p++) {
        if (*p == L'\\') {
            backslashes++;
        } else if (*p == L'"') {
            for (size_t k = 0; k < backslashes * 2 + 1; k++) {
                if (*pos + 1 >= cap) {
                    dst[cap - 1] = L'\0';
                    return FALSE;
                }
                dst[(*pos)++] = L'\\';
            }
            if (*pos + 1 >= cap) {
                dst[cap - 1] = L'\0';
                return FALSE;
            }
            dst[(*pos)++] = L'"';
            backslashes = 0;
        } else {
            for (size_t k = 0; k < backslashes; k++) {
                if (*pos + 1 >= cap) {
                    dst[cap - 1] = L'\0';
                    return FALSE;
                }
                dst[(*pos)++] = L'\\';
            }
            backslashes = 0;
            if (*pos + 1 >= cap) {
                dst[cap - 1] = L'\0';
                return FALSE;
            }
            dst[(*pos)++] = *p;
        }
    }
    for (size_t k = 0; k < backslashes * 2; k++) {
        if (*pos + 1 >= cap) {
            dst[cap - 1] = L'\0';
            return FALSE;
        }
        dst[(*pos)++] = L'\\';
    }
    if (*pos + 1 >= cap) {
        dst[cap - 1] = L'\0';
        return FALSE;
    }
    dst[(*pos)++] = L'"';
    dst[*pos] = L'\0';
    return TRUE;
}

static inline BOOL is_not_reparse_point(const wchar_t *path) {
    if (!path || path[0] == L'\0') return FALSE;
    DWORD attr = GetFileAttributesW(path);
    if (attr == INVALID_FILE_ATTRIBUTES) {
        return TRUE;
    }
    return (attr & FILE_ATTRIBUTE_REPARSE_POINT) == 0;
}

static inline BOOL is_safe_install_path(const wchar_t *path) {
    if (!path || path[0] == L'\0') return FALSE;
    size_t len = wcslen(path);
    if (len < 4 || len >= MAX_PATH) return FALSE;

    /* Reject bare drive roots such as "C:", "C:\", "C:/", or UNC/root slashes */
    if ((len <= 3 && path[1] == L':') ||
        (len == 1 && (path[0] == L'\\' || path[0] == L'/'))) {
        return FALSE;
    }
    /* Reject trailing space or dot (Win32 path canonicalization hazard) */
    if (path[len - 1] == L' ' || path[len - 1] == L'.') {
        return FALSE;
    }

    for (const wchar_t *p = path; *p != L'\0'; p++) {
        wchar_t ch = *p;
        if (ch < 0x20 || ch == L'"' || ch == L'%' || ch == L'&' ||
            ch == L'|' || ch == L'^' || ch == L'<' || ch == L'>' ||
            ch == L'!' || ch == L'(' || ch == L')' || ch == L';' ||
            ch == L'`' || ch == L'$' || ch == L'\r' || ch == L'\n') {
            return FALSE;
        }
    }
    return is_not_reparse_point(path);
}

#endif /* SPECTRA_WIN_SAFE_H */
