#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>
#include <tlhelp32.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <shellapi.h>
#include <conio.h>
#include "win_safe.h"
#include "zip_extract.h"

#define SPECTRA_BUILD        "20261125.1535"
#define SPECTRA_VERSION      "Build 20261125.1535"
#define SPECTRA_EDITION      "Windows Standalone Multi-Manufacturer"

static void log_updater(const wchar_t *fmt, ...) {
    wchar_t base_dir[MAX_PATH];
    wchar_t log_dir[MAX_PATH];
    wchar_t log_path[MAX_PATH];
    DWORD lad_len = GetEnvironmentVariableW(L"LOCALAPPDATA", base_dir, MAX_PATH);
    if (lad_len > 0 && lad_len < MAX_PATH && is_safe_install_path(base_dir)) {
        int dn = swprintf(log_dir, MAX_PATH, L"%ls\\SPECTRA", base_dir);
        if (dn > 0 && dn < MAX_PATH) {
            CreateDirectoryW(log_dir, NULL);
            dn = swprintf(log_dir, MAX_PATH, L"%ls\\SPECTRA\\logs", base_dir);
            if (dn > 0 && dn < MAX_PATH) {
                CreateDirectoryW(log_dir, NULL);
                if (swprintf(log_path, MAX_PATH, L"%ls\\spectra_update.log", log_dir) <= 0) {
                    return;
                }
            } else {
                return;
            }
        } else {
            return;
        }
    } else {
        if (GetTempPathW(MAX_PATH, base_dir) == 0) return;
        if (swprintf(log_path, MAX_PATH, L"%ls\\spectra_update.log", base_dir) <= 0) return;
    }

    /* Rotate log if larger than 256 KiB */
    WIN32_FILE_ATTRIBUTE_DATA fad;
    if (GetFileAttributesExW(log_path, GetFileExInfoStandard, &fad) &&
        (fad.nFileSizeHigh > 0 || fad.nFileSizeLow >= 256u * 1024u)) {
        wchar_t rot_path[MAX_PATH];
        int rn = swprintf(rot_path, MAX_PATH, L"%ls.1", log_path);
        if (rn > 0 && rn < MAX_PATH) {
            MoveFileExW(log_path, rot_path, MOVEFILE_REPLACE_EXISTING);
        }
    }

    FILE *f = _wfopen(log_path, L"a");
    if (!f) return;

    SYSTEMTIME st;
    GetLocalTime(&st);
    fwprintf(f, L"[%04d-%02d-%02d %02d:%02d:%02d] ",
             st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);

    va_list args;
    va_start(args, fmt);
    vfwprintf(f, fmt, args);
    va_end(args);
    fwprintf(f, L"\n");
    fclose(f);
}

static BOOL path_matches_install_scope(const wchar_t *img_path, const wchar_t *target_dir) {
    if (!img_path || !img_path[0] || !target_dir || !target_dir[0]) return FALSE;
    size_t tlen = wcslen(target_dir);
    while (tlen > 3 && (target_dir[tlen - 1] == L'\\' || target_dir[tlen - 1] == L'/')) {
        tlen--;
    }
    if (_wcsnicmp(img_path, target_dir, tlen) == 0 &&
        (img_path[tlen] == L'\\' || img_path[tlen] == L'/' || img_path[tlen] == L'\0')) {
        return TRUE;
    }

    /* Check immediate parent if target_dir ends with \build_* */
    wchar_t norm_dir[MAX_PATH];
    if (tlen < MAX_PATH) {
        safe_wcopy(norm_dir, tlen + 1, target_dir);
        const wchar_t *last_slash = wcsrchr(norm_dir, L'\\');
        if (last_slash && _wcsnicmp(last_slash + 1, L"build_", 6) == 0) {
            size_t plen = (size_t)(last_slash - norm_dir);
            if (plen > 0 && _wcsnicmp(img_path, norm_dir, plen) == 0 &&
                (img_path[plen] == L'\\' || img_path[plen] == L'/')) {
                return TRUE;
            }
        }
    }
    return FALSE;
}

