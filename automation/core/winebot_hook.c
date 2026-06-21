/*
 * winebot_hook.c — Single hook DLL for all Wine dialog interception
 *
 * Unlike per-DLL replacements, this uses the "AppInit_DLLs" pattern.
 * Loaded with WINEDLLOVERRIDES="winebot_hook=n" — a unique name that
 * doesn't conflict with any system DLL. On attach, it replaces the
 * target function pointers in the process's import table.
 *
 * Functions intercepted:
 *   user32!MessageBoxW, user32!MessageBoxA  → auto-dismiss
 *   comdlg32!GetSaveFileNameW               → pipe dialog
 *   comdlg32!GetOpenFileNameW               → pipe dialog
 *   shell32!SHBrowseForFolderW             → pipe dialog
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -shared -o winebot_hook.dll winebot_hook.c \
 *     -nostartfiles -lkernel32 -luser32 -lshell32
 */

#include <windows.h>
#include <commdlg.h>
#include <shlobj.h>

/* ── Pipe protocol ── */
#define PIPE        L"C:\\dialog_handler\\pipe.txt"
#define BUF_SIZE    4096
#define TIMEOUT     10000

static void pipe_write(const WCHAR *msg) {
    HANDLE h = CreateFileW(PIPE, GENERIC_WRITE, FILE_SHARE_READ,
                           NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    DWORD len = lstrlenW(msg) * sizeof(WCHAR), wr;
    WriteFile(h, msg, len, &wr, NULL);
    FlushFileBuffers(h);
    CloseHandle(h);
}

static int pipe_read(WCHAR *buf, DWORD size, DWORD timeout) {
    DWORD elapsed = 0;
    while (elapsed < timeout) {
        HANDLE h = CreateFileW(PIPE, GENERIC_READ, FILE_SHARE_READ,
                               NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
        if (h != INVALID_HANDLE_VALUE) {
            DWORD fs = GetFileSize(h, NULL);
            if (fs > 4 && fs < size) {
                BYTE *raw = (BYTE *)buf; DWORD rd;
                ReadFile(h, raw, fs, &rd, NULL); raw[rd] = 0;
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

static void extract_path(const WCHAR *json, WCHAR *out, int n) {
    const WCHAR *key = L"\"path\":\"";
    const WCHAR *s = wcsstr(json, key);
    if (!s) { out[0] = 0; return; } s += 8;
    const WCHAR *e = wcsstr(s, L"\"");
    if (!e) { out[0] = 0; return; }
    int len = (int)(e - s); if (len >= n) len = n - 1;
    { int i; for (i = 0; i < len; i++) out[i] = s[i]; } out[len] = 0;
}

/* ── Pipe save workflow (shared by comdlg32 + shell32) ── */

static BOOL pipe_save_flow(const WCHAR *default_name, WCHAR *result, int rlen) {
    WCHAR b[BUF_SIZE];
    pipe_write(L"open_gui");
    if (!pipe_read(b, sizeof(b), 5000)) return FALSE;

    if (default_name && default_name[0]) {
        WCHAR cmd[BUF_SIZE];
        wsprintfW(cmd, L"set_filename:%s", default_name);
        pipe_write(cmd);
    } else {
        pipe_write(L"set_filename:save_result");
    }
    if (!pipe_read(b, sizeof(b), 5000)) return FALSE;

    pipe_write(L"click_save");
    if (!pipe_read(b, sizeof(b), TIMEOUT)) return FALSE;

    extract_path(b, result, rlen);
    return result[0] != 0;
}

static void fwd_to_bslash(WCHAR *p) {
    for (; *p; p++) if (*p == L'/') *p = L'\\';
}

/* ── Override Message Box (use IAT-style direct hook) ── */

typedef int (WINAPI *MessageBoxW_t)(HWND, LPCWSTR, LPCWSTR, UINT);
typedef int (WINAPI *MessageBoxA_t)(HWND, LPCSTR, LPCSTR, UINT);
typedef BOOL (WINAPI *GetSaveFileNameW_t)(LPOPENFILENAMEW);
typedef BOOL (WINAPI *GetOpenFileNameW_t)(LPOPENFILENAMEW);
typedef LPITEMIDLIST (WINAPI *SHBrowseForFolderW_t)(LPBROWSEINFOW);

static MessageBoxW_t   TrueMessageBoxW    = NULL;
static MessageBoxA_t   TrueMessageBoxA    = NULL;
static GetSaveFileNameW_t TrueGetSaveFileNameW = NULL;
static GetOpenFileNameW_t TrueGetOpenFileNameW = NULL;
static SHBrowseForFolderW_t TrueSHBrowseForFolderW = NULL;

/* Our replacements */
static int WINAPI Hook_MessageBoxW(HWND h, LPCWSTR t, LPCWSTR c, UINT u) {
    (void)h; (void)t; (void)c;
    UINT btns = u & 0x0F;
    switch (btns) {
        case MB_OK: return IDOK;
        case MB_OKCANCEL: return IDOK;
        case MB_ABORTRETRYIGNORE: return IDIGNORE;
        case MB_YESNOCANCEL: return IDYES;
        case MB_YESNO: return IDYES;
        case MB_RETRYCANCEL: return IDRETRY;
        default: return IDOK;
    }
}

static int WINAPI Hook_MessageBoxA(HWND h, LPCSTR t, LPCSTR c, UINT u) {
    return Hook_MessageBoxW(h, NULL, NULL, u);
}

static BOOL WINAPI Hook_GetSaveFileNameW(LPOPENFILENAMEW ofn) {
    WCHAR path[MAX_PATH];
    if (!pipe_save_flow(ofn->lpstrFile && ofn->lpstrFile[0] ? ofn->lpstrFile : L"save_result", path, MAX_PATH))
        return FALSE;
    fwd_to_bslash(path);
    if (ofn->lpstrFile) {
        lstrcpynW(ofn->lpstrFile, path, ofn->nMaxFile);
        ofn->nFileOffset = lstrlenW(ofn->lpstrFile);
    }
    return TRUE;
}

static BOOL WINAPI Hook_GetOpenFileNameW(LPOPENFILENAMEW ofn) {
    return Hook_GetSaveFileNameW(ofn);
}

static LPITEMIDLIST make_pidl(const WCHAR *path) {
    if (!path || !path[0]) return NULL;
    WCHAR clean[MAX_PATH];
    lstrcpynW(clean, path, MAX_PATH);
    WCHAR *p; for (p = clean; *p; p++) if (*p == L'/') *p = L'\\';
    int pb = (lstrlenW(clean) + 1) * sizeof(WCHAR);
    int total = sizeof(USHORT) + pb + sizeof(USHORT);
    LPITEMIDLIST pidl = (LPITEMIDLIST)CoTaskMemAlloc(total);
    if (!pidl) return NULL;
    BYTE *raw = (BYTE *)pidl;
    *(USHORT *)raw = (USHORT)(pb + sizeof(USHORT));
    memcpy(raw + sizeof(USHORT), clean, pb);
    *(USHORT *)(raw + sizeof(USHORT) + pb) = 0;
    return pidl;
}

static LPITEMIDLIST WINAPI Hook_SHBrowseForFolderW(LPBROWSEINFOW lpbi) {
    WCHAR path[MAX_PATH];
    if (!pipe_save_flow(lpbi && lpbi->lpszTitle ? lpbi->lpszTitle : L"folder", path, MAX_PATH))
        return NULL;
    return make_pidl(path);
}

/* ── IAT hook helper ── */
static void *replace_iat_entry(HMODULE target_module, const char *target_dll,
                                const char *func_name, void *new_func) {
    PIMAGE_DOS_HEADER dos = (PIMAGE_DOS_HEADER)target_module;
    PIMAGE_NT_HEADERS nt = (PIMAGE_NT_HEADERS)((BYTE *)target_module + dos->e_lfanew);
    IMAGE_DATA_DIRECTORY imp = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
    if (!imp.VirtualAddress) return NULL;

    PIMAGE_IMPORT_DESCRIPTOR desc = (PIMAGE_IMPORT_DESCRIPTOR)((BYTE *)target_module + imp.VirtualAddress);
    while (desc->Name) {
        const char *name = (const char *)((BYTE *)target_module + desc->Name);
        if (_stricmp(name, target_dll) == 0) {
            PIMAGE_THUNK_DATA thunk = (PIMAGE_THUNK_DATA)((BYTE *)target_module + desc->FirstThunk);
            PIMAGE_THUNK_DATA orig  = (PIMAGE_THUNK_DATA)((BYTE *)target_module + (desc->OriginalFirstThunk ? desc->OriginalFirstThunk : desc->FirstThunk));
            while (orig->u1.AddressOfData) {
                if (!(orig->u1.Ordinal & IMAGE_ORDINAL_FLAG)) {
                    PIMAGE_IMPORT_BY_NAME byName = (PIMAGE_IMPORT_BY_NAME)((BYTE *)target_module + orig->u1.AddressOfData);
                    if (strcmp((char *)byName->Name, func_name) == 0) {
                        void *old = (void *)thunk->u1.Function;
                        DWORD oldProt;
                        VirtualProtect(&thunk->u1.Function, sizeof(void *), PAGE_READWRITE, &oldProt);
                        thunk->u1.Function = (ULONG_PTR)new_func;
                        VirtualProtect(&thunk->u1.Function, sizeof(void *), oldProt, &oldProt);
                        return old;
                    }
                }
                orig++; thunk++;
            }
        }
        desc++;
    }
    return NULL;
}

/* ── Entry point ── */
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)r;
    if (reason != DLL_PROCESS_ATTACH) return TRUE;
    DisableThreadLibraryCalls(h);

    /* Get the EXE's module handle */
    HMODULE exe = GetModuleHandleW(NULL);
    if (!exe) return TRUE;

    /* Hook user32!MessageBoxW/A in the EXE's import table */
    replace_iat_entry(exe, "user32.dll", "MessageBoxW", Hook_MessageBoxW);
    replace_iat_entry(exe, "user32.dll", "MessageBoxA", Hook_MessageBoxA);

    /* Hook comdlg32 file dialogs */
    replace_iat_entry(exe, "comdlg32.dll", "GetSaveFileNameW", Hook_GetSaveFileNameW);
    replace_iat_entry(exe, "comdlg32.dll", "GetOpenFileNameW", Hook_GetOpenFileNameW);

    /* Hook shell32 folder browser */
    replace_iat_entry(exe, "shell32.dll", "SHBrowseForFolderW", Hook_SHBrowseForFolderW);

    return TRUE;
}
