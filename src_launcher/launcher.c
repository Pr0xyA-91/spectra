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

#define SPECTRA_VERSION      "0.6.0-alpha"
#define SPECTRA_BUILD        "20261030.1515"
#define SPECTRA_EDITION      "Windows Edition"

static void print_banner(void) {
    wprintf(L"==============================================================================\n");
    wprintf(L"  SPECTRA (v%hs, build %hs) [%hs]\n", SPECTRA_VERSION, SPECTRA_BUILD, SPECTRA_EDITION);
    wprintf(L"  Universal Hardware Telemetry & Logic Board Diagnostics\n");
    wprintf(L"==============================================================================\n");
}

static BOOL file_exists(const wchar_t *path) {
    DWORD attr = GetFileAttributesW(path);
    return (attr != INVALID_FILE_ATTRIBUTES && !(attr & FILE_ATTRIBUTE_DIRECTORY));
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

    // 2. Search in system PATH for python.exe, py.exe, pythonw.exe
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

    // 3. Check common LocalAppData Python installations (e.g. %LOCALAPPDATA%\Programs\Python\Python3*\python.exe)
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
            wprintf(L"SPECTRA v%hs (build %hs) [%hs]\n", SPECTRA_VERSION, SPECTRA_BUILD, SPECTRA_EDITION);
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

    // Get executable directory
    wchar_t app_path[MAX_PATH];
    GetModuleFileNameW(NULL, app_path, MAX_PATH);
    wchar_t *last_slash = wcsrchr(app_path, L'\\');
    if (last_slash) *last_slash = L'\0';

    // Locate Python
    wchar_t python_exe[MAX_PATH];
    if (!find_python(python_exe, MAX_PATH, app_path)) {
        print_banner();
        wprintf(L"\n[!] ERROR: Python 3.10+ runtime was not found.\n");
        wprintf(L"    SPECTRA requires Python 3.10+ and pyserial to communicate with\n");
        wprintf(L"    FTDI optical transceivers and COM serial ports.\n\n");
        wprintf(L"    Please install Python from: https://www.python.org/downloads/windows/\n");
        wprintf(L"    (Ensure 'Add Python to PATH' is checked during installation)\n\n");

        int resp = MessageBoxW(
            NULL,
            L"SPECTRA requires Python 3.10+ to interface with physical COM serial ports.\n\n"
            L"Python was not detected in PATH or standard installation folders.\n\n"
            L"Would you like to open the official Python download page now?",
            L"SPECTRA — Python Runtime Required",
            MB_ICONWARNING | MB_YESNO | MB_DEFBUTTON1
        );
        if (resp == IDYES) {
            ShellExecuteW(NULL, L"open", L"https://www.python.org/downloads/windows/", NULL, NULL, SW_SHOWNORMAL);
        }
        return 1;
    }

    // Check target script
    wchar_t script_path[MAX_PATH];
    swprintf(script_path, MAX_PATH, L"%ls\\spectra_app.py", app_path);
    if (!file_exists(script_path)) {
        swprintf(script_path, MAX_PATH, L"%ls\\web_server.py", app_path);
    }

    // Construct command line
    wchar_t cmd_line[32768];
    int offset = swprintf(cmd_line, 32768, L"\"%ls\" \"%ls\"", python_exe, script_path);

    // Pass all arguments through
    for (int i = 1; i < argc; i++) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" \"%ls\"", argv[i]);
    }

    // If double-clicked with no arguments, or explicit --web, ensure --open is passed
    if (argc <= 1) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" --open");
    }

    // Print banner and launch status
    print_banner();
    wprintf(L"[*] Python Runtime : %ls\n", python_exe);
    wprintf(L"[*] Working Dir    : %ls\n", app_path);
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
        app_path,
        &si,
        &pi
    );

    if (!success) {
        DWORD err = GetLastError();
        wprintf(L"[-] Failed to launch SPECTRA process. Error code: %lu\n", err);
        return (int)err;
    }

    // Wait for process to exit and return exit code
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    return (int)exit_code;
}