static void strip_dir_arg(const wchar_t *raw, wchar_t *out, size_t max_len) {
    if (!raw || max_len == 0) {
        if (max_len > 0) out[0] = L'\0';
        return;
    }
    while (*raw == L'"' || *raw == L' ') raw++;
    safe_wcopy(out, max_len, raw);
    size_t len = wcslen(out);
    while (len > 0 && (out[len - 1] == L'"' || out[len - 1] == L' ' || out[len - 1] == L'\\' || out[len - 1] == L'/')) {
        if (len <= 3 && out[1] == L':' && (out[len - 1] == L'\\' || out[len - 1] == L'/')) {
            break;
        }
        out[--len] = L'\0';
    }
}

static void print_banner(void) {
    wprintf(L"==============================================================================\n");
    wprintf(L"  SPECTRA Updater — %hs [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
    wprintf(L"  Fast In-Place Telemetry & Diagnostic Suite Updater\n");
    wprintf(L"==============================================================================\n");
}

static BOOL dir_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY) && !(attr & FILE_ATTRIBUTE_REPARSE_POINT));
}

static BOOL file_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY));
}

static void kill_running_spectra(const wchar_t *target_dir) {
    DWORD my_pid = GetCurrentProcessId();
    log_updater(L"Scanning processes to stop running SPECTRA instances (my_pid=%lu, target=%ls)", my_pid, target_dir);

    for (int pass = 0; pass < 3; pass++) {
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
        if (snap == INVALID_HANDLE_VALUE) {
            log_updater(L"CreateToolhelp32Snapshot failed (err=%lu)", GetLastError());
            break;
        }

        PROCESSENTRY32W pe;
        ZeroMemory(&pe, sizeof(pe));
        pe.dwSize = sizeof(pe);
        int killed_in_pass = 0;

        if (Process32FirstW(snap, &pe)) {
            do {
                if (pe.th32ProcessID == 0 || pe.th32ProcessID == my_pid) {
                    continue;
                }

                BOOL is_spectra_bin = (_wcsicmp(pe.szExeFile, L"spectra-shell.exe") == 0 ||
                                       _wcsicmp(pe.szExeFile, L"spectra.exe") == 0);
                BOOL is_helper_bin = (_wcsicmp(pe.szExeFile, L"python.exe") == 0 ||
                                      _wcsicmp(pe.szExeFile, L"pythonw.exe") == 0 ||
                                      _wcsicmp(pe.szExeFile, L"msedgewebview2.exe") == 0);

                if (!is_spectra_bin && !is_helper_bin) {
                    continue;
                }

                HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE, FALSE, pe.th32ProcessID);
                if (!hProc) {
                    continue;
                }

                BOOL should_kill = FALSE;
                wchar_t img_path[MAX_PATH * 2];
                DWORD img_len = (DWORD)(sizeof(img_path) / sizeof(wchar_t));
                if (QueryFullProcessImageNameW(hProc, 0, img_path, &img_len)) {
                    if (path_matches_install_scope(img_path, target_dir)) {
                        should_kill = TRUE;
                    }
                }

                if (should_kill) {
                    log_updater(L"Terminating pid=%lu (%ls)", pe.th32ProcessID, pe.szExeFile);
                    if (TerminateProcess(hProc, 0)) {
                        WaitForSingleObject(hProc, 3000);
                        killed_in_pass++;
                    } else {
                        log_updater(L"TerminateProcess failed for pid=%lu (err=%lu)", pe.th32ProcessID, GetLastError());
                    }
                }
                CloseHandle(hProc);
            } while (Process32NextW(snap, &pe));
        }

        CloseHandle(snap);
        if (killed_in_pass == 0) {
            break;
        }
        Sleep(400);
    }

    // Give Windows a brief window to release mapped image/DLL locks
    Sleep(600);
}

