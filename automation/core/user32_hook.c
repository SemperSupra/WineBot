/*
 * user32_hook.c — Auto-dismiss MessageBoxW/MessageBoxA
 *
 * Returns the default positive response immediately without showing any dialog.
 * Reads MB_OK/OKCANCEL/YESNO/etc. from the uType parameter.
 *
 * Build:
 *   x86_64-w64-mingw32-gcc -shared -o user32.dll user32_hook.c \
 *     -nostartfiles -lkernel32
 *   i686-w64-mingw32-gcc -shared -o user32_32.dll user32_hook.c \
 *     -nostartfiles -lkernel32
 *
 * Install: cp to system32/syswow64, set per-app override:
 *   WINEDLLOVERRIDES="user32=n,b" wine app.exe
 */

#include <windows.h>

/* ── Exports ── */

int WINAPI MessageBoxW(HWND hWnd, LPCWSTR lpText, LPCWSTR lpCaption, UINT uType) {
    (void)hWnd; (void)lpText; (void)lpCaption;

    /* Return the default button based on dialog type */
    UINT buttons = uType & 0x0F; /* MB_OK=0, MB_OKCANCEL=1, MB_ABORTRETRYIGNORE=2,
                                    MB_YESNOCANCEL=3, MB_YESNO=4, MB_RETRYCANCEL=5 */

    switch (buttons) {
        case MB_OK:               return IDOK;
        case MB_OKCANCEL:         return IDOK;
        case MB_ABORTRETRYIGNORE: return IDIGNORE;
        case MB_YESNOCANCEL:      return IDYES;
        case MB_YESNO:            return IDYES;
        case MB_RETRYCANCEL:      return IDRETRY;
        default:                  return IDOK;
    }
}

int WINAPI MessageBoxA(HWND hWnd, LPCSTR lpText, LPCSTR lpCaption, UINT uType) {
    return MessageBoxW(hWnd, NULL, NULL, uType);
}

/* ── Stubs for functions Wine internals require ── */
/* These must exist or the Wine loader aborts when n,b override is active */

void WINAPI User32InitializeImmEntryTable(DWORD x) { (void)x; return; }

/* ── Entry point ── */
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID r) {
    (void)h; (void)r;
    if (reason == DLL_PROCESS_ATTACH) DisableThreadLibraryCalls(h);
    return TRUE;
}
