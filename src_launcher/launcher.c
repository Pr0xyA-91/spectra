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

#define SPECTRA_BUILD        "20261119.1612"
#define SPECTRA_VERSION      "Build 20261119.1612"
#define SPECTRA_EDITION      "Windows Standalone Multi-Manufacturer"

// ============================================================================
// Splash Window State & GDI Resources
// ============================================================================
static HWND g_hSplash = NULL;
static HANDLE g_hChildProcess = NULL;
static DWORD g_child_pid = 0;
static int g_timer_ticks = 0;
static HICON g_hAppIcon = NULL;
static HFONT g_hFontTitle = NULL;
static HFONT g_hFontSubtitle = NULL;
static HFONT g_hFontVersion = NULL;
static HFONT g_hFontStatus = NULL;
static HBRUSH g_hBrushBg = NULL;
static HBRUSH g_hBrushProgressBg = NULL;
static HBRUSH g_hBrushProgressBar = NULL;
static HPEN g_hPenBorder = NULL;
static const wchar_t *g_status_text = L"Initializing diagnostic engine...";

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

// ============================================================================
// Splash Window Procedure & Main Window Discovery
// ============================================================================
struct FindContext {
    DWORD target_pid;
    HWND found_hwnd;
};

static BOOL CALLBACK EnumWindowsCallback(HWND hwnd, LPARAM lParam) {
    struct FindContext *ctx = (struct FindContext *)lParam;
    if (hwnd == g_hSplash || !IsWindowVisible(hwnd)) {
        return TRUE;
    }
    DWORD pid = 0;
    GetWindowThreadProcessId(hwnd, &pid);
    wchar_t title[256];
    if (GetWindowTextW(hwnd, title, 256) > 0) {
        // Match main window: "SPECTRA — Universal...", "SPECTRA - Universal...", or browser title containing SPECTRA
        if (wcsstr(title, L"SPECTRA") != NULL) {
            ctx->found_hwnd = hwnd;
            return FALSE;
        }
    }
    return TRUE;
}

