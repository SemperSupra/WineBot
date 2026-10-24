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
        }
        return;
    }
    emit(kind, ++sequence);
}

int main(void) {
    HWINEVENTHOOK events_hook;
    HWINEVENTHOOK foreground_hook;
    MSG message;
    UINT_PTR timer_id;
    int rc = 0;

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
    timer_id = SetTimer(NULL, 0, 12000, NULL);
    if (!timer_id) {
        emit("unsupported", 0);
        rc = 4;
        goto done;
    }
    emit("ready", 0);
    while (GetMessageW(&message, NULL, 0, 0) > 0) {
        if (message.message == WM_TIMER && message.wParam == timer_id)
            break;
        TranslateMessage(&message);
        DispatchMessageW(&message);
    }
    KillTimer(NULL, timer_id);
done:
    if (foreground_hook)
        UnhookWinEvent(foreground_hook);
    if (events_hook)
        UnhookWinEvent(events_hook);
    return rc;
}
