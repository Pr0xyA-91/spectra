#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif

#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <shellapi.h>
#include <shlobj.h>
#include <objbase.h>
#include <conio.h>
#include "win_safe.h"
#include "zip_extract.h"

#define SPECTRA_BUILD        "20261125.1535"
#define SPECTRA_VERSION      "Build 20261125.1535"
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
    safe_wcopy(temp, MAX_PATH, path);
    size_t len = wcslen(temp);
    for (size_t i = 1; i < len; i++) {
        if (temp[i] == L'\\' || temp[i] == L'/') {
            if (i == 2 && temp[1] == L':') {
                temp[i] = L'\\';
                continue;
            }
            temp[i] = L'\0';
            CreateDirectoryW(temp, NULL);
            temp[i] = L'\\';
        }
    }
    CreateDirectoryW(temp, NULL);
}

static BOOL path_matches_install_scope(const wchar_t *img_path, const wchar_t *target_dir) {
    if (!img_path || !img_path[0] || !target_dir || !target_dir[0]) return FALSE;
    size_t tlen = wcslen(target_dir);
    while (tlen > 0 && (target_dir[tlen - 1] == L'\\' || target_dir[tlen - 1] == L'/')) {
        tlen--;
    }
    if (tlen == 0) return FALSE;
    return (_wcsnicmp(img_path, target_dir, tlen) == 0 &&
            (img_path[tlen] == L'\\' || img_path[tlen] == L'/' || img_path[tlen] == L'\0'));
}

static void kill_running_spectra(const wchar_t *target_dir) {
    DWORD my_pid = GetCurrentProcessId();
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return;

    PROCESSENTRY32W pe;
    ZeroMemory(&pe, sizeof(pe));
    pe.dwSize = sizeof(pe);
    if (Process32FirstW(snap, &pe)) {
        do {
            if (pe.th32ProcessID == 0 || pe.th32ProcessID == my_pid) continue;
            if (_wcsicmp(pe.szExeFile, L"spectra-shell.exe") == 0 ||
                _wcsicmp(pe.szExeFile, L"spectra.exe") == 0) {
                HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE | SYNCHRONIZE, FALSE, pe.th32ProcessID);
                if (hProc) {
                    wchar_t img_path[MAX_PATH * 2];
                    DWORD img_len = MAX_PATH * 2;
                    BOOL in_scope = FALSE;
                    if (QueryFullProcessImageNameW(hProc, 0, img_path, &img_len)) {
                        in_scope = path_matches_install_scope(img_path, target_dir);
                    }
                    if (in_scope) {
                        TerminateProcess(hProc, 0);
                        WaitForSingleObject(hProc, 3000);
                    }
                    CloseHandle(hProc);
                }
            }
        } while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
}

static BOOL extract_embedded_payload(const wchar_t *target_dir) {
    HRSRC hRes = FindResourceW(NULL, MAKEINTRESOURCEW(101), RT_RCDATA);
    if (!hRes) return FALSE;

    HGLOBAL hData = LoadResource(NULL, hRes);
    if (!hData) return FALSE;

    DWORD size = SizeofResource(NULL, hRes);
    const unsigned char *pData = (const unsigned char *)LockResource(hData);
    if (!pData || size == 0) return FALSE;

    create_dir_recursive(target_dir);

    wprintf(L"[*] Extracting embedded payload (%lu bytes) directly in-memory...\n", size);
    wprintf(L"[*] Extracting runtime files and diagnostic suite...\n");

    return extract_zip_from_memory(pData, (size_t)size, target_dir);
}

