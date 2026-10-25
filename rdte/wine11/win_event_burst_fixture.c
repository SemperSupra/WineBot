/* SPDX-License-Identifier: MIT
 * Synthetic-only Win32 WinEvent callback pressure. No user windows or content.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#ifndef CHILDID_SELF
#define CHILDID_SELF 0
#endif

static LRESULT CALLBACK fixture_proc(HWND hwnd, UINT message,
                                     WPARAM wparam, LPARAM lparam) {
    if (message == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(hwnd, message, wparam, lparam);
}

int main(void) {
    WNDCLASSW wc = {0};
    HWND hwnd;
    unsigned int index;
    wc.lpfnWndProc = fixture_proc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"WB_RDTE_WINDOW";
    if (!RegisterClassW(&wc))
        return 2;
    hwnd = CreateWindowExW(0, wc.lpszClassName, L"WineBot Synthetic Burst",
                           WS_OVERLAPPEDWINDOW, 60, 60, 320, 200,
                           NULL, NULL, wc.hInstance, NULL);
    if (!hwnd)
        return 3;
    ShowWindow(hwnd, SW_SHOWNORMAL);
    UpdateWindow(hwnd);
    Sleep(500);
    for (index = 0; index < 192; ++index) {
        NotifyWinEvent(EVENT_OBJECT_LOCATIONCHANGE, hwnd,
                       OBJID_WINDOW, CHILDID_SELF);
        Sleep(9);
    }
    DestroyWindow(hwnd);
    return 0;
}