static BOOL find_install_dir(wchar_t *out_dir, size_t max_len) {
    // 1. Check registry
    HKEY hKey;
    const wchar_t *subKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SPECTRA";
    if (RegOpenKeyExW(HKEY_CURRENT_USER, subKey, 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        wchar_t regPath[MAX_PATH + 1];
        DWORD size = (DWORD)(MAX_PATH * sizeof(wchar_t));
        DWORD type = REG_SZ;
        if (RegQueryValueExW(hKey, L"InstallLocation", NULL, &type, (LPBYTE)regPath, &size) == ERROR_SUCCESS &&
            (type == REG_SZ || type == REG_EXPAND_SZ) && size >= sizeof(wchar_t)) {
            size_t chars = size / sizeof(wchar_t);
            if (chars > MAX_PATH) chars = MAX_PATH;
            regPath[chars] = L'\0';
            regPath[MAX_PATH] = L'\0';
            RegCloseKey(hKey);

            wchar_t resolvedPath[MAX_PATH];
            if (type == REG_EXPAND_SZ) {
                DWORD exp = ExpandEnvironmentStringsW(regPath, resolvedPath, MAX_PATH);
                if (exp == 0 || exp >= MAX_PATH) {
                    resolvedPath[0] = L'\0';
                }
            } else {
                safe_wcopy(resolvedPath, MAX_PATH, regPath);
            }
            strip_dir_arg(resolvedPath, resolvedPath, MAX_PATH);
            if (resolvedPath[0] != L'\0' && dir_exists(resolvedPath)) {
                safe_wcopy(out_dir, max_len, resolvedPath);
                return TRUE;
            }
        } else {
            RegCloseKey(hKey);
        }
    }

    // 2. Check default %LOCALAPPDATA%\Programs\SPECTRA
    wchar_t local_app_data[MAX_PATH];
    DWORD lad_len = GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH);
    if (lad_len > 0 && lad_len < MAX_PATH) {
        wchar_t candidate[MAX_PATH];
        int cn = swprintf(candidate, MAX_PATH, L"%ls\\Programs\\SPECTRA", local_app_data);
        if (cn > 0 && cn < MAX_PATH && dir_exists(candidate)) {
            wchar_t build_sub[MAX_PATH];
            int bn = swprintf(build_sub, MAX_PATH, L"%ls\\build_%hs", candidate, SPECTRA_BUILD);
            if (bn > 0 && bn < MAX_PATH && dir_exists(build_sub)) {
                safe_wcopy(out_dir, max_len, build_sub);
                return TRUE;
            }
            safe_wcopy(out_dir, max_len, candidate);
            return TRUE;
        }
    }

    // 3. Check executable directory (ONLY if updater is placed directly inside an existing SPECTRA folder)
    wchar_t exe_dir[MAX_PATH];
    DWORD mlen = GetModuleFileNameW(NULL, exe_dir, MAX_PATH);
    if (mlen > 0 && mlen < MAX_PATH) {
        wchar_t *last_slash = wcsrchr(exe_dir, L'\\');
        if (last_slash) *last_slash = L'\0';

        wchar_t test_app[MAX_PATH];
        wchar_t test_exe[MAX_PATH];
        int n1 = swprintf(test_app, MAX_PATH, L"%ls\\spectra_app.py", exe_dir);
        int n2 = swprintf(test_exe, MAX_PATH, L"%ls\\spectra.exe", exe_dir);
        if (n1 > 0 && n1 < MAX_PATH && n2 > 0 && n2 < MAX_PATH &&
            file_exists(test_app) && file_exists(test_exe)) {
            safe_wcopy(out_dir, max_len, exe_dir);
            return TRUE;
        }
    }

    return FALSE;
}

static void clear_locked_binaries(const wchar_t *dir) {
    const wchar_t *bins[4] = {
        L"spectra.exe",
        L"spectra-shell.exe",
        L"spectra_py.pyd",
        L"WebView2Loader.dll"
    };
    for (int i = 0; i < 4; i++) {
        wchar_t src[MAX_PATH];
        wchar_t bak[MAX_PATH];
        int ns = swprintf(src, MAX_PATH, L"%ls\\%ls", dir, bins[i]);
        int nb = swprintf(bak, MAX_PATH, L"%ls\\%ls.old", dir, bins[i]);
        if (ns <= 0 || ns >= MAX_PATH || nb <= 0 || nb >= MAX_PATH) continue;
        if (!is_not_reparse_point(src) || !is_not_reparse_point(bak)) continue;
        DeleteFileW(bak);
        if (file_exists(src) && !DeleteFileW(src)) {
            MoveFileExW(src, bak, MOVEFILE_REPLACE_EXISTING);
            DeleteFileW(bak);
        }
    }
}

