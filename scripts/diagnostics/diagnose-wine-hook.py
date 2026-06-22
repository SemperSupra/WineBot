#!/usr/bin/env python3
# EXECUTION: IN_CONTAINER — uses ctypes to interact with Wine/Win32 API; requires Wine runtime
# STATUS: ACTIVE — IAT hook verification tool; tests MessageBox/GetSaveFileName/ShellBrowse hooks
import argparse
import ctypes
import ctypes.wintypes as wt
import json
import time

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MBUTTONDOWN = 0x0207
WM_MBUTTONUP = 0x0208
WM_MOUSEWHEEL = 0x020A
WM_MOUSEHWHEEL = 0x020E

ULONG_PTR = getattr(
    wt,
    "ULONG_PTR",
    ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong,
)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wt.DWORD),
        ("scanCode", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class POINT(ctypes.Structure):
    _fields_ = [("x", wt.LONG), ("y", wt.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wt.DWORD),
        ("flags", wt.DWORD),
        ("time", wt.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wt.HWND),
        ("message", wt.UINT),
        ("wParam", wt.WPARAM),
        ("lParam", wt.LPARAM),
        ("time", wt.DWORD),
        ("pt", POINT),
    ]


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wt.UINT), ("dwTime", wt.DWORD)]


user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = getattr(
    wt,
    "LRESULT",
    ctypes.c_longlong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_long,
)
LowLevelProc = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)

user32.SetWindowsHookExW.argtypes = [ctypes.c_int, LowLevelProc, wt.HINSTANCE, wt.DWORD]
user32.SetWindowsHookExW.restype = wt.HHOOK
user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
user32.CallNextHookEx.restype = LRESULT
kernel32.GetModuleHandleW.argtypes = [wt.LPCWSTR]
kernel32.GetModuleHandleW.restype = wt.HINSTANCE
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wt.HWND
user32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
user32.GetWindowRect.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
user32.GetWindowThreadProcessId.restype = wt.DWORD
user32.GetQueueStatus.argtypes = [wt.UINT]
user32.GetQueueStatus.restype = wt.DWORD
user32.GetLastInputInfo.argtypes = [ctypes.POINTER(LASTINPUTINFO)]
user32.GetLastInputInfo.restype = wt.BOOL
kernel32.GetTickCount64.restype = ctypes.c_ulonglong
kernel32.GetTickCount.restype = wt.DWORD

FORMAT_MESSAGE_FROM_SYSTEM = 0x00001000
FORMAT_MESSAGE_IGNORE_INSERTS = 0x00000200


