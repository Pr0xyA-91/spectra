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
    wprintf(L"  SPECTRA (%hs) [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
    wprintf(L"  Universal Hardware Telemetry & Logic Board Diagnostics\n");
    wprintf(L"==============================================================================\n");
}

static void pause_exit(DWORD code) {
    if (code != 0) {
        wprintf(L"\n[!] SPECTRA exited with status code: %lu\n", code);
    }
    wprintf(L"[*] Press any key to close this window...\n");
    _getch();
}

static BOOL file_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY));
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

    wprintf(L"[*] Extracting standalone SPECTRA runtime (first run initialization)...\n");
    HANDLE hFile = CreateFileW(zip_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        wprintf(L"[-] Failed to write temporary bundle to %ls (Error: %lu)\n", zip_path, GetLastError());
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
            WaitForSingleObject(pi.hProcess, 60000);
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

static BOOL find_python(wchar_t *out_path, size_t max_len, const wchar_t *app_dir) {
    wchar_t candidate[MAX_PATH];

    // 1. Check portable Python in application directory
    swprintf(candidate, MAX_PATH, L"%ls\\python.exe", app_dir);
    if (file_exists(candidate)) {
        wcsncpy(out_path, candidate, max_len);
        return TRUE;
    }
    swprintf(candidate, MAX_PATH, L"%ls\\python\\python.exe", app_dir);
    if (file_exists(candidate)) {
        wcsncpy(out_path, candidate, max_len);
        return TRUE;
    }

    // 2. Search in system PATH for python.exe, py.exe, python3.exe
    if (SearchPathW(NULL, L"python.exe", NULL, MAX_PATH, candidate, NULL) > 0) {
        wcsncpy(out_path, candidate, max_len);
        return TRUE;
    }
    if (SearchPathW(NULL, L"py.exe", NULL, MAX_PATH, candidate, NULL) > 0) {
        wcsncpy(out_path, candidate, max_len);
        return TRUE;
    }
    if (SearchPathW(NULL, L"python3.exe", NULL, MAX_PATH, candidate, NULL) > 0) {
        wcsncpy(out_path, candidate, max_len);
        return TRUE;
    }

    // 3. Check common LocalAppData Python installations
    wchar_t local_app_data[MAX_PATH];
    if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH) > 0) {
        const wchar_t *subdirs[] = {
            L"Python313", L"Python312", L"Python311", L"Python310"
        };
        for (int i = 0; i < 4; i++) {
            swprintf(candidate, MAX_PATH, L"%ls\\Programs\\Python\\%ls\\python.exe", local_app_data, subdirs[i]);
            if (file_exists(candidate)) {
                wcsncpy(out_path, candidate, max_len);
                return TRUE;
            }
        }
    }

    // 4. Check standard Program Files / System Drive (C:\Python3*)
    const wchar_t *std_paths[] = {
        L"C:\\Python313\\python.exe",
        L"C:\\Python312\\python.exe",
        L"C:\\Python311\\python.exe",
        L"C:\\Python310\\python.exe",
    };
    for (int i = 0; i < 4; i++) {
        if (file_exists(std_paths[i])) {
            wcsncpy(out_path, std_paths[i], max_len);
            return TRUE;
        }
    }

    return FALSE;
}