static void cleanup_old_backups(const wchar_t *dir) {
    const wchar_t *baks[4] = {
        L"spectra.exe.old",
        L"spectra-shell.exe.old",
        L"spectra_py.pyd.old",
        L"WebView2Loader.dll.old"
    };
    for (int i = 0; i < 4; i++) {
        wchar_t bak[MAX_PATH];
        swprintf(bak, MAX_PATH, L"%ls\\%ls", dir, baks[i]);
        if (file_exists(bak)) {
            if (!DeleteFileW(bak)) {
                MoveFileExW(bak, NULL, MOVEFILE_DELAY_UNTIL_REBOOT);
            }
        }
    }
}

static void safe_delete_regular_file(const wchar_t *path) {
    DWORD attrs = GetFileAttributesW(path);
    if (attrs == INVALID_FILE_ATTRIBUTES) return;
    if ((attrs & FILE_ATTRIBUTE_DIRECTORY) || (attrs & FILE_ATTRIBUTE_REPARSE_POINT)) return;
    if (attrs & FILE_ATTRIBUTE_READONLY) {
        SetFileAttributesW(path, attrs & ~FILE_ATTRIBUTE_READONLY);
    }
    DeleteFileW(path);
}

static void safe_delete_flat_dir(const wchar_t *dir_path) {
    DWORD attrs = GetFileAttributesW(dir_path);
    if (attrs == INVALID_FILE_ATTRIBUTES) return;
    if (!(attrs & FILE_ATTRIBUTE_DIRECTORY) || (attrs & FILE_ATTRIBUTE_REPARSE_POINT)) return;

    wchar_t pattern[MAX_PATH * 2];
    int pn = swprintf(pattern, MAX_PATH * 2, L"%ls\\*", dir_path);
    if (pn <= 0 || pn >= MAX_PATH * 2) return;

    WIN32_FIND_DATAW fd;
    HANDLE hFind = FindFirstFileW(pattern, &fd);
    if (hFind != INVALID_HANDLE_VALUE) {
        do {
            if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0) continue;
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
                continue;
            }
            wchar_t child[MAX_PATH * 2];
            int cn = swprintf(child, MAX_PATH * 2, L"%ls\\%ls", dir_path, fd.cFileName);
            if (cn > 0 && cn < MAX_PATH * 2) {
                safe_delete_regular_file(child);
            }
        } while (FindNextFileW(hFind, &fd));
        FindClose(hFind);
    }
    RemoveDirectoryW(dir_path);
}

