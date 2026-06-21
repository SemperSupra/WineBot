; dialog_watcher.ahk — Selective dialog closer
;
; Closes only unwanted confirmation/error popups. Leaves full file dialogs
; ("Save As", "Open") alone so the AHK pipe dialog (dialog_replacement.ahk)
; can serve as the replacement interaction surface.
;
; What it closes:
;   - "Notepad" (small 300x84 "Save changes?" confirmation)    → Send Esc
;   - "Error" dialogs                                           → Send Enter
;   - "Warning" dialogs                                         → Send Enter
;   - "Assertion Failed"                                        → Send Enter
;
; What it leaves alone:
;   - "Save As" (full file browser)
;   - "Open" (full file browser)
;   - "WineBot Save Dialog" (our AHK replacement)
;
; Launch: POST /apps/run {"path":"ahk","args":"C:/automation/core/dialog_watcher.ahk","detach":true}

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetTitleMatchMode, 3  ; exact match only

SetTimer, Watch, 500
return

Watch:
    ; Small "Save changes?" confirmation dialog (Wine Notepad)
    if (WinExist("Notepad")) {
        WinGetPos, , , w, h, Notepad
        if (w <= 400 and h <= 120) {
            WinActivate, Notepad
            Send, {Escape}
        }
    }
    ; Error/assertion dialogs
    if (WinExist("Error")) {
        WinActivate, Error
        Send, {Enter}
    }
    if (WinExist("Warning")) {
        WinActivate, Warning
        Send, {Enter}
    }
    ; Safety: stale "Invalid character" from bad saves in prior sessions
    SetTitleMatchMode, 2
    if (WinExist("Invalid character")) {
        WinActivate
        Send, {Enter}
    }
    SetTitleMatchMode, 3
return
