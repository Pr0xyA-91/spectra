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

#define SPECTRA_BUILD        "20261102.1738"
#define SPECTRA_VERSION      "Build 20261102.1738"
#define SPECTRA_EDITION      "Windows Standalone Multi-Manufacturer"

static void print_banner(void) {
    wprintf(L"==============================================================================\n");
    wprintf(L"  SPECTRA Setup — %hs [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
    wprintf(L"  Offline Standalone Installer & Hardware Diagnostics Setup\n");
    wprintf(L"==============================================================================\n");
}

static BOOL dir_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY));
}

static void create_dir_recursive(const wchar_t *path) {
    wchar_t temp[MAX_PATH];
    wcsncpy(temp, path, MAX_PATH);
    size_t len = wcslen(temp);
    for (size_t i = 1; i < len; i++) {
        if (temp[i] == L'\\' || temp[i] == L'/') {
            temp[i] = L'\0';
            CreateDirectoryW(temp, NULL);
            temp[i] = L'\\';
        }
    }
    CreateDirectoryW(temp, NULL);
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

static BOOL extract_embedded_payload(const wchar_t *target_dir) {
    HRSRC hRes = FindResourceW(NULL, MAKEINTRESOURCEW(101), RT_RCDATA);
    if (!hRes) return FALSE;

    HGLOBAL hData = LoadResource(NULL, hRes);
    if (!hData) return FALSE;

    DWORD size = SizeofResource(NULL, hRes);
    void *pData = LockResource(hData);
    if (!pData || size == 0) return FALSE;

    create_dir_recursive(target_dir);

    wchar_t zip_path[MAX_PATH];
    swprintf(zip_path, MAX_PATH, L"%ls\\bundle.zip", target_dir);

    wprintf(L"[*] Writing installation payload (%lu bytes)...\n", size);
    HANDLE hFile = CreateFileW(zip_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        wprintf(L"[-] Failed to write temporary bundle to %ls (Error: %lu)\n", zip_path, GetLastError());
        return FALSE;
    }

    DWORD written = 0;
    WriteFile(hFile, pData, size, &written, NULL);
    CloseHandle(hFile);

    wprintf(L"[*] Extracting runtime files and diagnostic suite...\n");
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
        WaitForSingleObject(pi.hProcess, 60000);
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
            WaitForSingleObject(pi.hProcess, 90000);
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

static void create_shortcut(const wchar_t *shortcut_path, const wchar_t *target_exe, const wchar_t *desc) {
    wchar_t ps_cmd[4096];
    swprintf(ps_cmd, 4096,
        L"powershell.exe -NoProfile -NonInteractive -Command \"$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%ls'); $s.TargetPath = '%ls'; $s.Description = '%ls'; $s.Save()\"",
        shortcut_path, target_exe, desc
    );

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));

    if (CreateProcessW(NULL, ps_cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        WaitForSingleObject(pi.hProcess, 15000);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
}

static void register_in_uninstall(const wchar_t *target_dir, const wchar_t *target_exe) {
    HKEY hKey;
    const wchar_t *subKey = L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SPECTRA";
    if (RegCreateKeyExW(HKEY_CURRENT_USER, subKey, 0, NULL, REG_OPTION_NON_VOLATILE, KEY_WRITE, NULL, &hKey, NULL) == ERROR_SUCCESS) {
        const wchar_t *dispName = L"SPECTRA Universal Hardware Diagnostics";
        const wchar_t *dispVer = L"Build " SPECTRA_BUILD;
        const wchar_t *publisher = L"SPECTRA Contributors";
        wchar_t uninstCmd[MAX_PATH + 64];
        swprintf(uninstCmd, MAX_PATH + 64, L"cmd.exe /c \"%ls\\uninstall.bat\"", target_dir);

        RegSetValueExW(hKey, L"DisplayName", 0, REG_SZ, (const BYTE*)dispName, (DWORD)((wcslen(dispName) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"DisplayVersion", 0, REG_SZ, (const BYTE*)dispVer, (DWORD)((wcslen(dispVer) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"Publisher", 0, REG_SZ, (const BYTE*)publisher, (DWORD)((wcslen(publisher) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"InstallLocation", 0, REG_SZ, (const BYTE*)target_dir, (DWORD)((wcslen(target_dir) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"DisplayIcon", 0, REG_SZ, (const BYTE*)target_exe, (DWORD)((wcslen(target_exe) + 1) * sizeof(wchar_t)));
        RegSetValueExW(hKey, L"UninstallString", 0, REG_SZ, (const BYTE*)uninstCmd, (DWORD)((wcslen(uninstCmd) + 1) * sizeof(wchar_t)));

        DWORD noModify = 1;
        RegSetValueExW(hKey, L"NoModify", 0, REG_DWORD, (const BYTE*)&noModify, sizeof(DWORD));
        RegSetValueExW(hKey, L"NoRepair", 0, REG_DWORD, (const BYTE*)&noModify, sizeof(DWORD));

        RegCloseKey(hKey);
    }
}

static void write_uninstaller_batch(const wchar_t *target_dir) {
    wchar_t uninst_path[MAX_PATH];
    swprintf(uninst_path, MAX_PATH, L"%ls\\uninstall.bat", target_dir);

    FILE *f = _wfopen(uninst_path, L"w");
    if (f) {
        fwprintf(f, L"@echo off\r\n");
        fwprintf(f, L"echo [*] Uninstalling SPECTRA Hardware Diagnostics...\r\n");
        fwprintf(f, L"taskkill /F /IM spectra.exe 2>nul\r\n");
        fwprintf(f, L"reg delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SPECTRA\" /f 2>nul\r\n");
        fwprintf(f, L"powershell -NoProfile -Command \"Remove-Item -Path '$env:APPDATA\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA' -Recurse -Force -ErrorAction SilentlyContinue\"\r\n");
        fwprintf(f, L"powershell -NoProfile -Command \"Remove-Item -Path '$env:USERPROFILE\\Desktop\\SPECTRA.lnk' -Force -ErrorAction SilentlyContinue\"\r\n");
        fwprintf(f, L"echo [✓] Shortcuts and registry entries removed.\r\n");
        fwprintf(f, L"cd /d %%TEMP%%\r\n");
        fwprintf(f, L"rmdir /s /q \"%ls\" 2>nul\r\n", target_dir);
        fwprintf(f, L"echo [✓] SPECTRA successfully uninstalled.\r\n");
        fwprintf(f, L"pause\r\n");
        fclose(f);
    }
}

int wmain(int argc, wchar_t *argv[]) {
    BOOL silent = FALSE;
    BOOL no_desktop = FALSE;
    wchar_t custom_dir[MAX_PATH] = L"";

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"/S") == 0 || wcscmp(argv[i], L"--silent") == 0) {
            silent = TRUE;
        } else if (wcscmp(argv[i], L"--no-desktop") == 0) {
            no_desktop = TRUE;
        } else if (wcsncmp(argv[i], L"/D=", 3) == 0) {
            wcsncpy(custom_dir, argv[i] + 3, MAX_PATH);
        } else if (wcsncmp(argv[i], L"--dir=", 6) == 0) {
            wcsncpy(custom_dir, argv[i] + 6, MAX_PATH);
        } else if (wcscmp(argv[i], L"-v") == 0 || wcscmp(argv[i], L"--version") == 0) {
            wprintf(L"SPECTRA Setup %hs [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
            return 0;
        } else if (wcscmp(argv[i], L"-h") == 0 || wcscmp(argv[i], L"--help") == 0) {
            print_banner();
            wprintf(L"\nUsage: spectra_setup.exe [/S] [/D=PATH] [--no-desktop]\n\n");
            wprintf(L"Options:\n");
            wprintf(L"  /S, --silent          Run unattended silent installation\n");
            wprintf(L"  /D=PATH, --dir=PATH   Install to custom target folder\n");
            wprintf(L"  --no-desktop          Do not create Desktop shortcut\n");
            wprintf(L"  --version, -v         Display installer build number\n");
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
        wchar_t local_app_data[MAX_PATH];
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH) > 0) {
            swprintf(target_dir, MAX_PATH, L"%ls\\Programs\\SPECTRA", local_app_data);
        } else {
            wcsncpy(target_dir, L"C:\\SPECTRA", MAX_PATH);
        }
    }

    wprintf(L"[*] Installation Directory: %ls\n", target_dir);

    // 1. Terminate running SPECTRA if upgrading
    kill_running_spectra();

    // 2. Extract embedded bundle
    if (!extract_embedded_payload(target_dir)) {
        wprintf(L"[-] ERROR: Failed to extract SPECTRA files.\n");
        if (!silent) {
            MessageBoxW(NULL, L"Installation failed: could not extract application payload.", L"SPECTRA Setup Error", MB_ICONERROR | MB_OK);
        }
        return 1;
    }

    wchar_t target_exe[MAX_PATH];
    swprintf(target_exe, MAX_PATH, L"%ls\\spectra.exe", target_dir);

    // 3. Write uninstaller script & Register in Add/Remove Programs
    write_uninstaller_batch(target_dir);
    register_in_uninstall(target_dir, target_exe);

    // 4. Create Start Menu shortcut
    wchar_t app_data[MAX_PATH];
    if (GetEnvironmentVariableW(L"APPDATA", app_data, MAX_PATH) > 0) {
        wchar_t start_menu_folder[MAX_PATH];
        swprintf(start_menu_folder, MAX_PATH, L"%ls\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA", app_data);
        create_dir_recursive(start_menu_folder);

        wchar_t start_link[MAX_PATH];
        swprintf(start_link, MAX_PATH, L"%ls\\SPECTRA Hardware Diagnostics.lnk", start_menu_folder);
        create_shortcut(start_link, target_exe, L"SPECTRA Hardware Telemetry & Logic Board Diagnostics");
    }

    // 5. Create Desktop shortcut
    if (!no_desktop) {
        wchar_t user_profile[MAX_PATH];
        if (GetEnvironmentVariableW(L"USERPROFILE", user_profile, MAX_PATH) > 0) {
            wchar_t desk_link[MAX_PATH];
            swprintf(desk_link, MAX_PATH, L"%ls\\Desktop\\SPECTRA.lnk", user_profile);
            create_shortcut(desk_link, target_exe, L"SPECTRA Universal Diagnostics");
        }
    }

    wprintf(L"[✓] SPECTRA %hs installed successfully!\n", SPECTRA_VERSION);

    // 6. Launch installed application if interactive
    if (!silent) {
        wprintf(L"[*] Launching SPECTRA...\n");
        ShellExecuteW(NULL, L"open", target_exe, NULL, target_dir, SW_SHOW);
    }

    return 0;
}
