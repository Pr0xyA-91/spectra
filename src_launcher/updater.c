#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <shellapi.h>
#include <conio.h>

#define SPECTRA_BUILD        "20261102.1520"
#define SPECTRA_VERSION      "Build 20261102.1520"
#define SPECTRA_EDITION      "Windows Standalone Multi-Manufacturer"

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

static void kill_running_spectra(void) {
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));

    wchar_t cmd[] = L"taskkill.exe /F /IM spectra.exe /T";
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 5000);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
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
            wcsncpy(out_dir, candidate, max_len);
            return TRUE;
        }
    }

    // 3. Check current working directory
    wchar_t cur_dir[MAX_PATH];
    GetCurrentDirectoryW(MAX_PATH, cur_dir);
    wchar_t test_file[MAX_PATH];
    swprintf(test_file, MAX_PATH, L"%ls\\profiles_data.json", cur_dir);
    if (GetFileAttributesW(test_file) != INVALID_FILE_ATTRIBUTES) {
        wcsncpy(out_dir, cur_dir, max_len);
        return TRUE;
    }

    return FALSE;
}

static BOOL extract_update_payload(const wchar_t *target_dir) {
    HRSRC hRes = FindResourceW(NULL, MAKEINTRESOURCEW(101), RT_RCDATA);
    if (!hRes) return FALSE;

    HGLOBAL hData = LoadResource(NULL, hRes);
    if (!hData) return FALSE;

    DWORD size = SizeofResource(NULL, hRes);
    void *pData = LockResource(hData);
    if (!pData || size == 0) return FALSE;

    wchar_t zip_path[MAX_PATH];
    swprintf(zip_path, MAX_PATH, L"%ls\\update.zip", target_dir);

    wprintf(L"[*] Applying fast in-place update (%lu bytes)...\n", size);
    HANDLE hFile = CreateFileW(zip_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        wprintf(L"[-] Failed to write update package to %ls (Error: %lu)\n", zip_path, GetLastError());
        return FALSE;
    }

    DWORD written = 0;
    WriteFile(hFile, pData, size, &written, NULL);
    CloseHandle(hFile);

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

    BOOL extracted = FALSE;
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, target_dir, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 30000);
        DWORD code = 0;
        GetExitCodeProcess(pi.hProcess, &code);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        if (code == 0) extracted = TRUE;
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
            DWORD code = 0;
            GetExitCodeProcess(pi.hProcess, &code);
            CloseHandle(pi.hProcess);
            CloseHandle(pi.hThread);
            if (code == 0) extracted = TRUE;
        }
    }

    DeleteFileW(zip_path);
    return extracted;
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
    wchar_t custom_dir[MAX_PATH] = L"";

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"/S") == 0 || wcscmp(argv[i], L"--silent") == 0) {
            silent = TRUE;
        } else if (wcsncmp(argv[i], L"/D=", 3) == 0) {
            wcsncpy(custom_dir, argv[i] + 3, MAX_PATH);
        } else if (wcsncmp(argv[i], L"--dir=", 6) == 0) {
            wcsncpy(custom_dir, argv[i] + 6, MAX_PATH);
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

    // 1. Terminate running SPECTRA instance
    kill_running_spectra();

    // 2. Extract update payload in-place
    if (!extract_update_payload(target_dir)) {
        wprintf(L"[-] ERROR: In-place update extraction failed.\n");
        if (!silent) {
            MessageBoxW(NULL, L"Update failed: could not overwrite application files.", L"SPECTRA Updater Error", MB_ICONERROR | MB_OK);
        }
        return 1;
    }

    // 3. Update Registry version metadata
    update_registry_version();

    wprintf(L"[✓] SPECTRA successfully updated to %hs!\n", SPECTRA_VERSION);

    // 4. Restart SPECTRA if interactive
    if (!silent) {
        wchar_t target_exe[MAX_PATH];
        swprintf(target_exe, MAX_PATH, L"%ls\\spectra.exe", target_dir);
        wprintf(L"[*] Restarting SPECTRA...\n");
        ShellExecuteW(NULL, L"open", target_exe, NULL, target_dir, SW_SHOW);
    }

    return 0;
}
