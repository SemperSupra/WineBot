; dialog_replacement.ahk — AHK Save Dialog (pipe-driven, no interception)
;
; This is NOT an interceptor. It is a standalone AHK Gui dialog that
; accepts commands via a pipe file. No Wine dialogs are triggered.
;
; Launch: POST /apps/run {"path":"ahk","args":"C:/dr.ahk","detach":true}
;
; Pipe commands (write to C:\dialog_handler\pipe.txt):
;   open_gui              Show the AHK dialog
;   set_filename:name.txt  Set filename
;   click_save             Save file and exit
;   click_cancel           Cancel and exit
;
; Responses: {"status":"ready|gui_opened|set_ok|saved|cancelled|error:..."}

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetWorkingDir, C:\

global PIPE := "C:\dialog_handler\pipe.txt"
global ARTIFACTS := "C:/artifacts/"
global gFileName := "untitled.txt"
global gGuiOpen := false

FileCreateDir, C:\dialog_handler
FileDelete, %PIPE%
Sleep, 150
FileAppend, {"status":"ready"}`n, %PIPE%

SetTimer, PollPipe, 300
SetTimer, SelfDestruct, -180000
return

SelfDestruct:
    FileDelete, %PIPE%
    ExitApp 0
return

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
            gGuiOpen := true
            Gui, New, +AlwaysOnTop +ToolWindow, WineBot Save Dialog
            Gui, Color, 1A2340
            Gui, Font, s11 cFFFFFF, Segoe UI
            Gui, Add, Text, x15 y10 w360, Save File
            Gui, Add, Edit, x15 y40 w360 vDlgFileName, % gFileName
            Gui, Font, s10 cFFFFFF
            Gui, Add, Button, x100 y80 w100 h30 gBtnSave, Save
            Gui, Add, Button, x230 y80 w100 h30 gBtnCancel, Cancel
            Gui, Show, w400 h130, WineBot Save Dialog
        }
        FileAppend, {"status":"gui_opened"}`n, %PIPE%
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
