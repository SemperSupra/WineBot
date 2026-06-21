; save_dialog_replacement.ahk
; Replaces Wine's comdlg32 Save As dialog with an AHK Gui that has REAL,
; injectable controls. The AHK Gui Edit field maps to an actual X11 window
; that /input/key and xdotool can type into.
;
; Usage (from /run/ahk):
;   RunWait, C:\automation\core\save_dialog_replacement.ahk "default_filename.txt"
;
; Behavior:
;   1. Monitors for Wine "Save As" dialog for up to 10 seconds
;   2. When found, sends Escape to close it
;   3. Opens AHK Gui "WineBot Save As" with filename field and Save/Cancel
;   4. Waits for user/agent to fill filename and click Save or press Enter
;   5. Writes the actual file to C:\artifacts\ (or returns path via exit code)
;
; Communication via pipe file for API-driven input:
;   The script watches C:\artifacts\save_dialog_pipe.txt for commands.
;   Commands:
;     set_text:<filename>   - Sets the Edit control text
;     click_save            - Clicks Save button
;     click_cancel          - Clicks Cancel

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetTitleMatchMode, 2
SetWorkingDir, C:\

global SAVE_PATH := "C:\artifacts"
global PIPE_FILE := "C:\artifacts\save_dialog_pipe.txt"
global GUI_WIDTH := 500
global GUI_HEIGHT := 200
global GUI_TITLE := "WineBot Save As"
global FILENAME := ""
global CANCELLED := false

; Get default filename from command line
if (%0% >= 1) {
    FILENAME := %1%
}

; Most of the script runs as a Gui event loop after dialog detection.
DetectAndReplace()

; ============================================================
DetectAndReplace() {
    global

    ; Wait for Wine Save As dialog
    Loop, 60 {
        if (WinExist("Save As")) {
            break
        }
        Sleep, 500
    }

    if (!WinExist("Save As")) {
        ; Dialog never appeared — maybe already handled or app closed
        FileAppend, {"status":"no_dialog"}`n, %PIPE_FILE%
        ExitApp 0
    }

    ; Read dialog context (optional: what app opened it, what file filters exist)
    ; For now, just close it
    WinClose, Save As
    Sleep, 500

    ; If still there, force-kill with Escape
    if (WinExist("Save As")) {
        WinActivate, Save As
        Sleep, 200
        Send, {Escape}
        Sleep, 300
    }

    ; Build AHK Gui replacement
    BuildGui()
}

BuildGui() {
    global

    Gui, New, +AlwaysOnTop +ToolWindow, %GUI_TITLE%
    Gui, Color, F0F0F0
    Gui, Font, s10, Segoe UI

    ; File path section
    Gui, Add, GroupBox, x10 y10 w%GUI_WIDTH% h50, Save Location
    Gui, Add, Text, x20 y35, Path:
    Gui, Add, Edit, x60 y32 w370 vFilePath, C:\artifacts\
    Gui, Add, Button, x440 y30 w50 gBrowseFile, ...

    ; Filename section
    Gui, Add, GroupBox, x10 y70 w%GUI_WIDTH% h50, File Name
    Gui, Add, Text, x20 y95, Name:
    Gui, Add, Edit, x70 y92 w360 vFileName, %FILENAME%

    ; Buttons
    Gui, Add, Button, x130 y140 w100 h30 gSaveFile, &Save
    Gui, Add, Button, x260 y140 w100 h30 gCancelDialog, &Cancel

    ; Status bar
    Gui, Add, Text, x10 y180 w%GUI_WIDTH% vStatusText, Ready. Type a filename and click Save.

    ; Timer to check pipe file for API commands
    SetTimer, CheckPipe, 300

    ; Show the Gui
    Gui, Show, w%GUI_WIDTH% h%GUI_HEIGHT%, %GUI_TITLE%

    ; Wait for the Gui to close
    WinWaitClose, %GUI_TITLE%

    ; Cleanup
    SetTimer, CheckPipe, Off
    FileDelete, %PIPE_FILE%

    if (CANCELLED) {
        FileAppend, {"status":"cancelled"}`n, %PIPE_FILE%
        ExitApp 1
    } else {
        FileAppend, {"status":"saved","path":""%SAVE_PATH%"","filename":""%FILENAME%""}`n, %PIPE_FILE%
        ExitApp 0
    }
}

; ============================================================
; Event handlers
; ============================================================

SaveFile:
    Gui, Submit, NoHide
    if (FileName = "") {
        GuiControl,, StatusText, ERROR: Please enter a filename.
        return
    }

    ; Build full path
    fullPath := FilePath . FileName

    ; Create the file
    FileDelete, %fullPath%
    FileAppend, Saved via AHK Gui replacement dialog`n, %fullPath%
    if (ErrorLevel) {
        GuiControl,, StatusText, ERROR: Could not write file.
        return
    }

    SAVE_PATH := fullPath
    FILENAME := FileName
    FileAppend, {"status":"saved","path":"%fullPath%"}`n, %PIPE_FILE%
    Gui, Destroy
return

CancelDialog:
    CANCELLED := true
    Gui, Destroy
return

BrowseFile:
    MsgBox, Browse not implemented. Type the full path in the Path field.
return

; ============================================================
; Pipe command handler — accepts API commands
; ============================================================
CheckPipe:
    if (!FileExist(PIPE_FILE))
        return

    FileRead, raw, %PIPE_FILE%
    if (raw = "")
        return

    FileDelete, %PIPE_FILE%

    Loop, Parse, raw, `n, `r
    {
        line := Trim(A_LoopField)
        if (line = "")
            continue

        if (InStr(line, "set_filename:")) {
            newName := SubStr(line, 14)
            GuiControl,, FileName, %newName%
            GuiControl,, StatusText, Filename set via API: %newName%
        }
        else if (InStr(line, "set_path:")) {
            newPath := SubStr(line, 10)
            GuiControl,, FilePath, %newPath%
            GuiControl,, StatusText, Path set via API: %newPath%
        }
        else if (InStr(line, "click_save")) {
            GoSub, SaveFile
        }
        else if (InStr(line, "click_cancel")) {
            GoSub, CancelDialog
        }
        else if (InStr(line, "get_state")) {
            Gui, Submit, NoHide
            FileAppend, {"path":""%FilePath%"","filename":""%FileName%""}`n, %PIPE_FILE%
        }
    }
return
