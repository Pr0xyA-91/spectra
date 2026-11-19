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

#define SPECTRA_BUILD        "20261119.1125"
#define SPECTRA_VERSION      "Build 20261119.1125"
#define SPECTRA_EDITION      "Windows Standalone Multi-Manufacturer"

static void log_updater(const wchar_t *fmt, ...) {
    wchar_t temp_dir[MAX_PATH];
    if (GetTempPathW(MAX_PATH, temp_dir) == 0) return;
    wchar_t log_path[MAX_PATH];
    swprintf(log_path, MAX_PATH, L"%ls\\spectra_update.log", temp_dir);

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

static BOOL contains_ci_w(const wchar_t *hay, const wchar_t *needle) {
    if (!hay || !needle || !needle[0]) return FALSE;
    size_t nlen = wcslen(needle);
    for (const wchar_t *p = hay; *p; p++) {
        if (_wcsnicmp(p, needle, nlen) == 0) {
            return TRUE;
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
    wcsncpy(out, raw, max_len - 1);
    out[max_len - 1] = L'\0';
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
    return (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY));
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
                if (!hProc && is_spectra_bin) {
                    hProc = OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, FALSE, pe.th32ProcessID);
                }
                if (!hProc) {
                    continue;
                }

                BOOL should_kill = is_spectra_bin;
                if (is_helper_bin) {
                    wchar_t img_path[MAX_PATH * 2];
                    DWORD img_len = (DWORD)(sizeof(img_path) / sizeof(wchar_t));
                    if (QueryFullProcessImageNameW(hProc, 0, img_path, &img_len)) {
                        if ((target_dir && target_dir[0] && contains_ci_w(img_path, target_dir)) ||
                            contains_ci_w(img_path, L"\\SPECTRA\\")) {
                            should_kill = TRUE;
                        }
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
        wchar_t regPath[MAX_PATH];
        DWORD size = sizeof(regPath);
        DWORD type = REG_SZ;
        if (RegQueryValueExW(hKey, L"InstallLocation", NULL, &type, (LPBYTE)regPath, &size) == ERROR_SUCCESS) {
            RegCloseKey(hKey);
            if (dir_exists(regPath)) {
                wcsncpy(out_dir, regPath, max_len);
                return TRUE;
            }
        }
        RegCloseKey(hKey);
    }

    // 2. Check default %LOCALAPPDATA%\Programs\SPECTRA
    wchar_t local_app_data[MAX_PATH];
    if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH) > 0) {
        wchar_t candidate[MAX_PATH];
        swprintf(candidate, MAX_PATH, L"%ls\\Programs\\SPECTRA", local_app_data);
        if (dir_exists(candidate)) {
            wchar_t build_sub[MAX_PATH];
            swprintf(build_sub, MAX_PATH, L"%ls\\build_%hs", candidate, SPECTRA_BUILD);
            if (dir_exists(build_sub)) {
                wcsncpy(out_dir, build_sub, max_len);
                return TRUE;
            }
            wcsncpy(out_dir, candidate, max_len);
            return TRUE;
        }
    }

    // 3. Check executable directory (if updater is placed adjacent to SPECTRA files)
    wchar_t exe_dir[MAX_PATH];
    GetModuleFileNameW(NULL, exe_dir, MAX_PATH);
    wchar_t *last_slash = wcsrchr(exe_dir, L'\\');
    if (last_slash) *last_slash = L'\0';

    wchar_t test_file[MAX_PATH];
    swprintf(test_file, MAX_PATH, L"%ls\\spectra_app.py", exe_dir);
    if (GetFileAttributesW(test_file) != INVALID_FILE_ATTRIBUTES) {
        wcsncpy(out_dir, exe_dir, max_len);
        return TRUE;
    }
    swprintf(test_file, MAX_PATH, L"%ls\\spectra.exe", exe_dir);
    if (GetFileAttributesW(test_file) != INVALID_FILE_ATTRIBUTES) {
        wcsncpy(out_dir, exe_dir, max_len);
        return TRUE;
    }
    swprintf(test_file, MAX_PATH, L"%ls\\profiles_data.json", exe_dir);
    if (GetFileAttributesW(test_file) != INVALID_FILE_ATTRIBUTES) {
        wcsncpy(out_dir, exe_dir, max_len);
        return TRUE;
    }

    // 4. Check current working directory
    wchar_t cur_dir[MAX_PATH];
    GetCurrentDirectoryW(MAX_PATH, cur_dir);
    swprintf(test_file, MAX_PATH, L"%ls\\profiles_data.json", cur_dir);
    if (GetFileAttributesW(test_file) != INVALID_FILE_ATTRIBUTES) {
        wcsncpy(out_dir, cur_dir, max_len);
        return TRUE;
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
        swprintf(src, MAX_PATH, L"%ls\\%ls", dir, bins[i]);
        swprintf(bak, MAX_PATH, L"%ls\\%ls.old", dir, bins[i]);
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

static BOOL extract_payload_to_single_dir(const wchar_t *target_dir, const void *pData, DWORD size) {
    wchar_t zip_path[MAX_PATH];
    swprintf(zip_path, MAX_PATH, L"%ls\\update.zip", target_dir);

    HANDLE hFile = CreateFileW(zip_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        log_updater(L"Failed to create %ls (err=%lu)", zip_path, GetLastError());
        wprintf(L"[-] Failed to write update package to %ls (Error: %lu)\n", zip_path, GetLastError());
        return FALSE;
    }

    DWORD written = 0;
    WriteFile(hFile, pData, size, &written, NULL);
    CloseHandle(hFile);

    BOOL extracted = FALSE;
    for (int attempt = 0; attempt < 3 && !extracted; attempt++) {
        if (attempt > 0) {
            log_updater(L"Extraction retry %d in %ls...", attempt, target_dir);
            kill_running_spectra(target_dir);
            Sleep(700);
        }
        clear_locked_binaries(target_dir);

        // Extraction command via Windows tar.exe (built-in Windows 10/11)
        wchar_t cmd[4096];
        swprintf(cmd, 4096, L"tar.exe -xf \"%ls\" -C \"%ls\"", zip_path, target_dir);

        STARTUPINFOW si;
        PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof(si));
        si.cb = sizeof(si);
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_HIDE;
        ZeroMemory(&pi, sizeof(pi));

        if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, target_dir, &si, &pi)) {
            WaitForSingleObject(pi.hProcess, 30000);
            DWORD code = 1;
            GetExitCodeProcess(pi.hProcess, &code);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            log_updater(L"tar.exe exit=%lu (attempt=%d)", code, attempt);
            if (code == 0) extracted = TRUE;
        } else {
            log_updater(L"CreateProcessW tar.exe failed (err=%lu)", GetLastError());
        }

        // Fallback to PowerShell Expand-Archive (Win7+)
        if (!extracted) {
            swprintf(cmd, 4096, L"powershell.exe -NoProfile -NonInteractive -Command \"Expand-Archive -Path '%ls' -DestinationPath '%ls' -Force\"", zip_path, target_dir);
            ZeroMemory(&si, sizeof(si));
            si.cb = sizeof(si);
            si.dwFlags = STARTF_USESHOWWINDOW;
            si.wShowWindow = SW_HIDE;
            ZeroMemory(&pi, sizeof(pi));
            if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, target_dir, &si, &pi)) {
                WaitForSingleObject(pi.hProcess, 45000);
                DWORD code = 1;
                GetExitCodeProcess(pi.hProcess, &code);
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);
                log_updater(L"Expand-Archive exit=%lu (attempt=%d)", code, attempt);
                if (code == 0) extracted = TRUE;
            }
        }
    }

    DeleteFileW(zip_path);
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
    swprintf(pattern, MAX_PATH, L"%ls\\build_*", target_dir);
    WIN32_FIND_DATAW fd;
    HANDLE hFind = FindFirstFileW(pattern, &fd);
    if (hFind != INVALID_HANDLE_VALUE) {
        do {
            if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && wcscmp(fd.cFileName, L".") != 0 && wcscmp(fd.cFileName, L"..") != 0) {
                wchar_t sub_dir[MAX_PATH];
                swprintf(sub_dir, MAX_PATH, L"%ls\\%ls", target_dir, fd.cFileName);
                log_updater(L"Also updating bundled directory: %ls", sub_dir);
                extract_payload_to_single_dir(sub_dir, pData, size);
            }
        } while (FindNextFileW(hFind, &fd));
        FindClose(hFind);
    }

    const wchar_t *last_slash = wcsrchr(target_dir, L'\\');
    if (last_slash && _wcsnicmp(last_slash + 1, L"build_", 6) == 0) {
        wchar_t parent_dir[MAX_PATH];
        size_t plen = (size_t)(last_slash - target_dir);
        if (plen > 0 && plen < MAX_PATH) {
            wcsncpy(parent_dir, target_dir, plen);
            parent_dir[plen] = L'\0';
            wchar_t parent_marker[MAX_PATH];
            swprintf(parent_marker, MAX_PATH, L"%ls\\spectra.exe", parent_dir);
            if (file_exists(parent_marker)) {
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
        wcsncpy(target_dir, custom_dir, MAX_PATH);
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