int wmain(int argc, wchar_t *argv[]) {
    // Quick CLI flags
    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"-v") == 0 || wcscmp(argv[i], L"--version") == 0) {
            wprintf(L"SPECTRA %hs [%hs]\n", SPECTRA_VERSION, SPECTRA_EDITION);
            return 0;
        }
        if (wcscmp(argv[i], L"-h") == 0 || wcscmp(argv[i], L"--help") == 0) {
            print_banner();
            wprintf(L"\nUsage: spectra.exe [OPTIONS]\n\n");
            wprintf(L"Options:\n");
            wprintf(L"  (no args)             Launch Next-Gen Web Dashboard on http://127.0.0.1:8080\n");
            wprintf(L"  --web                 Explicitly launch Web Dashboard and open browser\n");
            wprintf(L"  --cli                 Launch interactive text terminal diagnostic console\n");
            wprintf(L"  --port <COMx>         Specify hardware serial port (e.g. COM3)\n");
            wprintf(L"  --demo                Run in simulated hardware demonstration mode\n");
            wprintf(L"  --sensors             Poll live sensor registers and telemetry\n");
            wprintf(L"  --version, -v         Display version and build identifier\n");
            wprintf(L"  --help, -h            Show this help message\n");
            return 0;
        }
    }

    // Determine executable directory
    wchar_t exe_dir[MAX_PATH];
    GetModuleFileNameW(NULL, exe_dir, MAX_PATH);
    wchar_t *last_slash = wcsrchr(exe_dir, L'\\');
    if (last_slash) *last_slash = L'\0';

    wchar_t app_dir[MAX_PATH];
    wcsncpy(app_dir, exe_dir, MAX_PATH);

    // 1. Check if spectra_app.py exists adjacent, in parent directory (bin/), or grand-parent
    wchar_t candidate_script[MAX_PATH];
    BOOL found_local = FALSE;

    // Check adjacent
    swprintf(candidate_script, MAX_PATH, L"%ls\\spectra_app.py", app_dir);
    if (file_exists(candidate_script)) {
        found_local = TRUE;
    } else {
        // Check parent directory (e.g. if running inside bin\ or dist\)
        swprintf(candidate_script, MAX_PATH, L"%ls\\..\\spectra_app.py", app_dir);
        if (file_exists(candidate_script)) {
            wchar_t full_parent[MAX_PATH];
            GetFullPathNameW(candidate_script, MAX_PATH, full_parent, NULL);
            wchar_t *slash = wcsrchr(full_parent, L'\\');
            if (slash) *slash = L'\0';
            wcsncpy(app_dir, full_parent, MAX_PATH);
            found_local = TRUE;
        }
    }

    wchar_t python_exe[MAX_PATH];
    python_exe[0] = L'\0';

    // 2. If not found locally, check or extract embedded standalone bundle
    if (!found_local) {
        wchar_t local_app_data[MAX_PATH];
        if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app_data, MAX_PATH) > 0) {
            wchar_t bundle_dir[MAX_PATH];
            swprintf(bundle_dir, MAX_PATH, L"%ls\\Programs\\SPECTRA\\build_%hs", local_app_data, SPECTRA_BUILD);

            wchar_t bundled_script[MAX_PATH];
            swprintf(bundled_script, MAX_PATH, L"%ls\\spectra_app.py", bundle_dir);
            wchar_t bundled_python[MAX_PATH];
            swprintf(bundled_python, MAX_PATH, L"%ls\\python.exe", bundle_dir);

            if (!file_exists(bundled_script) || !file_exists(bundled_python)) {
                if (extract_embedded_payload(bundle_dir)) {
                    wcsncpy(app_dir, bundle_dir, MAX_PATH);
                    wcsncpy(python_exe, bundled_python, MAX_PATH);
                    found_local = TRUE;
                }
            } else {
                wcsncpy(app_dir, bundle_dir, MAX_PATH);
                wcsncpy(python_exe, bundled_python, MAX_PATH);
                found_local = TRUE;
            }
        }
    }

    // 3. Locate Python runtime if not already bound
    if (python_exe[0] == L'\0') {
        if (!find_python(python_exe, MAX_PATH, app_dir)) {
            print_banner();
            wprintf(L"\n[!] ERROR: Python 3.10+ runtime was not found.\n");
            wprintf(L"    SPECTRA requires Python 3.10+ and pyserial to communicate with\n");
            wprintf(L"    FTDI optical transceivers and COM serial ports.\n\n");
            wprintf(L"    Please install Python from: https://www.python.org/downloads/windows/\n");
            wprintf(L"    (Ensure 'Add Python to PATH' is checked during installation)\n\n");

            MessageBoxW(
                NULL,
                L"SPECTRA requires Python 3.10+ to interface with physical COM serial ports.\n\n"
                L"Python was not detected in PATH or standard installation folders.\n\n"
                L"Please install Python from python.org with 'Add Python to PATH' enabled.",
                L"SPECTRA — Python Runtime Required",
                MB_ICONWARNING | MB_OK
            );
            pause_exit(1);
            return 1;
        }
    }

    // 4. Resolve target script
    wchar_t script_path[MAX_PATH];
    swprintf(script_path, MAX_PATH, L"%ls\\spectra_app.py", app_dir);
    if (!file_exists(script_path)) {
        swprintf(script_path, MAX_PATH, L"%ls\\web_server.py", app_dir);
    }

    if (!file_exists(script_path)) {
        print_banner();
        wprintf(L"\n[!] ERROR: SPECTRA application files were not found in:\n");
        wprintf(L"    %ls\n\n", app_dir);
        MessageBoxW(
            NULL,
            L"Unable to find spectra_app.py or web_server.py.\n"
            L"Please verify application files are intact.",
            L"SPECTRA — Launch Error",
            MB_ICONERROR | MB_OK
        );
        pause_exit(1);
        return 1;
    }

    // 5. Construct command line
    wchar_t cmd_line[32768];
    int offset = swprintf(cmd_line, 32768, L"\"%ls\" \"%ls\"", python_exe, script_path);

    // Pass all arguments through
    for (int i = 1; i < argc; i++) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" \"%ls\"", argv[i]);
    }

    // Default: open browser dashboard if no arguments passed
    if (argc <= 1) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" --open");
    }

    // Print banner and launch status
    print_banner();
    wprintf(L"[*] Python Runtime : %ls\n", python_exe);
    wprintf(L"[*] Working Dir    : %ls\n", app_dir);
    wprintf(L"[*] Starting SPECTRA Telemetry Engine...\n");
    wprintf(L"==============================================================================\n");

    // Launch child process
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));

    BOOL success = CreateProcessW(
        NULL,
        cmd_line,
        NULL,
        NULL,
        TRUE,
        0,
        NULL,
        app_dir,
        &si,
        &pi
    );

    if (!success) {
        DWORD err = GetLastError();
        wprintf(L"[-] Failed to launch SPECTRA process. Error code: %lu\n", err);
        pause_exit(err);
        return (int)err;
    }

    // Wait for process to exit
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    if (exit_code != 0) {
        pause_exit(exit_code);
    }

    return (int)exit_code;
}
