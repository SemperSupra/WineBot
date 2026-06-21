/*
 * comdlg32_hook.c — API hook DLL for GetSaveFileNameW / GetOpenFileNameW
 *
 * Replaces Wine's file dialog with the AHK pipe-driven dialog replacement.
 * Only two exports: GetSaveFileNameW and GetOpenFileNameW.
 * All other comdlg32 functions fall through to Wine's builtin (n,b override).
 */

#include <windows.h>
#include <commdlg.h>

/* ── Pipe protocol (shared with dialog_replacement.ahk) ── */
#define PIPE        L"C:\\dialog_handler\\pipe.txt"
#define ARTIFACTS   L"C:/artifacts/"
#define BUF_SIZE    4096
#define TIMEOUT     10000

static void write_pipe(const WCHAR *msg) {
    HANDLE h = CreateFileW(PIPE, GENERIC_WRITE, FILE_SHARE_READ,
                           NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD len = lstrlenW(msg) * sizeof(WCHAR), written;
    WriteFile(h, msg, len, &written, NULL);
    FlushFileBuffers(h);
    CloseHandle(h);
}

static int read_pipe(WCHAR *buf, DWORD size, DWORD timeout) {
    DWORD elapsed = 0;
    while (elapsed < timeout) {
        HANDLE h = CreateFileW(PIPE, GENERIC_READ, FILE_SHARE_READ,
                               NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            DWORD fs = GetFileSize(h, NULL);
            if (fs > 4 && fs < size) {
                BYTE *raw = (BYTE *)buf;
                DWORD rd;
                ReadFile(h, raw, fs, &rd, NULL);
                raw[rd] = 0;
                WCHAR *s = buf;
                while (*s && *s != L'{') s++;
                if (*s == L'{') { CloseHandle(h); return 1; }
            }
            CloseHandle(h);
        }
        Sleep(100); elapsed += 100;
    }
    buf[0] = 0; return 0;
}

static void extract_path(const WCHAR *json, WCHAR *out, int outlen) {
    const WCHAR *key = L"\"path\":\"";
    const WCHAR *s = wcsstr(json, key);
    if (!s) { out[0] = 0; return; }
    s += 8; /* strlen of "path":" */
    const WCHAR *e = wcsstr(s, L"\"");
    if (!e) { out[0] = 0; return; }
    int n = (int)(e - s);
    if (n >= outlen) n = outlen - 1;
    { int i; for (i = 0; i < n; i++) out[i] = s[i]; }
    out[n] = 0;
}

static void fwd_to_bslash(WCHAR *p) {
    for (; *p; p++) if (*p == L'/') *p = L'\\';
}

/* ── Pipe dialog workflow ── */

static BOOL run_pipe_save(LPOPENFILENAMEW ofn) {
    WCHAR b[BUF_SIZE];

    /* Step 1: open the AHK Gui */
    write_pipe(L"open_gui");
    if (!read_pipe(b, sizeof(b), 5000)) return FALSE;

    /* Step 2: set filename (use app default if provided) */
    if (ofn->lpstrFile && ofn->lpstrFile[0]) {
        WCHAR cmd[BUF_SIZE];
        wsprintfW(cmd, L"set_filename:%s", ofn->lpstrFile);
        write_pipe(cmd);
    } else {
        write_pipe(L"set_filename:save_result.txt");
    }
    if (!read_pipe(b, sizeof(b), 5000)) return FALSE;

    /* Step 3: click save — response has the path */
    write_pipe(L"click_save");
    if (!read_pipe(b, sizeof(b), TIMEOUT)) return FALSE;

    /* Step 4: extract path from {"status":"saved","path":"C:/artifacts/x.txt"} */
    WCHAR path[MAX_PATH];
    extract_path(b, path, MAX_PATH);
    if (!path[0]) return FALSE;

    fwd_to_bslash(path);

    if (ofn->lpstrFile) {
        lstrcpynW(ofn->lpstrFile, path, ofn->nMaxFile);
        ofn->nFileOffset = lstrlenW(ofn->lpstrFile);
    }

    return TRUE;
}

/* ── Exports ── */

BOOL WINAPI GetSaveFileNameW(LPOPENFILENAMEW ofn) { return run_pipe_save(ofn); }
BOOL WINAPI GetOpenFileNameW(LPOPENFILENAMEW ofn) { return run_pipe_save(ofn); }

/* ── Entry point ── */
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h);
    return TRUE;
}