static void cleanup_obsolete_install_files(const wchar_t *dir) {
    static const wchar_t *retired_files[] = {
        L"wrat_engine.py",
        L"CHANGELOG_CS.pdf",
        L"web\\public\\favicon.ico",
        L"web\\public\\icon.png",
        L"web\\public\\logo.svg",
        L"docs\\brand\\spectra_logo.svg"
    };
    size_t count = sizeof(retired_files) / sizeof(retired_files[0]);
    for (size_t i = 0; i < count; i++) {
        wchar_t target[MAX_PATH * 2];
        int n = swprintf(target, MAX_PATH * 2, L"%ls\\%ls", dir, retired_files[i]);
        if (n > 0 && n < MAX_PATH * 2) {
            safe_delete_regular_file(target);
        }
    }

    /* Remove now-empty web\public directory (RemoveDirectoryW only succeeds if empty) */
    wchar_t web_public[MAX_PATH * 2];
    int wn = swprintf(web_public, MAX_PATH * 2, L"%ls\\web\\public", dir);
    if (wn > 0 && wn < MAX_PATH * 2) {
        DWORD attrs = GetFileAttributesW(web_public);
        if (attrs != INVALID_FILE_ATTRIBUTES &&
            (attrs & FILE_ATTRIBUTE_DIRECTORY) &&
            !(attrs & FILE_ATTRIBUTE_REPARSE_POINT)) {
            RemoveDirectoryW(web_public);
        }
    }

    /* Prune legacy root-level test_*.py scripts (tests were consolidated into tests/) */
    wchar_t test_pat[MAX_PATH * 2];
    int tn = swprintf(test_pat, MAX_PATH * 2, L"%ls\\test_*.py", dir);
    if (tn > 0 && tn < MAX_PATH * 2) {
        WIN32_FIND_DATAW fd;
        HANDLE hFind = FindFirstFileW(test_pat, &fd);
        if (hFind != INVALID_HANDLE_VALUE) {
            do {
                if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
                    continue;
                }
                wchar_t fpath[MAX_PATH * 2];
                int fn = swprintf(fpath, MAX_PATH * 2, L"%ls\\%ls", dir, fd.cFileName);
                if (fn > 0 && fn < MAX_PATH * 2) {
                    safe_delete_regular_file(fpath);
                }
            } while (FindNextFileW(hFind, &fd));
            FindClose(hFind);
        }
    }

    /* Prune stale compiled bytecode for retired wrat_engine shim */
    wchar_t pyc_pat[MAX_PATH * 2];
    int cn = swprintf(pyc_pat, MAX_PATH * 2, L"%ls\\__pycache__\\wrat_engine.*.pyc", dir);
    if (cn > 0 && cn < MAX_PATH * 2) {
        WIN32_FIND_DATAW fd;
        HANDLE hFind = FindFirstFileW(pyc_pat, &fd);
        if (hFind != INVALID_HANDLE_VALUE) {
            do {
                if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) || (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT)) {
                    continue;
                }
                wchar_t fpath[MAX_PATH * 2];
                int fn = swprintf(fpath, MAX_PATH * 2, L"%ls\\__pycache__\\%ls", dir, fd.cFileName);
                if (fn > 0 && fn < MAX_PATH * 2) {
                    safe_delete_regular_file(fpath);
                }
            } while (FindNextFileW(hFind, &fd));
            FindClose(hFind);
        }
    }

    log_updater(L"Pruned obsolete app files in %ls", dir);
}

static BOOL extract_payload_to_single_dir(const wchar_t *target_dir, const void *pData, DWORD size) {
    /* Stage old web\dist\assets aside so stale hashed JS/CSS bundles do not accumulate */
    wchar_t assets_dir[MAX_PATH * 2];
    wchar_t assets_old[MAX_PATH * 2];
    BOOL assets_staged = FALSE;
    int an = swprintf(assets_dir, MAX_PATH * 2, L"%ls\\web\\dist\\assets", target_dir);
    int bn = swprintf(assets_old, MAX_PATH * 2, L"%ls\\web\\dist\\assets.old", target_dir);
    if (an > 0 && an < MAX_PATH * 2 && bn > 0 && bn < MAX_PATH * 2) {
        safe_delete_flat_dir(assets_old);
        DWORD a_attrs = GetFileAttributesW(assets_dir);
        if (a_attrs != INVALID_FILE_ATTRIBUTES &&
            (a_attrs & FILE_ATTRIBUTE_DIRECTORY) &&
            !(a_attrs & FILE_ATTRIBUTE_REPARSE_POINT)) {
            if (MoveFileExW(assets_dir, assets_old, MOVEFILE_REPLACE_EXISTING)) {
                assets_staged = TRUE;
            }
        }
    }

    BOOL extracted = FALSE;
    for (int attempt = 0; attempt < 3 && !extracted; attempt++) {
        if (attempt > 0) {
            log_updater(L"Extraction retry %d in %ls...", attempt, target_dir);
            kill_running_spectra(target_dir);
            Sleep(700);
        }
        clear_locked_binaries(target_dir);
        extracted = extract_zip_from_memory((const unsigned char *)pData, (size_t)size, target_dir);
        log_updater(L"in-memory zip extraction=%d (attempt=%d)", (int)extracted, attempt);
    }

    if (extracted) {
        if (assets_staged) {
            safe_delete_flat_dir(assets_old);
        }
        cleanup_obsolete_install_files(target_dir);
    } else if (assets_staged && !dir_exists(assets_dir)) {
        /* Roll back staged UI assets if all extraction attempts failed */
        MoveFileExW(assets_old, assets_dir, MOVEFILE_REPLACE_EXISTING);
    }

    cleanup_old_backups(target_dir);
    return extracted;
}