static void create_shortcut(const wchar_t *shortcut_path, const wchar_t *target_exe, const wchar_t *desc) {
    HRESULT hrInit = CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);
    IShellLinkW *psl = NULL;
    HRESULT hr = CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (void **)&psl);
    if (SUCCEEDED(hr) && psl) {
        psl->lpVtbl->SetPath(psl, target_exe);
        psl->lpVtbl->SetDescription(psl, desc);

        wchar_t work_dir[MAX_PATH];
        safe_wcopy(work_dir, MAX_PATH, target_exe);
        wchar_t *slash = wcsrchr(work_dir, L'\\');
        if (slash) {
            *slash = L'\0';
            psl->lpVtbl->SetWorkingDirectory(psl, work_dir);
        }

        IPersistFile *ppf = NULL;
        hr = psl->lpVtbl->QueryInterface(psl, &IID_IPersistFile, (void **)&ppf);
        if (SUCCEEDED(hr) && ppf) {
            ppf->lpVtbl->Save(ppf, shortcut_path, TRUE);
            ppf->lpVtbl->Release(ppf);
        }
        psl->lpVtbl->Release(psl);
    }
    if (SUCCEEDED(hrInit)) {
        CoUninitialize();
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
        int un = swprintf(uninstCmd, MAX_PATH + 64, L"cmd.exe /c \"%ls\\uninstall.bat\"", target_dir);
        if (un < 0 || un >= (MAX_PATH + 64)) {
            RegCloseKey(hKey);
            return;
        }

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
    if (!is_safe_install_path(target_dir)) {
        return;
    }

    wchar_t uninst_path[MAX_PATH];
    int pn = swprintf(uninst_path, MAX_PATH, L"%ls\\uninstall.bat", target_dir);
    if (pn < 0 || pn >= MAX_PATH || !is_not_reparse_point(uninst_path)) {
        return;
    }

    FILE *f = _wfopen(uninst_path, L"w");
    if (f) {
        fwprintf(f, L"@echo off\r\n");
        fwprintf(f, L"setlocal DisableDelayedExpansion\r\n");
        fwprintf(f, L"set \"INST_DIR=%%~dp0\"\r\n");
        fwprintf(f, L"if \"%%INST_DIR:~-1%%\"==\"\\\" set \"INST_DIR=%%INST_DIR:~0,-1%%\"\r\n");
        fwprintf(f, L"echo [*] Uninstalling SPECTRA Hardware Diagnostics...\r\n");
        fwprintf(f, L"\"%%SystemRoot%%\\System32\\taskkill.exe\" /F /IM spectra-shell.exe 2>nul\r\n");
        fwprintf(f, L"\"%%SystemRoot%%\\System32\\taskkill.exe\" /F /IM spectra.exe 2>nul\r\n");
        fwprintf(f, L"\"%%SystemRoot%%\\System32\\reg.exe\" delete \"HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\SPECTRA\" /f 2>nul\r\n");
        fwprintf(f, L"if exist \"%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA\" (\r\n");
        fwprintf(f, L"    del /f /q \"%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA\\*.lnk\" 2>nul\r\n");
        fwprintf(f, L"    rmdir /s /q \"%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA\" 2>nul\r\n");
        fwprintf(f, L")\r\n");
        fwprintf(f, L"if exist \"%%USERPROFILE%%\\Desktop\\SPECTRA.lnk\" del /f /q \"%%USERPROFILE%%\\Desktop\\SPECTRA.lnk\" 2>nul\r\n");
        fwprintf(f, L"echo [OK] Shortcuts and registry entries removed.\r\n");
        fwprintf(f, L"cd /d \"%%TEMP%%\"\r\n");
        fwprintf(f, L"if exist \"%%INST_DIR%%\\spectra.exe\" rmdir /s /q \"%%INST_DIR%%\" 2>nul\r\n");
        fwprintf(f, L"echo [OK] SPECTRA successfully uninstalled.\r\n");
        fwprintf(f, L"pause\r\n");
        fclose(f);
    }
}