static LRESULT CALLBACK SplashWndProc(HWND hwnd, UINT uMsg, WPARAM wParam, LPARAM lParam) {
    switch (uMsg) {
        case WM_CREATE: {
            SetTimer(hwnd, 1, 60, NULL);
            return 0;
        }
        case WM_TIMER: {
            g_timer_ticks++;

            // 1. Check if child process terminated early
            if (g_hChildProcess != NULL) {
                DWORD exit_code = 0;
                if (GetExitCodeProcess(g_hChildProcess, &exit_code) && exit_code != STILL_ACTIVE) {
                    DestroyWindow(hwnd);
                    return 0;
                }

                // 2. Check if main application window has appeared
                struct FindContext ctx = { g_child_pid, NULL };
                EnumWindows(EnumWindowsCallback, (LPARAM)&ctx);
                if (ctx.found_hwnd != NULL) {
                    // Small grace period (min ~0.5s) to allow first frame paint
                    if (g_timer_ticks > 8) {
                        DestroyWindow(hwnd);
                        return 0;
                    }
                }
            }

            // 3. Safety timeout: 35 seconds max (580 * 60ms)
            if (g_timer_ticks > 580) {
                DestroyWindow(hwnd);
                return 0;
            }

            // Redraw progress bar
            RECT rcProg = { 40, 240, 420, 248 };
            InvalidateRect(hwnd, &rcProg, FALSE);
            return 0;
        }
        case WM_PAINT: {
            PAINTSTRUCT ps;
            HDC hdc = BeginPaint(hwnd, &ps);
            RECT clientRect;
            GetClientRect(hwnd, &clientRect);
            int w = clientRect.right;
            int h = clientRect.bottom;

            // Fill dark background (#0E0E12)
            FillRect(hdc, &clientRect, g_hBrushBg);

            // Draw cyan border (#06B6D4)
            HGDIOBJ oldPen = SelectObject(hdc, g_hPenBorder);
            HGDIOBJ oldBrush = SelectObject(hdc, GetStockObject(NULL_BRUSH));
            Rectangle(hdc, 0, 0, w, h);
            SelectObject(hdc, oldPen);
            SelectObject(hdc, oldBrush);

            // Draw SPECTRA Prism Logo icon
            if (g_hAppIcon) {
                DrawIconEx(hdc, (w - 48) / 2, 28, g_hAppIcon, 48, 48, 0, NULL, DI_NORMAL);
            }

            SetBkMode(hdc, TRANSPARENT);

            // Title: SPECTRA
            SelectObject(hdc, g_hFontTitle);
            SetTextColor(hdc, RGB(255, 255, 255));
            RECT titleRect = { 0, 88, w, 122 };
            DrawTextW(hdc, L"SPECTRA", -1, &titleRect, DT_CENTER | DT_SINGLELINE | DT_VCENTER);

            // Subtitle
            SelectObject(hdc, g_hFontSubtitle);
            SetTextColor(hdc, RGB(148, 163, 184));
            RECT subRect = { 20, 126, w - 20, 146 };
            DrawTextW(hdc, L"Universal Hardware Telemetry & Logic Diagnostics", -1, &subRect, DT_CENTER | DT_SINGLELINE | DT_VCENTER);

            // Version / Build Badge
            SelectObject(hdc, g_hFontVersion);
            SetTextColor(hdc, RGB(6, 182, 212));
            wchar_t verText[64];
            swprintf(verText, 64, L"%hs", SPECTRA_VERSION);
            RECT verRect = { 0, 150, w, 170 };
            DrawTextW(hdc, verText, -1, &verRect, DT_CENTER | DT_SINGLELINE | DT_VCENTER);

            // Status Text
            SelectObject(hdc, g_hFontStatus);
            SetTextColor(hdc, RGB(100, 116, 139));
            RECT statusRect = { 0, 215, w, 235 };
            DrawTextW(hdc, g_status_text, -1, &statusRect, DT_CENTER | DT_SINGLELINE | DT_VCENTER);

            // Progress Bar Track
            RECT progTrack = { 40, 244, w - 40, 248 };
            FillRect(hdc, &progTrack, g_hBrushProgressBg);

            // Animated Smooth Glowing Progress Bar
            int trackW = (w - 80);
            int barW = 110;
            int offset = (g_timer_ticks * 7) % (trackW + barW) - barW;
            int startX = 40 + offset;
            int endX = startX + barW;
            if (startX < 40) startX = 40;
            if (endX > w - 40) endX = w - 40;
            if (endX > startX) {
                RECT progFill = { startX, 244, endX, 248 };
                FillRect(hdc, &progFill, g_hBrushProgressBar);
            }

            EndPaint(hwnd, &ps);
            return 0;
        }
        case WM_DESTROY: {
            KillTimer(hwnd, 1);
            g_hSplash = NULL;
            PostQuitMessage(0);
            return 0;
        }
        default:
            return DefWindowProcW(hwnd, uMsg, wParam, lParam);
    }
}