def main():
    parser = argparse.ArgumentParser(
        description="Low-level keyboard/mouse hook observer"
    )
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, default=0.0)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--source", default="windows")
    parser.add_argument("--layer", default="windows")
    parser.add_argument("--origin", default="unknown")
    parser.add_argument("--tool", default="win_hook")
    parser.add_argument("--sample-ms", type=int, default=0)
    parser.add_argument("--sample-focus", type=int, default=1)
    parser.add_argument("--sample-queue", type=int, default=1)
    args = parser.parse_args()

    out_path = args.out
    duration = float(args.duration)
    end_time = None
    if duration > 0:
        end_time = time.time() + max(0.1, duration)

    logf = open(out_path, "w", encoding="utf-8")

    def log_event(payload):
        payload["timestamp_epoch_ms"] = int(time.time() * 1000)
        if args.session_id:
            payload.setdefault("session_id", args.session_id)
        payload.setdefault("source", args.source)
        payload.setdefault("layer", args.layer)
        payload.setdefault("origin", args.origin)
        payload.setdefault("tool", args.tool)
        logf.write(json.dumps(payload) + "\n")
        logf.flush()

    def get_window_text(hwnd):
        buf = ctypes.create_unicode_buffer(512)
        if user32.GetWindowTextW(hwnd, buf, len(buf)) == 0:
            return ""
        return buf.value

    def get_class_name(hwnd):
        buf = ctypes.create_unicode_buffer(256)
        if user32.GetClassNameW(hwnd, buf, len(buf)) == 0:
            return ""
        return buf.value

    def log_focus_state():
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            log_event({"event": "focus_state", "hwnd": 0, "title": "", "class": ""})
            return
        title = get_window_text(hwnd)
        class_name = get_class_name(hwnd)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wt.DWORD(0)
        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        log_event(
            {
                "event": "focus_state",
                "hwnd": int(hwnd),
                "title": title,
                "class": class_name,
                "pid": int(pid.value),
                "tid": int(tid),
                "rect": {
                    "left": int(rect.left),
                    "top": int(rect.top),
                    "right": int(rect.right),
                    "bottom": int(rect.bottom),
                },
            }
        )

    QS_ALLINPUT = 0x04FF

    def get_tick_count():
        if hasattr(kernel32, "GetTickCount64"):
            return int(kernel32.GetTickCount64())
        return int(kernel32.GetTickCount())

    def log_queue_state():
        qs = user32.GetQueueStatus(QS_ALLINPUT)
        flags = int(qs & 0xFFFF)
        status = int((qs >> 16) & 0xFFFF)
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        last_input_ms_ago = None
        if user32.GetLastInputInfo(ctypes.byref(lii)):
            now = get_tick_count()
            last_input_ms_ago = int(now - lii.dwTime)
        payload = {"event": "queue_state", "queue_flags": flags, "queue_status": status}
        if last_input_ms_ago is not None:
            payload["last_input_ms_ago"] = last_input_ms_ago
        log_event(payload)

    def format_error(err_code):
        if not err_code:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        kernel32.FormatMessageW(
            FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS,
            None,
            err_code,
            0,
            buf,
            len(buf),
            None,
        )
        return buf.value.strip()

    log_event(
        {
            "event": "hook_start",
            "pid": int(kernel32.GetCurrentProcessId()),
            "tid": int(kernel32.GetCurrentThreadId()),
        }
    )

    sample_ms = max(0, int(args.sample_ms))
    next_sample = time.time()

    def keyboard_proc(nCode, wParam, lParam):
        if nCode == 0:
            kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk_code = int(kbd.vkCode)
            vk_name = f"vk{vk_code:02X}"
            if wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                log_event(
                    {
                        "event": "key_down",
                        "key": vk_name,
                        "vk": vk_name,
                        "vk_code": vk_code,
                        "scan": int(kbd.scanCode),
                        "flags": int(kbd.flags),
                    }
                )
            elif wParam in (WM_KEYUP, WM_SYSKEYUP):
                log_event(
                    {
                        "event": "key_up",
                        "key": vk_name,
                        "vk": vk_name,
                        "vk_code": vk_code,
                        "scan": int(kbd.scanCode),
                        "flags": int(kbd.flags),
                    }
                )
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def mouse_proc(nCode, wParam, lParam):
        if nCode == 0:
            ms = ctypes.cast(lParam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            if wParam == WM_MOUSEMOVE:
                log_event({"event": "mouse_move", "x": int(ms.pt.x), "y": int(ms.pt.y)})
            elif wParam == WM_LBUTTONDOWN:
                log_event(
                    {
                        "event": "mouse_down",
                        "button": "left",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_LBUTTONUP:
                log_event(
                    {
                        "event": "mouse_up",
                        "button": "left",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_RBUTTONDOWN:
                log_event(
                    {
                        "event": "mouse_down",
                        "button": "right",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_RBUTTONUP:
                log_event(
                    {
                        "event": "mouse_up",
                        "button": "right",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_MBUTTONDOWN:
                log_event(
                    {
                        "event": "mouse_down",
                        "button": "middle",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_MBUTTONUP:
                log_event(
                    {
                        "event": "mouse_up",
                        "button": "middle",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                    }
                )
            elif wParam == WM_MOUSEWHEEL:
                log_event(
                    {
                        "event": "mouse_wheel",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                        "mouseData": int(ms.mouseData),
                    }
                )
            elif wParam == WM_MOUSEHWHEEL:
                log_event(
                    {
                        "event": "mouse_hwheel",
                        "x": int(ms.pt.x),
                        "y": int(ms.pt.y),
                        "mouseData": int(ms.mouseData),
                    }
                )
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    keyboard_cb = LowLevelProc(keyboard_proc)
    mouse_cb = LowLevelProc(mouse_proc)

    ctypes.set_last_error(0)
    h_kbd = user32.SetWindowsHookExW(
        WH_KEYBOARD_LL, keyboard_cb, kernel32.GetModuleHandleW(None), 0
    )
    kbd_err = ctypes.get_last_error()
    ctypes.set_last_error(0)
    h_mouse = user32.SetWindowsHookExW(
        WH_MOUSE_LL, mouse_cb, kernel32.GetModuleHandleW(None), 0
    )
    mouse_err = ctypes.get_last_error()

    if not h_kbd:
        log_event(
            {
                "event": "hook_error",
                "hook": "keyboard",
                "err": int(kbd_err),
                "err_text": format_error(kbd_err),
            }
        )
    if not h_mouse:
        log_event(
            {
                "event": "hook_error",
                "hook": "mouse",
                "err": int(mouse_err),
                "err_text": format_error(mouse_err),
            }
        )

    if not h_kbd or not h_mouse:
        ctypes.set_last_error(0)
        thread_id = kernel32.GetCurrentThreadId()
        if not h_kbd:
            h_kbd = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, keyboard_cb, kernel32.GetModuleHandleW(None), thread_id
            )
            retry_err = ctypes.get_last_error()
            log_event(
                {
                    "event": "hook_retry",
                    "hook": "keyboard",
                    "thread_id": int(thread_id),
                    "ok": int(bool(h_kbd)),
                    "err": int(retry_err),
                    "err_text": format_error(retry_err),
                }
            )
        if not h_mouse:
            h_mouse = user32.SetWindowsHookExW(
                WH_MOUSE_LL, mouse_cb, kernel32.GetModuleHandleW(None), thread_id
            )
            retry_err = ctypes.get_last_error()
            log_event(
                {
                    "event": "hook_retry",
                    "hook": "mouse",
                    "thread_id": int(thread_id),
                    "ok": int(bool(h_mouse)),
                    "err": int(retry_err),
                    "err_text": format_error(retry_err),
                }
            )

    msg = MSG()
    while end_time is None or time.time() < end_time:
        if sample_ms > 0:
            now = time.time()
            if now >= next_sample:
                next_sample = now + (sample_ms / 1000.0)
                if args.sample_focus:
                    log_focus_state()
                if args.sample_queue:
                    log_queue_state()
        while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        time.sleep(0.01)

    if h_kbd:
        user32.UnhookWindowsHookEx(h_kbd)
    if h_mouse:
        user32.UnhookWindowsHookEx(h_mouse)

    logf.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
