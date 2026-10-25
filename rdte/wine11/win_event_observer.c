/*
 * SPDX-License-Identifier: MIT
 * WineBot read-only WinEvent RDTE; Windows event hooks are used unmodified.
 * Outputs ONLY synthetic-schema event kinds and sequence numbers. No titles,
 * HWNDs, PIDs, coordinates, application content, paths or real user data.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define FIXTURE_CLASS L"WB_RDTE_WINDOW"
#define MAX_OBSERVATIONS 128
#define MAX_LIFETIME_MS 120000UL
#define CONTROL_POLL_MS 100
#ifndef CHILDID_SELF
#define CHILDID_SELF 0
#endif
static unsigned int sequence = 0;
static int overflow_reported = 0;

static void emit(const char *kind, unsigned int index) {
    printf("{\"schema\":\"winebot.wine.event.v1\",\"kind\":\"%s\",\"sequence\":%u}\n",
           kind, index);
    fflush(stdout);
}

static void CALLBACK observe(HWINEVENTHOOK hook, DWORD event, HWND hwnd,
                             LONG object_id, LONG child_id,
                             DWORD thread_id, DWORD event_time) {
    WCHAR class_name[64];
    const char *kind = NULL;
    (void)hook;
    (void)thread_id;
    (void)event_time;
    if (!hwnd || object_id != OBJID_WINDOW || child_id != CHILDID_SELF)
        return;
    if (!GetClassNameW(hwnd, class_name, 64))
        return;
    if (lstrcmpW(class_name, FIXTURE_CLASS) != 0)
        return;

    switch (event) {
        case EVENT_OBJECT_CREATE: kind = "create"; break;
        case EVENT_OBJECT_SHOW: kind = "show"; break;
        case EVENT_OBJECT_HIDE: kind = "hide"; break;
        case EVENT_OBJECT_DESTROY: kind = "destroy"; break;
        case EVENT_OBJECT_FOCUS: kind = "focus"; break;
        case EVENT_OBJECT_LOCATIONCHANGE: kind = "location"; break;
        case EVENT_SYSTEM_FOREGROUND: kind = "foreground"; break;
        default: return;
    }
    if (sequence >= MAX_OBSERVATIONS) {
        if (!overflow_reported) {
            emit("overflow", ++sequence);
            overflow_reported = 1;
            PostQuitMessage(6);
        }
        return;
    }
    emit(kind, ++sequence);
}

int main(void) {
    HWINEVENTHOOK events_hook;
    HWINEVENTHOOK foreground_hook;
    MSG message;
    BOOL message_result;
    UINT_PTR timer_id;
    HANDLE control = GetStdHandle(STD_INPUT_HANDLE);
    DWORD started = GetTickCount();
    int rc = 0;

    /* RDTE stop channel: exactly one Q byte over a private inherited pipe.
     * No application selection, network transport, or arbitrary commands. */
    if (control == INVALID_HANDLE_VALUE || GetFileType(control) != FILE_TYPE_PIPE) {
        emit("unsupported", 0);
        return 4;
    }

    events_hook = SetWinEventHook(EVENT_OBJECT_CREATE, EVENT_OBJECT_LOCATIONCHANGE,
                                  NULL, observe, 0, 0,
                                  WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS);
    foreground_hook = SetWinEventHook(EVENT_SYSTEM_FOREGROUND, EVENT_SYSTEM_FOREGROUND,
                                      NULL, observe, 0, 0,
                                      WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS);
    if (!events_hook || !foreground_hook) {
        emit("unsupported", 0);
        rc = 4;
        goto done;
    }
    timer_id = SetTimer(NULL, 0, CONTROL_POLL_MS, NULL);
    if (!timer_id) {
        emit("unsupported", 0);
        rc = 4;
        goto done;
    }
    emit("ready", 0);
    while ((message_result = GetMessageW(&message, NULL, 0, 0)) > 0) {
        if (message.message == WM_TIMER && message.wParam == timer_id) {
            DWORD available = 0;
            char command = 0;
            DWORD received = 0;
            if ((DWORD)(GetTickCount() - started) >= MAX_LIFETIME_MS) {
                rc = 3; /* Expiration is not ordinary EOF. */
                break;
            }
            if (!PeekNamedPipe(control, NULL, 0, NULL, &available, NULL)) {
                /* A closed owning process pipe is a terminal stop. */
                DWORD why = GetLastError();
                rc = (why == ERROR_BROKEN_PIPE || why == ERROR_PIPE_NOT_CONNECTED) ? 0 : 4;
                break;
            }
            if (available > 0) {
                if (!ReadFile(control, &command, 1, &received, NULL)
                    || received != 1 || command != 'Q') {
                    rc = 4;
                }
                break;
            }
            continue;
        }
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    if (message_result < 0)
        rc = 4;
    if (overflow_reported)
        rc = 6;
    KillTimer(NULL, timer_id);
done:
    if (foreground_hook)
        UnhookWinEvent(foreground_hook);
    if (events_hook)
        UnhookWinEvent(events_hook);
    return rc;
}