static HWND create_splash_window(HINSTANCE hInstance) {
    WNDCLASSEXW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.cbSize = sizeof(WNDCLASSEXW);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = SplashWndProc;
    wc.hInstance = hInstance;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.lpszClassName = L"SPECTRA_SPLASH_CLASS";

    g_hAppIcon = (HICON)LoadImageW(hInstance, MAKEINTRESOURCEW(1), IMAGE_ICON, 48, 48, LR_SHARED);
    if (!g_hAppIcon) {
        g_hAppIcon = (HICON)LoadIconW(hInstance, MAKEINTRESOURCEW(1));
    }
    wc.hIcon = g_hAppIcon;
    wc.hIconSm = g_hAppIcon;

    RegisterClassExW(&wc);

    // GDI objects
    g_hBrushBg = CreateSolidBrush(RGB(14, 14, 18));
    g_hBrushProgressBg = CreateSolidBrush(RGB(30, 30, 40));
    g_hBrushProgressBar = CreateSolidBrush(RGB(6, 182, 212));
    g_hPenBorder = CreatePen(PS_SOLID, 1, RGB(6, 182, 212));

    g_hFontTitle = CreateFontW(32, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    g_hFontSubtitle = CreateFontW(15, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    g_hFontVersion = CreateFontW(14, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    g_hFontStatus = CreateFontW(13, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");

    int screen_w = GetSystemMetrics(SM_CXSCREEN);
    int screen_h = GetSystemMetrics(SM_CYSCREEN);
    int w = 460;
    int h = 280;
    int x = (screen_w - w) / 2;
    int y = (screen_h - h) / 2;

    HWND hwnd = CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_TOOLWINDOW,
        L"SPECTRA_SPLASH_CLASS",
        L"SPECTRA Splash",
        WS_POPUP | WS_VISIBLE,
        x, y, w, h,
        NULL, NULL, hInstance, NULL
    );

    UpdateWindow(hwnd);
    return hwnd;
}

static void cleanup_splash_gdi(void) {
    if (g_hBrushBg) DeleteObject(g_hBrushBg);
    if (g_hBrushProgressBg) DeleteObject(g_hBrushProgressBg);
    if (g_hBrushProgressBar) DeleteObject(g_hBrushProgressBar);
    if (g_hPenBorder) DeleteObject(g_hPenBorder);
    if (g_hFontTitle) DeleteObject(g_hFontTitle);
    if (g_hFontSubtitle) DeleteObject(g_hFontSubtitle);
    if (g_hFontVersion) DeleteObject(g_hFontVersion);
    if (g_hFontStatus) DeleteObject(g_hFontStatus);
}

// ============================================================================
// Payload Extraction (First-Run Standalone Initialization)
// ============================================================================
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

    if (g_hSplash) {
        g_status_text = L"First-run extraction in progress...";
        InvalidateRect(g_hSplash, NULL, FALSE);
        UpdateWindow(g_hSplash);
    } else {
        wprintf(L"[*] Extracting standalone SPECTRA runtime (first run initialization)...\n");
    }

    HANDLE hFile = CreateFileW(zip_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
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

// ============================================================================
// Python Runtime Discovery (Prefers pythonw.exe in GUI mode)
// ============================================================================
static BOOL find_python(wchar_t *out_path, size_t max_len, const wchar_t *app_dir, BOOL prefer_gui) {
    wchar_t candidate[MAX_PATH];

    // 1. Check portable Python in application directory
    if (prefer_gui) {
        swprintf(candidate, MAX_PATH, L"%ls\\pythonw.exe", app_dir);
        if (file_exists(candidate)) {
            wcsncpy(out_path, candidate, max_len);
            return TRUE;
        }
        swprintf(candidate, MAX_PATH, L"%ls\\python\\pythonw.exe", app_dir);
        if (file_exists(candidate)) {
            wcsncpy(out_path, candidate, max_len);
            return TRUE;
        }
    }

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

    // 2. Search in system PATH
    if (prefer_gui) {
        if (SearchPathW(NULL, L"pythonw.exe", NULL, MAX_PATH, candidate, NULL) > 0) {
            wcsncpy(out_path, candidate, max_len);
            return TRUE;
        }
    }
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
            if (prefer_gui) {
                swprintf(candidate, MAX_PATH, L"%ls\\Programs\\Python\\%ls\\pythonw.exe", local_app_data, subdirs[i]);
                if (file_exists(candidate)) {
                    wcsncpy(out_path, candidate, max_len);
                    return TRUE;
                }
            }
            swprintf(candidate, MAX_PATH, L"%ls\\Programs\\Python\\%ls\\python.exe", local_app_data, subdirs[i]);
            if (file_exists(candidate)) {
                wcsncpy(out_path, candidate, max_len);
                return TRUE;
            }
        }
    }

    // 4. Check standard Program Files / System Drive (C:\Python3*)
    const wchar_t *std_paths[] = {
        L"C:\\Python313", L"C:\\Python312", L"C:\\Python311", L"C:\\Python310"
    };
    for (int i = 0; i < 4; i++) {
        if (prefer_gui) {
            swprintf(candidate, MAX_PATH, L"%ls\\pythonw.exe", std_paths[i]);
            if (file_exists(candidate)) {
                wcsncpy(out_path, candidate, max_len);
                return TRUE;
            }
        }
        swprintf(candidate, MAX_PATH, L"%ls\\python.exe", std_paths[i]);
        if (file_exists(candidate)) {
            wcsncpy(out_path, candidate, max_len);
            return TRUE;
        }
    }

    return FALSE;
}

extern HRESULT WINAPI SetCurrentProcessExplicitAppUserModelID(PCWSTR AppID);

// ============================================================================
// Main GUI Entry Point (wWinMain)
// ============================================================================
int WINAPI wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, PWSTR pCmdLine, int nCmdShow) {
    SetCurrentProcessExplicitAppUserModelID(L"SPECTRA.Diagnostics.Suite");
    int argc = 0;
    LPWSTR *argv = CommandLineToArgvW(GetCommandLineW(), &argc);

    // Determine if CLI console mode or browser fallback mode was explicitly requested
    BOOL is_cli_mode = FALSE;
    BOOL is_browser_mode = FALSE;
    for (int i = 1; i < argc; i++) {
        if (wcscmp(argv[i], L"-h") == 0 || wcscmp(argv[i], L"--help") == 0 ||
            wcscmp(argv[i], L"-v") == 0 || wcscmp(argv[i], L"--version") == 0 ||
            wcscmp(argv[i], L"--cli") == 0 || wcscmp(argv[i], L"--sensors") == 0 ||
            wcscmp(argv[i], L"--port") == 0 || wcscmp(argv[i], L"--demo") == 0) {
            is_cli_mode = TRUE;
            break;
        }
        if (wcscmp(argv[i], L"--browser") == 0 || wcscmp(argv[i], L"--web") == 0 ||
            wcscmp(argv[i], L"--legacy-gtk") == 0 || wcscmp(argv[i], L"--gtk") == 0) {
            is_browser_mode = TRUE;
        }
    }

    if (is_cli_mode) {
        if (AttachConsole(ATTACH_PARENT_PROCESS) || AllocConsole()) {
            FILE *fp;
            freopen_s(&fp, "CONOUT$", "w", stdout);
            freopen_s(&fp, "CONOUT$", "w", stderr);
            freopen_s(&fp, "CONIN$", "r", stdin);
        }
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
    } else {
        // Only display GDI splash when spectra-shell.exe is not already installed next to the launcher
        wchar_t exe_dir_check[MAX_PATH], local_shell[MAX_PATH];
        GetModuleFileNameW(NULL, exe_dir_check, MAX_PATH);
        wchar_t *s = wcsrchr(exe_dir_check, L'\\');
        if (s) *s = L'\0';
        swprintf(local_shell, MAX_PATH, L"%ls\\spectra-shell.exe", exe_dir_check);
        if (is_browser_mode || !file_exists(local_shell)) {
            wchar_t appdata_shell[MAX_PATH];
            appdata_shell[0] = L'\0';
            wchar_t local_app[MAX_PATH];
            if (GetEnvironmentVariableW(L"LOCALAPPDATA", local_app, MAX_PATH)) {
                swprintf(appdata_shell, MAX_PATH, L"%ls\\SPECTRA\\app\\spectra-shell.exe", local_app);
            }
            if (is_browser_mode || !appdata_shell[0] || !file_exists(appdata_shell)) {
                g_hSplash = create_splash_window(hInstance);
            }
        }
    }

    // Determine executable directory
    wchar_t exe_dir[MAX_PATH];
    GetModuleFileNameW(NULL, exe_dir, MAX_PATH);
    wchar_t *last_slash = wcsrchr(exe_dir, L'\\');
    if (last_slash) *last_slash = L'\0';

    wchar_t app_dir[MAX_PATH];
    wcsncpy(app_dir, exe_dir, MAX_PATH);

    // 1. Check if spectra_app.py exists adjacent or in parent directory
    wchar_t candidate_script[MAX_PATH];
    BOOL found_local = FALSE;

    swprintf(candidate_script, MAX_PATH, L"%ls\\spectra_app.py", app_dir);
    if (file_exists(candidate_script)) {
        found_local = TRUE;
    } else {
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
            swprintf(bundled_python, MAX_PATH, !is_cli_mode ? L"%ls\\pythonw.exe" : L"%ls\\python.exe", bundle_dir);

            if (!file_exists(bundled_script) || (!file_exists(bundled_python) && !file_exists(candidate_script))) {
                if (extract_embedded_payload(bundle_dir)) {
                    wcsncpy(app_dir, bundle_dir, MAX_PATH);
                    if (file_exists(bundled_python)) {
                        wcsncpy(python_exe, bundled_python, MAX_PATH);
                    }
                    found_local = TRUE;
                }
            } else {
                wcsncpy(app_dir, bundle_dir, MAX_PATH);
                if (file_exists(bundled_python)) {
                    wcsncpy(python_exe, bundled_python, MAX_PATH);
                }
                found_local = TRUE;
            }
        }
    }

    // 3. Locate Python runtime if not already bound
    if (python_exe[0] == L'\0') {
        if (!find_python(python_exe, MAX_PATH, app_dir, !is_cli_mode)) {
            if (g_hSplash) DestroyWindow(g_hSplash);
            if (is_cli_mode) {
                print_banner();
                wprintf(L"\n[!] ERROR: Python 3.10+ runtime was not found.\n");
                wprintf(L"    SPECTRA requires Python 3.10+ and pyserial to communicate with\n");
                wprintf(L"    FTDI optical transceivers and COM serial ports.\n\n");
                pause_exit(1);
            } else {
                MessageBoxW(
                    NULL,
                    L"SPECTRA requires Python 3.10+ to interface with physical COM serial ports.\n\n"
                    L"Python was not detected in PATH or standard installation folders.\n\n"
                    L"Please install Python from python.org with 'Add Python to PATH' enabled.",
                    L"SPECTRA — Python Runtime Required",
                    MB_ICONWARNING | MB_OK
                );
            }
            return 1;
        }
    }

    // 3b. Native Desktop Shell Cutover: prefer spectra-shell.exe directly in GUI mode
    wchar_t shell_exe[MAX_PATH];
    swprintf(shell_exe, MAX_PATH, L"%ls\\spectra-shell.exe", app_dir);
    if (!is_cli_mode && !is_browser_mode && file_exists(shell_exe)) {
        if (g_hSplash) {
            DestroyWindow(g_hSplash);
            g_hSplash = NULL;
        }
        wchar_t shell_cmd[32768];
        swprintf(shell_cmd, 32768, L"\"%ls\" --root \"%ls\"", shell_exe, app_dir);

        STARTUPINFOW si_shell;
        PROCESS_INFORMATION pi_shell;
        ZeroMemory(&si_shell, sizeof(si_shell));
        si_shell.cb = sizeof(si_shell);
        si_shell.dwFlags = STARTF_USESHOWWINDOW;
        si_shell.wShowWindow = SW_SHOWNORMAL;
        ZeroMemory(&pi_shell, sizeof(pi_shell));

        if (CreateProcessW(NULL, shell_cmd, NULL, NULL, FALSE, 0, NULL, app_dir, &si_shell, &pi_shell)) {
            WaitForSingleObject(pi_shell.hProcess, INFINITE);
            DWORD shell_exit = 0;
            GetExitCodeProcess(pi_shell.hProcess, &shell_exit);
            CloseHandle(pi_shell.hProcess);
            CloseHandle(pi_shell.hThread);
            LocalFree(argv);
            return (int)shell_exit;
        }
    }

    // 4. Resolve target script
    wchar_t script_path[MAX_PATH];
    swprintf(script_path, MAX_PATH, L"%ls\\spectra_app.py", app_dir);
    if (!file_exists(script_path)) {
        swprintf(script_path, MAX_PATH, L"%ls\\web_server.py", app_dir);
    }

    if (!file_exists(script_path)) {
        if (g_hSplash) DestroyWindow(g_hSplash);
        if (is_cli_mode) {
            print_banner();
            wprintf(L"\n[!] ERROR: SPECTRA application files were not found in:\n    %ls\n\n", app_dir);
            pause_exit(1);
        } else {
            MessageBoxW(
                NULL,
                L"Unable to find spectra_app.py or web_server.py.\n"
                L"Please verify application files are intact.",
                L"SPECTRA — Launch Error",
                MB_ICONERROR | MB_OK
            );
        }
        return 1;
    }

    // 5. Construct command line
    wchar_t cmd_line[32768];
    int offset = swprintf(cmd_line, 32768, L"\"%ls\" \"%ls\"", python_exe, script_path);

    for (int i = 1; i < argc; i++) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" \"%ls\"", argv[i]);
    }

    if (argc <= 1) {
        offset += swprintf(cmd_line + offset, 32768 - offset, L" --open");
    }

    // 6. Launch child process
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    // Keep CREATE_NO_WINDOW to suppress any console popup, while using SW_SHOWNORMAL
    // so .NET WinForms / pywebview / WebView2's first top-level Form is never hidden by SW_HIDE.
    if (!is_cli_mode) {
        si.dwFlags = STARTF_USESHOWWINDOW;
        si.wShowWindow = SW_SHOWNORMAL;
    }
    ZeroMemory(&pi, sizeof(pi));

    DWORD creation_flags = !is_cli_mode ? CREATE_NO_WINDOW : 0;
    BOOL success = CreateProcessW(
        NULL,
        cmd_line,
        NULL,
        NULL,
        FALSE,
        creation_flags,
        NULL,
        app_dir,
        &si,
        &pi
    );

    if (!success) {
        DWORD err = GetLastError();
        if (g_hSplash) DestroyWindow(g_hSplash);
        if (is_cli_mode) {
            wprintf(L"[-] Failed to launch SPECTRA process. Error code: %lu\n", err);
            pause_exit(err);
        } else {
            wchar_t errMsg[256];
            swprintf(errMsg, 256, L"Failed to launch SPECTRA process.\nError code: %lu", err);
            MessageBoxW(NULL, errMsg, L"SPECTRA — Process Error", MB_ICONERROR | MB_OK);
        }
        return (int)err;
    }

    g_hChildProcess = pi.hProcess;
    g_child_pid = pi.dwProcessId;
    g_timer_ticks = 0; // Reset ticks so child process gets full window discovery period

    // 7. If in GUI mode, pump splash messages until main window is ready
    if (!is_cli_mode && g_hSplash != NULL) {
        MSG msg;
        while (g_hSplash != NULL && IsWindow(g_hSplash) && GetMessageW(&msg, NULL, 0, 0)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        cleanup_splash_gdi();
    }

    // 8. Wait for child process to terminate
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);

    if (is_cli_mode && exit_code != 0) {
        pause_exit(exit_code);
    } else if (!is_cli_mode && exit_code != 0) {
        wchar_t errMsg[512];
        swprintf(errMsg, 512,
            L"SPECTRA process exited unexpectedly with code: %lu\n\n"
            L"A diagnostic crash log may have been saved to:\n"
            L"%%TEMP%%\\spectra_crash.log\n\n"
            L"You can also run 'spectra.exe --cli' in a command prompt\n"
            L"to view console diagnostic messages.",
            exit_code);
        MessageBoxW(NULL, errMsg, L"SPECTRA — Process Error", MB_ICONERROR | MB_OK);
    }

    return (int)exit_code;
}
