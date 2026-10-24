/*
 * SPDX-License-Identifier: MIT
 * A synthetic, independently built Win32 event producer. No personal data.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static LRESULT CALLBACK window_proc(HWND hwnd, UINT message,
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
    wc.lpfnWndProc = window_proc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"WB_RDTE_WINDOW";
    if (!RegisterClassW(&wc))
        return 2;
    hwnd = CreateWindowExW(0, wc.lpszClassName,
                           L"WineBot RDTE Fixture", WS_OVERLAPPEDWINDOW,
                           60, 60, 320, 200, NULL, NULL, wc.hInstance, NULL);
    if (!hwnd)
        return 3;
    ShowWindow(hwnd, SW_SHOWNORMAL);
    UpdateWindow(hwnd);
    Sleep(1200);
    if (!MoveWindow(hwnd, 140, 110, 360, 250, TRUE))
        return 4;
    Sleep(1200);
    SetForegroundWindow(hwnd);
    Sleep(1200);
    DestroyWindow(hwnd);
    return 0;
}
