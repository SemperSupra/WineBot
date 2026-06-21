; dialog_replacement.ahk — AHK Save Dialog with Pipe Protocol
;
; Launch: POST /apps/run {"path":"ahk","args":"C:/dr.ahk","detach":true}
;
; Commands (write to C:\dialog_handler\pipe.txt):
;   open_gui              Show the dialog
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

; Startup: ensure dir and pipe exist, both owned by current user
FileCreateDir, C:\dialog_handler
FileDelete, %PIPE%
Sleep, 150
FileAppend, {"status":"ready"}`n, %PIPE%

SetTimer, PollPipe, 300
SetTimer, SelfDestruct, -120000
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
    }
    else if (InStr(cmd, "set_filename:")) {
        name := Trim(SubStr(cmd, 14), " `r`n`t")
        if (name != "") {
            gFileName := name
            GuiControl,, DlgFileName, %name%
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
        Gui, Destroy
        FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
        Sleep, 200
        ExitApp 0
    }
    else if (InStr(cmd, "click_cancel")) {
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
    Gui, Destroy
    FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE%
    ExitApp 0

BtnCancel:
    Gui, Destroy
    FileAppend, {"status":"cancelled"}`n, %PIPE%
    ExitApp 1