static BOOL extract_update_payload(const wchar_t *target_dir) {
    HRSRC hRes = FindResourceW(NULL, MAKEINTRESOURCEW(101), RT_RCDATA);
    if (!hRes) return FALSE;

    HGLOBAL hData = LoadResource(NULL, hRes);
    if (!hData) return FALSE;

    DWORD size = SizeofResource(NULL, hRes);
    void *pData = LockResource(hData);
    if (!pData || size == 0) return FALSE;

    wprintf(L"[*] Applying fast in-place update (%lu bytes)...\n", size);
    log_updater(L"Applying payload (%lu bytes) into %ls", size, target_dir);

    BOOL ok = extract_payload_to_single_dir(target_dir, pData, size);
    if (!ok) return FALSE;

    // Also update sibling build_* subdirectories OR parent SPECTRA folder if present
    wchar_t pattern[MAX_PATH];
    int pn = swprintf(pattern, MAX_PATH, L"%ls\\build_*", target_dir);
    if (pn > 0 && pn < MAX_PATH) {
        WIN32_FIND_DATAW fd;
        HANDLE hFind = FindFirstFileW(pattern, &fd);
        if (hFind != INVALID_HANDLE_VALUE) {
            do {
                if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) &&
                    !(fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) &&
                    wcscmp(fd.cFileName, L".") != 0 && wcscmp(fd.cFileName, L"..") != 0) {
                    wchar_t sub_dir[MAX_PATH];
                    int sn = swprintf(sub_dir, MAX_PATH, L"%ls\\%ls", target_dir, fd.cFileName);
                    if (sn > 0 && sn < MAX_PATH && is_not_reparse_point(sub_dir)) {
                        log_updater(L"Also updating bundled directory: %ls", sub_dir);
                        extract_payload_to_single_dir(sub_dir, pData, size);
                    }
                }
            } while (FindNextFileW(hFind, &fd));
            FindClose(hFind);
        }
    }

    const wchar_t *last_slash = wcsrchr(target_dir, L'\\');
    if (last_slash && _wcsnicmp(last_slash + 1, L"build_", 6) == 0) {
        wchar_t parent_dir[MAX_PATH];
        size_t plen = (size_t)(last_slash - target_dir);
        if (plen > 0 && plen < MAX_PATH) {
            safe_wcopy(parent_dir, plen + 1, target_dir);
            wchar_t parent_marker[MAX_PATH];
            int mn = swprintf(parent_marker, MAX_PATH, L"%ls\\spectra.exe", parent_dir);
            if (mn > 0 && mn < MAX_PATH && is_not_reparse_point(parent_dir) && file_exists(parent_marker)) {
                log_updater(L"Also updating parent installation directory: %ls", parent_dir);
                extract_payload_to_single_dir(parent_dir, pData, size);
            }
        }
    }

    return TRUE;
}

static void update_registry_version(void) {
    HKEY hKey;
    const wchar_t *subKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SPECTRA";
    if (RegOpenKeyExW(HKEY_CURRENT_USER, subKey, 0, KEY_SET_VALUE, &hKey) == ERROR_SUCCESS) {
        const wchar_t *dispVer = L"Build " SPECTRA_BUILD;
        RegSetValueExW(hKey, L"DisplayVersion", 0, REG_SZ, (const BYTE*)dispVer, (DWORD)((wcslen(dispVer) + 1) * sizeof(wchar_t)));
        RegCloseKey(hKey);
    }
}

