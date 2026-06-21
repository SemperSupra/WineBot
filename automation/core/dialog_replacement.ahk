; dialog_replacement.ahk — AHK Save Dialog with Pipe Protocol
;
; Launched via /apps/run with detach=true:
;   POST /apps/run {"path": "ahk", "args": "C:/automation/core/dialog_replacement.ahk", "detach": true}
;
; Protocol via C:\dialog_handler\pipe.txt:
;   open_gui                        — Shows the AHK Save dialog
;   set_filename:name.txt           — Sets filename in Edit control
;   click_save                       — Saves file and exits
;   click_cancel                     — Cancels and exits
;
; Responses (JSON-style, written back to pipe):
;   {"status":"ready"}       — Script started, waiting
;   {"status":"gui_opened"}   — Gui is visible
;   {"status":"set_ok"}       — Filename set successfully
;   {"status":"saved"}        — File saved to disk
;   {"status":"cancelled"}    — User/agent cancelled
;   {"status":"error:..."}     — Error with message

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetWorkingDir, C:\

global PIPE := "C:\dialog_handler\pipe.txt"
global FILE_ARTIFACTS := "C:/artifacts/"
global gFileName := "untitled.txt"

FileCreateDir, C:\dialog_handler
FileDelete, %PIPE%
Sleep, 200
FileAppend, {"status":"ready"}`n, %PIPE%

SetTimer, PollPipe, 300
SetTimer, SelfDestruct, -60000  ; 60s lifetime
return

SelfDestruct:
    FileDelete, %PIPE%
    ExitApp 0
return

PollPipe:
    if (!FileExist(PIPE))
        return
    FileRead, raw, %PIPE%
    if (raw = "" or InStr(raw, "ready") or InStr(raw, """status"""))
        return

    FileDelete, %PIPE%
    raw := Trim(raw, " `r`n`t")
    cmd := raw

    if (InStr(cmd, "open_gui")) {
        Gui, New, +AlwaysOnTop +ToolWindow, WineBot Save Dialog
        Gui, Color, 1A2340
        Gui, Font, s11 cFFFFFF, Segoe UI
        Gui, Add, Text, x15 y10 w360, Save File — AHK Dialog Replacement
        Gui, Add, Edit, x15 y40 w360 vDlgFileName, untitled.txt
        Gui, Font, s10 cFFFFFF
        Gui, Add, Button, x100 y80 w100 h30 gBtnSave, andSave
        Gui, Add, Button, x230 y80 w100 h30 gBtnCancel, andCancel
        Gui, Show, w400 h130, WineBot Save Dialog
        FileAppend, {"status":"gui_opened"}`n, %PIPE%
        return
    }

    if (InStr(cmd, "set_filename:")) {
        name := SubStr(cmd, 14)
        name := Trim(name, " `r`n`t")
        if (name != "") {
            gFileName := name
            GuiControl,, DlgFileName, %name%
            FileAppend, {"status":"set_ok"}`n, %PIPE%
        } else {
            FileAppend, {"status":"error:empty_name"}`n, %PIPE%
        }
        return
    }

    if (InStr(cmd, "click_save")) {
        if (gFileName = "" or gFileName = "untitled.txt") {
            FileAppend, {"status":"error:no_filename_set"}`n, %PIPE%
            return
        }
        fullPath := FILE_ARTIFACTS . gFileName
        FileDelete, %fullPath%
        FileAppend, Saved via AHK Pipe Protocol`n`nFile: %gFileName%`n, %fullPath%
        Sleep, 500
        Gui, Destroy
        FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
        Sleep, 300
        ExitApp 0
    }
        Gui, Destroy
        FileAppend, {"status":"cancelled"}`n, %PIPE%
        ExitApp 1
    }
return

BtnSave:
    Gui, Submit, NoHide
    fullPath := FILE_ARTIFACTS . DlgFileName
    FileDelete, %fullPath%
    FileAppend, Saved via AHK Button`n`nFile: %DlgFileName%`n, %fullPath%
    Sleep, 500
    Gui, Destroy
    FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
    ExitApp 0

BtnCancel:
    Gui, Destroy
    FileAppend, {"status":"cancelled"}`n, %PIPE%
    ExitApp 1
