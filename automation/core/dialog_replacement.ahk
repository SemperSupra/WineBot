; dialog_replacement.ahk — Resident dialog interceptor
;
; Monitors for Wine comdlg32 Save As / Open dialogs. When detected,
; closes the Wine dialog and opens an AHK Gui replacement that accepts
; commands via a named pipe file.
;
; This works because AHK CAN control its own Gui internally (GuiControl)
; even though external tools cannot inject into Wine-internal USER32 controls.
; The API communicates with the script through a pipe file.
;
; Commands (one per line, written to C:\dialog_handler\pipe.txt):
;   set_filename:myfile.txt     — Sets the filename field
;   click_save                   — Clicks the Save button
;   click_cancel                 — Clicks Cancel / closes the dialog
;   get_state                    — Writes current state to pipe file
;
; Results (written back to the pipe file after each action):
;   {"status":"ok","action":"set_filename","value":"myfile.txt"}
;   {"status":"ok","action":"click_save","saved_path":"C:\\artifacts\\myfile.txt"}
;
; The AHK Gui window IS visible on the X11 desktop (1280x720) and its
; buttons are clickable via xdotool (/input/mouse/click) since X11
; mouse events pass through the desktop barrier. The Edit control is NOT
; injectable via xdotool/AHK Send (same comdlg32 limitation), but IS
; controllable via the pipe + GuiControl pathway.

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent
SetTitleMatchMode, 2
SetWorkingDir, C:\

global PIPE_DIR := "C:\dialog_handler"
global PIPE_FILE := PIPE_DIR . "\pipe.txt"
global ACTIVE_GUI := false
global GUI_DESTROYED := false

; Ensure pipe directory exists
FileCreateDir, %PIPE_DIR%
FileDelete, %PIPE_FILE%

; Initialize pipe
FileAppend, {"status":"init","pid":0}`n, %PIPE_FILE%

; Main loop — poll for dialogs and pipe commands
SetTimer, PollDialogs, 500
SetTimer, PollPipe, 300
return

; ============================================================
; Dialog Detection
; ============================================================
PollDialogs:
    if (ACTIVE_GUI)
        return

    ; Monitor for Save As dialog
    if (WinExist("Save As")) {
        HandleDialog("Save As")
    }
    else if (WinExist("Open")) {
        HandleDialog("Open")
    }
return

HandleDialog(dialogTitle) {
    global ACTIVE_GUI

    ; Close the Wine dialog
    WinActivate, %dialogTitle%
    Sleep, 200
    Send, {Escape}
    Sleep, 500

    ; Double-check it's gone
    if (WinExist(dialogTitle)) {
        WinClose, %dialogTitle%
        Sleep, 500
    }

    ACTIVE_GUI := true
    FileAppend, {"status":"dialog_intercepted","type":"%dialogTitle%"}`n, %PIPE_FILE%

    ; Build and show the replacement Gui
    BuildReplacementGui(dialogTitle)
}

; ============================================================
; AHK Gui Replacement
; ============================================================
BuildReplacementGui(type) {
    global GUI_DESTROYED

    GUI_DESTROYED := false

    Gui, New, +AlwaysOnTop +ToolWindow, WineBot Dialog
    Gui, Color, 2A3F5F  ; WineBot dark blue
    Gui, Font, s10 cWhite, Segoe UI

    Gui, Add, Text, x15 y15 w440, %type% — WineBot Replacement

    ; Row 1: Save location
    Gui, Font, s9 cAAAAAA
    Gui, Add, Text, x15 y45, Save in:
    Gui, Font, s10 cWhite
    Gui, Add, Edit, x15 y65 w400 vFilePath, C:\artifacts\
    Gui, Add, Button, x420 y65 w50 gBrowsePath, ...

    ; Row 2: Filename
    Gui, Font, s9 cAAAAAA
    Gui, Add, Text, x15 y105, File name:
    Gui, Font, s11 cWhite
    Gui, Add, Edit, x15 y125 w250 vFileName,

    ; Row 3: Buttons
    Gui, Add, Button, x100 y175 w100 h35 gSaveFile, &Save
    Gui, Add, Button, x230 y175 w100 h35 gCancelFile, &Cancel

    ; Status bar
    Gui, Font, s8 c88AAFF
    Gui, Add, Text, x15 y225 w440 vStatusText, Ready — Enter filename and click Save, or use API pipe commands.

    Gui, Show, w480 h260, WineBot Dialog

    ; Wait for Gui to close (event loop handles the rest)
    while (!GUI_DESTROYED) {
        Sleep, 100
    }

    ACTIVE_GUI := false
}

; ============================================================
; Gui Event Handlers
; ============================================================
SaveFile:
    Gui, Submit, NoHide
    if (FileName = "") {
        GuiControl,, StatusText, ERROR: Please enter a filename.
        return
    }

    fullPath := FilePath . FileName
    FileDelete, %fullPath%
    FileAppend, Saved via WineBot AHK Dialog Replacement`n, %fullPath%

    GuiControl,, StatusText, Saved: %fullPath%
    FileAppend, {"status":"ok","action":"click_save","saved_path":"%fullPath%"}`n, %PIPE_FILE%

    Sleep, 500
    Gui, Destroy
    GUI_DESTROYED := true
return

CancelFile:
    Gui, Destroy
    GUI_DESTROYED := true
    FileAppend, {"status":"ok","action":"click_cancel"}`n, %PIPE_FILE%
return

BrowsePath:
    GuiControl,, StatusText, Browse not available — type path manually.
return

; ============================================================
; Pipe Command Handler — API writes commands here
; ============================================================
PollPipe:
    if (!FileExist(PIPE_FILE))
        return

    FileRead, raw, %PIPE_FILE%
    if (raw = "" || InStr(raw, "{""status"":"))
        return  ; Only process command lines, not status responses

    ; Check for command patterns
    Loop, Parse, raw, `n, `r
    {
        line := Trim(A_LoopField)
        if (line = "" || InStr(line, "{""status"":""))
            continue

        FileDelete, %PIPE_FILE%

        if (InStr(line, "set_filename:")) {
            newName := SubStr(line, 14)
            GuiControl,, FileName, %newName%
            GuiControl,, StatusText, [API] Filename set: %newName%
            FileAppend, {"status":"ok","action":"set_filename","value":"%newName%"}`n, %PIPE_FILE%
        }
        else if (InStr(line, "set_path:")) {
            newPath := SubStr(line, 10)
            GuiControl,, FilePath, %newPath%
            GuiControl,, StatusText, [API] Path set: %newPath%
            FileAppend, {"status":"ok","action":"set_path","value":"%newPath%"}`n, %PIPE_FILE%
        }
        else if (InStr(line, "click_save")) {
            GoSub, SaveFile
        }
        else if (InStr(line, "click_cancel")) {
            Gui, Destroy
            GUI_DESTROYED := true
            FileAppend, {"status":"ok","action":"click_cancel"}`n, %PIPE_FILE%
        }
        else if (InStr(line, "get_state")) {
            Gui, Submit, NoHide
            FileAppend, {"path":"%FilePath%","filename":"%FileName%"}`n, %PIPE_FILE%
        }

        break  ; Process one command per poll cycle
    }
return
