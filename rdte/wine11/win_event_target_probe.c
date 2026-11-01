/* SPDX-License-Identifier: MIT
 * Synthetic-only target-correlation comparator: no authority or actuation.
 * HWND, PID and thread IDs are consulted only internally; never printed.
 * The emitted fixture token is NOT secret, authenticated, or authorized.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

#define FIXTURE_CLASS L"WB_RDTE_WINDOW"
#define LIMIT_EVENTS 128
#define MAX_TARGETS 16
#define CONTROL_STOP (WM_APP + 18)

struct target {
    HWND hwnd;
    DWORD pid;
    DWORD thread_id;
    unsigned int epoch;
    BOOL active;
};
struct stop_context {
    HANDLE input;
    DWORD owner_thread;
};
static struct target targets[MAX_TARGETS];
static unsigned int next_epoch=0;
static unsigned int sequence=0;
static int overflow=0;

static void emit_event(const char *kind, unsigned int epoch) {
    if (sequence >= LIMIT_EVENTS) {
        if (!overflow) {
            overflow=1;
            printf("{\"schema\":\"winebot.target.hint.rdte.v0\",\"kind\":\"overflow\",\"sequence\":129,\"target_ref\":\"\",\"target_epoch\":0}\n");
            fflush(stdout);
            PostQuitMessage(6);
        }
        return;
    }
    printf("{\"schema\":\"winebot.target.hint.rdte.v0\",\"kind\":\"%s\",\"sequence\":%u,\"target_ref\":\"fixture-target-%u\",\"target_epoch\":%u}\n",
           kind,++sequence,epoch,epoch);
    fflush(stdout);
}
static void emit_ready(void) {
    printf("{\"schema\":\"winebot.target.hint.rdte.v0\",\"kind\":\"ready\",\"sequence\":0,\"target_ref\":\"\",\"target_epoch\":0}\n");
    fflush(stdout);
}
static int find_target(HWND hwnd) {
    int i;
    for (i=0;i<MAX_TARGETS;i++)
        if (targets[i].active && targets[i].hwnd==hwnd) return i;
    return -1;
}
static int allocate_target(HWND hwnd, DWORD pid, DWORD thread_id) {
    int i;
    for (i=0;i<MAX_TARGETS;i++) {
        if (!targets[i].active) {
            if (next_epoch==0xffffffffU) return -1;
            targets[i].hwnd=hwnd;
            targets[i].pid=pid;
            targets[i].thread_id=thread_id;
            targets[i].epoch=++next_epoch;
            targets[i].active=TRUE;
            return i;
        }
    }
    return -1;
}
static DWORD WINAPI control_reader(LPVOID arg) {
    const struct stop_context *c=(const struct stop_context *)arg;
    char command=0;
    DWORD received=0;
    BOOL ok=ReadFile(c->input,&command,1,&received,NULL);
    WPARAM invalid=!(ok && received==1 && command=='Q');
    PostThreadMessageW(c->owner_thread,CONTROL_STOP,invalid,0);
    return 0;
}
#ifndef CHILDID_SELF
#define CHILDID_SELF 0
#endif
static void CALLBACK on_event(HWINEVENTHOOK hook,DWORD event,HWND hwnd,
                              LONG object_id,LONG child_id,
                              DWORD event_thread,DWORD event_time) {
    WCHAR class_name[64];
    DWORD pid=0;
    DWORD thread_id=0;
    int i;
    const char *kind=NULL;
    (void)hook;
    (void)event_thread;
    (void)event_time;
    if (!hwnd || object_id!=OBJID_WINDOW || child_id!=CHILDID_SELF) return;
    i=find_target(hwnd);
    /* A destroy may be delivered after the HWND no longer supports
     * GetClassName/GetWindowThreadProcessId. Only a previously observed
     * fixture target may be invalidated; do not create an identity here.
     */
    if (event==EVENT_OBJECT_DESTROY) {
        if (i>=0) {
            emit_event("destroy",targets[i].epoch);
            targets[i].active=FALSE;
        }
        return;
    }
    if (!GetClassNameW(hwnd,class_name,64) ||
        lstrcmpW(class_name,FIXTURE_CLASS)!=0) return;
    thread_id=GetWindowThreadProcessId(hwnd,&pid);
    if (!thread_id || !pid) return;
    if (i>=0 && (targets[i].pid!=pid || targets[i].thread_id!=thread_id)) {
        emit_event("gap",targets[i].epoch);
        targets[i].active=FALSE;
        PostQuitMessage(6);
        return;
    }
    if (i<0) {
        i=allocate_target(hwnd,pid,thread_id);
        if (i<0) {
            emit_event("overflow",0);
            PostQuitMessage(6);
            return;
        }
    }
    switch(event) {
        case EVENT_OBJECT_CREATE: kind="create"; break;
        case EVENT_OBJECT_SHOW: kind="show"; break;
        case EVENT_OBJECT_HIDE: kind="hide"; break;
        case EVENT_OBJECT_LOCATIONCHANGE: kind="location"; break;
        case EVENT_OBJECT_FOCUS: kind="focus"; break;
        case EVENT_SYSTEM_FOREGROUND: kind="foreground"; break;
        default: return;
    }
    emit_event(kind,targets[i].epoch);
}
int main(void) {
    HWINEVENTHOOK h1=NULL;
    HWINEVENTHOOK h2=NULL;
    HANDLE control=GetStdHandle(STD_INPUT_HANDLE);
    HANDLE reader=NULL;
    struct stop_context c;
    MSG msg;
    BOOL message_result;
    UINT_PTR timer;
    DWORD started=GetTickCount();
    int rc=0;
    if (control==INVALID_HANDLE_VALUE || GetFileType(control)!=FILE_TYPE_PIPE)
        return 4;
    h1=SetWinEventHook(EVENT_OBJECT_CREATE,EVENT_OBJECT_LOCATIONCHANGE,NULL,
                       on_event,0,0,WINEVENT_OUTOFCONTEXT|WINEVENT_SKIPOWNPROCESS);
    h2=SetWinEventHook(EVENT_SYSTEM_FOREGROUND,EVENT_SYSTEM_FOREGROUND,NULL,
                       on_event,0,0,WINEVENT_OUTOFCONTEXT|WINEVENT_SKIPOWNPROCESS);
    if (!h1 || !h2) {rc=4;goto done;}
    PeekMessageW(&msg,NULL,WM_APP,WM_APP,PM_NOREMOVE);
    c.input=control;
    c.owner_thread=GetCurrentThreadId();
    reader=CreateThread(NULL,0,control_reader,&c,0,NULL);
    if (!reader) {rc=4;goto done;}
    timer=SetTimer(NULL,0,500,NULL);
    if (!timer) {rc=4;goto done;}
    emit_ready();
    while ((message_result=GetMessageW(&msg,NULL,0,0))>0) {
        if (msg.message==CONTROL_STOP) {rc=msg.wParam?4:0;break;}
        if (msg.message==WM_TIMER && msg.wParam==timer) {
            if ((DWORD)(GetTickCount()-started)>=120000UL) {rc=3;break;}
            continue;
        }
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (message_result<0) rc=4;
    if (overflow) rc=6;
    KillTimer(NULL,timer);
done:
    if (reader) CloseHandle(reader);
    if (h2) UnhookWinEvent(h2);
    if (h1) UnhookWinEvent(h1);
    return rc;
}
