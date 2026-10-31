/* SPDX-License-Identifier: MIT */
/* Synthetic event storm only: exercise bounded observer overflow. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

static LRESULT CALLBACK test_window_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_DESTROY)
        return 0;
    return DefWindowProcW(hwnd, msg, wp, lp);
}

int main(void) {
    WNDCLASSW wc = {0};
    int i;
    wc.lpfnWndProc = test_window_proc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"WB_RDTE_WINDOW";
    if (!RegisterClassW(&wc))
        return 2;
    for (i = 0; i != 160; ++i) {
        HWND hwnd = CreateWindowExW(0, wc.lpszClassName,
                                    L"WineBot Synthetic Storm", WS_OVERLAPPEDWINDOW,
                                    30, 30, 260, 160, NULL, NULL, wc.hInstance, NULL);
        if (!hwnd)
            return 3;
        ShowWindow(hwnd, SW_SHOWNORMAL);
        MoveWindow(hwnd, 40 + (i % 10), 40 + (i % 10), 280, 180, TRUE);
        UpdateWindow(hwnd);
        Sleep(25);
        DestroyWindow(hwnd);
        Sleep(15);
    }
    return 0;
}
