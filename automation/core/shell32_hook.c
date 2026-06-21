/*
 * shell32_hook.c — Intercept SHBrowseForFolderW
 *
 * Replaces the folder browser dialog with our pipe-driven AHK replacement.
 * Returns a simple PIDL pointing to the chosen directory.
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -shared -o shell32.dll shell32_hook.c \
 *     -nostartfiles -lkernel32 -luser32 -lshell32
 */

#include <windows.h>
#include <shlobj.h>
#include <stdio.h>

/* ── Pipe protocol (shared with dialog_replacement.ahk) ── */
#define PIPE        L"C:\\dialog_handler\\pipe.txt"
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
    s += 8;
    const WCHAR *e = wcsstr(s, L"\"");
    if (!e) { out[0] = 0; return; }
    int n = (int)(e - s);
    if (n >= outlen) n = outlen - 1;
    { int i; for (i = 0; i < n; i++) out[i] = s[i]; }
    out[n] = 0;
}

/* Build a simple PIDL from a filesystem path string.
 * A simple PIDL is a SHITEMID structure with just the path bytes,
 * terminated by a 2-byte zero cb field. */
static LPITEMIDLIST make_simple_pidl(const WCHAR *path) {
    if (!path || !path[0]) return NULL;

    /* Convert forward slashes to backslashes */
    WCHAR clean[MAX_PATH];
    lstrcpynW(clean, path, MAX_PATH);
    WCHAR *p;
    for (p = clean; *p; p++) if (*p == L'/') *p = L'\\';

    /* Calculate size: 1 SHITEMID with the path, then terminator */
    int path_bytes = (lstrlenW(clean) + 1) * sizeof(WCHAR); /* +1 for null */
    int total = sizeof(USHORT) + path_bytes + sizeof(USHORT); /* cb + data + terminator cb */

    LPITEMIDLIST pidl = (LPITEMIDLIST)CoTaskMemAlloc(total);
    if (!pidl) return NULL;

    BYTE *raw = (BYTE *)pidl;
    *(USHORT *)raw = (USHORT)(path_bytes + sizeof(USHORT)); /* cb: size of this item including cb itself */
    raw += sizeof(USHORT);
    memcpy(raw, clean, path_bytes); /* data */
    raw += path_bytes;
    *(USHORT *)raw = 0; /* terminator cb=0 */

    return pidl;
}

/* ── Hook ── */

LPITEMIDLIST WINAPI SHBrowseForFolderW(LPBROWSEINFOW lpbi) {
    WCHAR b[BUF_SIZE];

    write_pipe(L"open_gui");
    if (!read_pipe(b, sizeof(b), 5000)) return NULL;

    /* Use the display name or title as default */
    if (lpbi && lpbi->lpszTitle) {
        WCHAR cmd[BUF_SIZE];
        wsprintfW(cmd, L"set_filename:%s", lpbi->lpszTitle);
        write_pipe(cmd);
    } else {
        write_pipe(L"set_filename:browse_result");
    }
    if (!read_pipe(b, sizeof(b), 5000)) return NULL;

    write_pipe(L"click_save");
    if (!read_pipe(b, sizeof(b), TIMEOUT)) return NULL;

    WCHAR path[MAX_PATH];
    extract_path(b, path, MAX_PATH);
    if (!path[0]) return NULL;

    return make_simple_pidl(path);
}

/* ── Entry point ── */
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h);
    return TRUE;
}
