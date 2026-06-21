; dialog_watcher.ahk — Persistent dialog closer
;
; Monitors for Wine comdlg32 dialogs and closes them immediately.
; No state machine. No global variables. No race conditions.
; Just a pure watcher loop.
;
; Closes: Save As, Open, Error, Assertion Failed, etc.
;
; Launch: POST /apps/run {"path":"ahk","args":"C:/automation/core/dialog_watcher.ahk","detach":true}
; Kill:   pkill -f dialog_watcher

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetTitleMatchMode, 2 ; partial title match

SetTimer, Watch, 500
return

Watch:
    if (WinExist("Save As")) {
        WinClose, Save As
        Sleep, 200
        if (WinExist("Save As")) {
            WinActivate, Save As
            Send, {Escape}
        }
    }
    if (WinExist("Open")) {
        WinClose, Open
        Sleep, 200
        if (WinExist("Open")) {
            WinActivate, Open
            Send, {Escape}
        }
    }
    if (WinExist("Error")) {
        WinClose, Error
        Sleep, 200
        if (WinExist("Error")) {
            WinActivate, Error
            Send, {Enter}
        }
    }
return
