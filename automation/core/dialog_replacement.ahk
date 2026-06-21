; dialog_replacement.ahk — AHK Save Dialog + comdlg32 Interceptor
;
; Dual mode: intercepts Wine Save As dialogs AND accepts pipe commands.
;
; Launch: POST /apps/run {"path":"ahk","args":"C:/dr.ahk","detach":true}
;
; Behavior:
;   1. Polls for Wine "Save As" dialog every 500ms
;   2. When detected: WinClose, then open AHK replacement Gui
;   3. Accepts pipe commands via C:\dialog_handler\pipe.txt
;
; Pipe commands:
;   open_gui              Show the AHK dialog (even without Wine dialog)
;   set_filename:name.txt  Set filename
;   click_save             Save file and exit
;   click_cancel           Cancel and exit
;
; Responses: {"status":"ready|gui_opened|set_ok|saved|cancelled|intercepted|error:..."}

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetTitleMatchMode, 2
SetWorkingDir, C:\

global PIPE := "C:\dialog_handler\pipe.txt"
global ARTIFACTS := "C:/artifacts/"
global gFileName := "untitled.txt"
global gGuiOpen := false

FileCreateDir, C:\dialog_handler
FileDelete, %PIPE%
Sleep, 150
FileAppend, {"status":"ready"}`n, %PIPE%

; Dual timers: poll pipe commands, poll Wine dialogs
SetTimer, PollPipe, 300
SetTimer, PollDialogs, 500
SetTimer, SelfDestruct, -180000
return

SelfDestruct:
    FileDelete, %PIPE%
    ExitApp 0
return

; ---- INTERCEPT WINE DIALOGS ----
PollDialogs:
    if (gGuiOpen)
        return
    if (WinExist("Save As")) {
        WinClose, Save As
        Sleep, 300
        if (WinExist("Save As")) {
            WinActivate, Save As
            Send, {Escape}
            Sleep, 300
        }
        FileAppend, {"status":"intercepted","dialog":"Save As"}`n, %PIPE%
        OpenReplacementGui()
    }
return

; ---- PIPE COMMAND HANDLER ----
PollPipe:
    if (!FileExist(PIPE))
        return
    FileRead, raw, %PIPE%
    if (raw = "" or InStr(raw, """status"""))
        return

    FileDelete, %PIPE%
    cmd := Trim(raw, " `r`n`t")

    if (InStr(cmd, "open_gui")) {
        if (!gGuiOpen) {
            OpenReplacementGui()
        }
    }
    else if (InStr(cmd, "set_filename:")) {
        name := Trim(SubStr(cmd, 14), " `r`n`t")
        if (name != "") {
            gFileName := name
            FileAppend, {"status":"set_ok"}`n, %PIPE%
        } else {
            FileAppend, {"status":"error:empty_name"}`n, %PIPE%
        }
    }
    else if (InStr(cmd, "click_save")) {
        if (gFileName = "" or gFileName = "untitled.txt") {
            FileAppend, {"status":"error:no_filename_set"}`n, %PIPE%
            return
        }
        fullPath := ARTIFACTS . gFileName
        FileDelete, %fullPath%
        FileAppend, Saved via AHK Pipe Protocol`n`nFile: %gFileName%`n, %fullPath%
        Sleep, 500
        gGuiOpen := false
        Gui, Destroy
        FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
        Sleep, 200
        ExitApp 0
    }
    else if (InStr(cmd, "click_cancel")) {
        gGuiOpen := false
        Gui, Destroy
        FileAppend, {"status":"cancelled"}`n, %PIPE%
        ExitApp 1
    }
return

OpenReplacementGui() {
    global gGuiOpen
    Gui, New, +AlwaysOnTop +ToolWindow, WineBot Save Dialog
    Gui, Color, 1A2340
    Gui, Font, s11 cFFFFFF, Segoe UI
    Gui, Add, Text, x15 y10 w360, Save File
    Gui, Add, Edit, x15 y40 w360 vDlgFileName, % gFileName
    Gui, Font, s10 cFFFFFF
    Gui, Add, Button, x100 y80 w100 h30 gBtnSave, Save
    Gui, Add, Button, x230 y80 w100 h30 gBtnCancel, Cancel
    Gui, Show, w400 h130, WineBot Save Dialog
    gGuiOpen := true
    FileAppend, {"status":"gui_opened"}`n, %PIPE%
}

BtnSave:
    Gui, Submit, NoHide
    fullPath := ARTIFACTS . DlgFileName
    FileDelete, %fullPath%
    FileAppend, Saved via AHK Button`n`nFile: %DlgFileName%`n, %fullPath%
    Sleep, 500
    gGuiOpen := false
    Gui, Destroy
    FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
    ExitApp 0

BtnCancel:
    gGuiOpen := false
    Gui, Destroy
    FileAppend, {"status":"cancelled"}`n, %PIPE%
    ExitApp 1
