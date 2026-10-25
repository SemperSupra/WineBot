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
#define LIFETIME_POLL_MS 500
#define CONTROL_STOP_MESSAGE (WM_APP + 17)

struct control_context {
    HANDLE input;
    DWORD owner_thread;
};

/* Only private stdin from the fixed-owner Wine process. This separate
 * blocking reader avoids dependence on PeekNamedPipe on Wine. All event
 * hooks and dispatch remain on the Win32 message-pump thread.
 */
static DWORD WINAPI control_reader(LPVOID param) {
    const struct control_context *control = (const struct control_context *)param;
    char command = 0;
    DWORD received = 0;
    BOOL ok = ReadFile(control->input, &command, 1, &received, NULL);
    DWORD invalid = (ok && received == 1 && command == 'Q') ? 0 : 1;
    PostThreadMessageW(control->owner_thread, CONTROL_STOP_MESSAGE, invalid, 0);
    return 0;
}
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
    UINT_PTR timer_id = 0;
    HANDLE control = GetStdHandle(STD_INPUT_HANDLE);
    HANDLE reader = NULL;
    struct control_context reader_context;
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
    /* Materialize the message queue before a possible immediate EOF. */
    PeekMessageW(&message, NULL, WM_APP, WM_APP, PM_NOREMOVE);
    reader_context.input = control;
    reader_context.owner_thread = GetCurrentThreadId();
    reader = CreateThread(NULL, 0, control_reader, &reader_context, 0, NULL);
    if (!reader) {
        emit("unsupported", 0);
        rc = 4;
        goto done;
    }
    timer_id = SetTimer(NULL, 0, LIFETIME_POLL_MS, NULL);
    if (!timer_id) {
        emit("unsupported", 0);
        rc = 4;
        goto done;
    }
    emit("ready", 0);
    while ((message_result = GetMessageW(&message, NULL, 0, 0)) > 0) {
        if (message.message == CONTROL_STOP_MESSAGE) {
            rc = message.wParam ? 4 : 0;
            break;
        }
        if (message.message == WM_TIMER && message.wParam == timer_id) {
            if ((DWORD)(GetTickCount() - started) >= MAX_LIFETIME_MS) {
                rc = 3; /* Expiration is not ordinary EOF. */
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
done:
    if (timer_id)
        KillTimer(NULL, timer_id);
    if (reader)
        CloseHandle(reader);
    if (foreground_hook)
        UnhookWinEvent(foreground_hook);
    if (events_hook)
        UnhookWinEvent(events_hook);
    return rc;
}