int wmain(int argc, wchar_t *argv[]) {
    enable_safe_dll_search();
    BOOL silent = FALSE;
    BOOL no_desktop = FALSE;
    wchar_t custom_dir[MAX_PATH] = L"";

    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"/S") == 0 || wcscmp(argv[i], L"--silent") == 0) {
            silent = TRUE;
        } else if (wcscmp(argv[i], L"--no-desktop") == 0) {
            no_desktop = TRUE;
        } else if (wcsncmp(argv[i], L"/D=", 3) == 0) {
            safe_wcopy(custom_dir, MAX_PATH, argv[i] + 3);
        } else if (wcsncmp(argv[i], L"--dir=", 6) == 0) {
            safe_wcopy(custom_dir, MAX_PATH, argv[i] + 6);
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
        safe_wcopy(target_dir, MAX_PATH, custom_dir);
    } else {
        wchar_t local_app_data[MAX_PATH];
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH) > 0) {
            swprintf(target_dir, MAX_PATH, L"%ls\\Programs\\SPECTRA", local_app_data);
        } else {
            safe_wcopy(target_dir, MAX_PATH, L"C:\\SPECTRA");
        }
    }

    if (!is_safe_install_path(target_dir)) {
        wprintf(L"[-] ERROR: Installation path contains unsafe characters.\n");
        if (!silent) {
            MessageBoxW(NULL, L"Installation path contains disallowed shell/control characters.", L"SPECTRA Setup Error", MB_ICONERROR | MB_OK);
        }
        return 1;
    }

    wprintf(L"[*] Installation Directory: %ls\n", target_dir);

    // 1. Terminate running SPECTRA if upgrading
    kill_running_spectra(target_dir);

    // 2. Extract embedded bundle
    if (!extract_embedded_payload(target_dir)) {
        wprintf(L"[-] ERROR: Failed to extract SPECTRA files.\n");
        if (!silent) {
            MessageBoxW(NULL, L"Installation failed: could not extract application payload.", L"SPECTRA Setup Error", MB_ICONERROR | MB_OK);
        }
        return 1;
    }

    wchar_t target_exe[MAX_PATH];
    if (swprintf(target_exe, MAX_PATH, L"%ls\\spectra.exe", target_dir) < 0) {
        return 1;
    }

    // 3. Write uninstaller script & Register in Add/Remove Programs
    write_uninstaller_batch(target_dir);
    register_in_uninstall(target_dir, target_exe);

    // 4. Create Start Menu shortcut
    wchar_t app_data[MAX_PATH];
    if (GetEnvironmentVariableW(L"APPDATA", app_data, MAX_PATH) > 0) {
        wchar_t start_menu_folder[MAX_PATH];
        if (swprintf(start_menu_folder, MAX_PATH, L"%ls\\Microsoft\\Windows\\Start Menu\\Programs\\SPECTRA", app_data) > 0) {
            create_dir_recursive(start_menu_folder);

            wchar_t start_link[MAX_PATH];
            if (swprintf(start_link, MAX_PATH, L"%ls\\SPECTRA Hardware Diagnostics.lnk", start_menu_folder) > 0) {
                create_shortcut(start_link, target_exe, L"SPECTRA Hardware Telemetry & Logic Board Diagnostics");
            }
        }
    }

    // 5. Create Desktop shortcut
    if (!no_desktop) {
        wchar_t user_profile[MAX_PATH];
        if (GetEnvironmentVariableW(L"USERPROFILE", user_profile, MAX_PATH) > 0) {
            wchar_t desk_link[MAX_PATH];
            if (swprintf(desk_link, MAX_PATH, L"%ls\\Desktop\\SPECTRA.lnk", user_profile) > 0) {
                create_shortcut(desk_link, target_exe, L"SPECTRA Universal Diagnostics");
            }
        }
    }

    wprintf(L"[OK] SPECTRA %hs installed successfully!\n", SPECTRA_VERSION);

    // 6. Launch installed application if interactive
    if (!silent) {
        wprintf(L"[*] Launching SPECTRA...\n");
        ShellExecuteW(NULL, L"open", target_exe, NULL, target_dir, SW_SHOW);
    }

    return 0;
}