int wmain(int argc, wchar_t *argv[]) {
    enable_safe_dll_search();
    BOOL silent = FALSE;
    BOOL force_relaunch = FALSE;
    wchar_t custom_dir[MAX_PATH] = L"";

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"/S") == 0 || wcscmp(argv[i], L"--silent") == 0) {
            silent = TRUE;
        } else if (wcscmp(argv[i], L"/R") == 0 || wcscmp(argv[i], L"--relaunch") == 0) {
            force_relaunch = TRUE;
        } else if (wcsncmp(argv[i], L"/D=", 3) == 0) {
            strip_dir_arg(argv[i] + 3, custom_dir, MAX_PATH);
        } else if (wcsncmp(argv[i], L"--dir=", 6) == 0) {
            strip_dir_arg(argv[i] + 6, custom_dir, MAX_PATH);
        } else if (wcscmp(argv[i], L"-v") == 0 || wcscmp(argv[i], L"--version") == 0) {
            wprintf(L"SPECTRA Updater %hs [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
            return 0;
        } else if (wcscmp(argv[i], L"-h") == 0 || wcscmp(argv[i], L"--help") == 0) {
            print_banner();
            wprintf(L"\nUsage: spectra_update.exe [/S] [/D=PATH]\n\n");
            wprintf(L"Options:\n");
            wprintf(L"  /S, --silent          Run unattended silent update\n");
            wprintf(L"  /D=PATH, --dir=PATH   Target custom installation folder\n");
            wprintf(L"  --version, -v         Display updater build number\n");
            wprintf(L"  --help, -h            Show this help dialog\n");
            return 0;
        }
    }

    if (!silent) {
        print_banner();
    }

    wchar_t target_dir[MAX_PATH];
    if (custom_dir[0] != L'\0') {
        safe_wcopy(target_dir, MAX_PATH, custom_dir);
    } else {
        if (!find_install_dir(target_dir, MAX_PATH)) {
            wprintf(L"[-] ERROR: SPECTRA installation could not be located.\n");
            wprintf(L"    Please run the full installer (spectra_setup.exe) or specify --dir=<PATH>\n");
            if (!silent) {
                MessageBoxW(NULL, L"Existing SPECTRA installation was not found.\nPlease run full setup installer.", L"SPECTRA Updater", MB_ICONWARNING | MB_OK);
            }
            return 1;
        }
    }

    if (!is_safe_install_path(target_dir)) {
        log_updater(L"Rejected unsafe target directory: %ls", target_dir);
        wprintf(L"[-] ERROR: Target directory contains unsafe characters.\n");
        return 1;
    }

    wprintf(L"[*] Target Installation Directory: %ls\n", target_dir);
    log_updater(L"Updater started (silent=%d, force_relaunch=%d, target_dir=%ls)", silent, force_relaunch, target_dir);

    if (force_relaunch) {
        Sleep(800);
    }

    // 1. Terminate running SPECTRA instances (without killing updater itself)
    kill_running_spectra(target_dir);

    // 2. Extract update payload in-place
    if (!extract_update_payload(target_dir)) {
        log_updater(L"ERROR: In-place update extraction failed for %ls", target_dir);
        wprintf(L"[-] ERROR: In-place update extraction failed.\n");
        if (!silent || force_relaunch) {
            MessageBoxW(
                NULL,
                L"Update failed: could not overwrite application files.\nSee %TEMP%\\spectra_update.log for details.",
                L"SPECTRA Updater Error",
                MB_ICONERROR | MB_OK
            );
        }
        return 1;
    }

    // 3. Update Registry version metadata
    update_registry_version();

    log_updater(L"Successfully updated %ls to %hs", target_dir, SPECTRA_VERSION);
    wprintf(L"[✓] SPECTRA successfully updated to %hs!\n", SPECTRA_VERSION);

    // 4. Restart SPECTRA if interactive or explicitly requested via --relaunch
    if (!silent || force_relaunch) {
        wchar_t target_exe[MAX_PATH];
        swprintf(target_exe, MAX_PATH, L"%ls\\spectra.exe", target_dir);
        wprintf(L"[*] Restarting SPECTRA...\n");
        log_updater(L"Relaunching %ls", target_exe);

        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_SHOWNORMAL;
        ZeroMemory(&pi, sizeof(pi));

        wchar_t launch_cmd[MAX_PATH + 8];
        swprintf(launch_cmd, MAX_PATH + 8, L"\"%ls\"", target_exe);
        if (CreateProcessW(target_exe, launch_cmd, NULL, NULL, FALSE, CREATE_NEW_PROCESS_GROUP, NULL, target_dir, &si, &pi)) {
            log_updater(L"Relaunched spectra.exe cleanly (pid=%lu)", pi.dwProcessId);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
        } else {
            DWORD cp_err = GetLastError();
            log_updater(L"CreateProcessW failed (err=%lu), falling back to ShellExecuteW", cp_err);
            ShellExecuteW(NULL, L"open", target_exe, NULL, target_dir, SW_SHOW);
            Sleep(1500);
        }
    }

    return 0;
}
