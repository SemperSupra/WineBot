/* Source-backed synthetic input oracle for Wine built-in Notepad.
 * Upstream wine-mirror/wine programs/notepad/main.c registers the Notepad
 * Win32 class and creates a child EDIT control. No content leaves the runner.
 * Copyright 2026 WineBot RDTE contributors; public test-only fixture.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>
#include <stdio.h>

int main(void)
{
    HWND notepad = FindWindowW(L"Notepad", NULL);
    if (!notepad) { puts("UNQUALIFIED: notepad_native_top_level"); return 2; }
    HWND edit = FindWindowExW(notepad, NULL, L"Edit", NULL);
    if (!edit) { puts("UNQUALIFIED: notepad_native_edit_control"); return 2; }
    wchar_t text[256] = {0};
    DWORD_PTR n = 0;
    if (!SendMessageTimeoutW(edit, WM_GETTEXT, 256, (LPARAM)text,
                             SMTO_ABORTIFHUNG | SMTO_BLOCK, 3000, &n)) {
        puts("UNQUALIFIED: notepad_native_gettext_timeout"); return 2;
    }
    if (!wcsstr(text, L"WINEBOTRDTE")) {
        puts("UNQUALIFIED: notepad_native_text_mismatch"); return 2;
    }
    puts("PASS: Wine Notepad native EDIT text readback after X11 input");
    return 0;
}
