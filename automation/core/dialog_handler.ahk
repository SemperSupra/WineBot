; dialog_handler.ahk
; Resident AHK script that monitors Wine comdlg32 dialogs and sets text using
; the Windows API SetWindowTextW directly (bypasses Send/ControlSetText).
;
; Strategy: Poll for Save As / Open dialogs every 500ms. When found,
; use DllCall("user32\SetWindowTextW", ...) to set the filename field text.
;
; Usage: ahk dialog_handler.ahk <pipe_path>
; Commands are read from a named pipe file: one JSON command per line.
; {"action":"set_filename","dialog_title":"Save As","text":"C:/path/file.txt"}
; {"action":"click_button","dialog_title":"Save As","button_label":"&Save"}
;
; Stays resident until receiving {"action":"exit"} or the pipe file is deleted.

#NoTrayIcon
#NoEnv
#SingleInstance Force
#Persistent

global PIPE_PATH := ""
global LAST_POLL := A_TickCount

; Parse command line
Loop, %0%
{
    param := %A_Index%
    if (A_Index = 1)
        PIPE_PATH := param
}

if (PIPE_PATH = "")
{
    FileAppend, ERROR: No pipe path provided`n, *
    ExitApp 1
}

; Ensure pipe file exists
FileAppend, , %PIPE_PATH%

SetTimer, PollCommands, 500
SetTimer, CheckDialogs, 500
return

PollCommands:
{
    FileRead, raw, %PIPE_PATH%
    if (raw = "")
        return

    ; Clear the file after reading
    FileDelete, %PIPE_PATH%

    Loop, Parse, raw, `n, `r
    {
        line := A_LoopField
        if (line = "")
            continue

        ; Very simple JSON parsing — just extract fields with regex
        RegExMatch(line, """action"":\s*""([^""]+)""", action_match)
        action := action_match1

        RegExMatch(line, """dialog_title"":\s*""([^""]+)""", title_match)
        dialog_title := title_match1

        RegExMatch(line, """text"":\s*""([^""]+)""", text_match)
        text := text_match1

        RegExMatch(line, """button_label"":\s*""([^""]+)""", btn_match)
        button_label := btn_match1

        if (action = "exit")
        {
            FileAppend, {"status":"exiting"}`n, %PIPE_PATH%
            ExitApp 0
        }

        if (action = "set_filename" and dialog_title != "" and text != "")
        {
            result := SetDialogFilename(dialog_title, text)
            FileAppend, {"status":"%result%"}`n, %PIPE_PATH%
        }

        if (action = "click_button" and dialog_title != "" and button_label != "")
        {
            result := ClickDialogButton(dialog_title, button_label)
            FileAppend, {"status":"%result%"}`n, %PIPE_PATH%
        }

        if (action = "list_dialogs")
        {
            list := ListDialogs()
            FileAppend, %list%`n, %PIPE_PATH%
        }
    }
}
return

CheckDialogs:
{
    ; Periodic health check — just ensure we're still alive
    LAST_POLL := A_TickCount
}
return

SetDialogFilename(dialogTitle, text)
{
    SetTitleMatchMode, 2
    WinWait, %dialogTitle%,, 3
    if (ErrorLevel)
        return "dialog_not_found"

    WinActivate, %dialogTitle%
    WinWaitActive, %dialogTitle%,, 2
    if (ErrorLevel)
        return "dialog_not_active"

    Sleep, 300

    ; Try DllCall(SetWindowTextW) on the Edit control
    ; First, get the dialog HWND
    hDlg := WinExist(dialogTitle)
    if (!hDlg)
        return "hwnd_not_found"

    ; Enumerate child windows to find the Edit control
    ; In Wine Save As, the filename field is typically:
    ;   - An Edit control inside a ComboBox (class "ComboBoxEx32" or "ComboBox")
    ;   - Or a direct Edit control

    ; Try: Find Edit control directly
    hEdit := DllCall("FindWindowExW", "Ptr", hDlg, "Ptr", 0, "Str", "Edit", "Ptr", 0, "Ptr")

    if (!hEdit)
    {
        ; Try: Find ComboBox, then Edit inside it
        hCombo := DllCall("FindWindowExW", "Ptr", hDlg, "Ptr", 0, "Str", "ComboBox", "Ptr", 0, "Ptr")
        if (hCombo)
            hEdit := DllCall("FindWindowExW", "Ptr", hCombo, "Ptr", 0, "Str", "Edit", "Ptr", 0, "Ptr")
    }

    if (!hEdit)
    {
        ; Try ComboBoxEx32
        hComboEx := DllCall("FindWindowExW", "Ptr", hDlg, "Ptr", 0, "Str", "ComboBoxEx32", "Ptr", 0, "Ptr")
        if (hComboEx)
            hEdit := DllCall("FindWindowExW", "Ptr", hComboEx, "Ptr", 0, "Str", "Edit", "Ptr", 0, "Ptr")
    }

    if (!hEdit)
    {
        ; Last resort: enumerate ALL child windows, find the first Edit
        EnumChildWindows(hDlg, "FindFirstEdit")
    }

    if (hEdit)
    {
        ; Set the text via SetWindowTextW
        DllCall("SetWindowTextW", "Ptr", hEdit, "Str", text)
        Sleep, 200

        ; Verify
        VarSetCapacity(buf, 512)
        DllCall("GetWindowTextW", "Ptr", hEdit, "Str", buf, "Int", 256)
        if (buf = text)
            return "ok"
        else
            return "text_verification_failed_set=[" text "] got=[" buf "]"
    }

    return "edit_control_not_found"
}

EnumChildWindows(hWnd, callbackName)
{
    ; This requires a callback — SKIP for now, use alternate approach
    return 0
}

ClickDialogButton(dialogTitle, buttonLabel)
{
    SetTitleMatchMode, 2
    WinWait, %dialogTitle%,, 3
    if (ErrorLevel)
        return "dialog_not_found"

    hDlg := WinExist(dialogTitle)
    if (!hDlg)
        return "hwnd_not_found"

    ; Find button by label
    hBtn := 0
    nextBtn := DllCall("FindWindowExW", "Ptr", hDlg, "Ptr", 0, "Str", "Button", "Ptr", 0, "Ptr")
    Loop, 20
    {
        if (!nextBtn)
            break

        VarSetCapacity(btnText, 256)
        DllCall("GetWindowTextW", "Ptr", nextBtn, "Str", btnText, "Int", 255)

        if (InStr(btnText, buttonLabel))
        {
            hBtn := nextBtn
            break
        }

        nextBtn := DllCall("FindWindowExW", "Ptr", hDlg, "Ptr", nextBtn, "Str", "Button", "Ptr", 0, "Ptr")
    }

    if (hBtn)
    {
        DllCall("SendMessageW", "Ptr", hBtn, "UInt", 0x00F5, "Ptr", 0, "Ptr", 0)  ; BM_CLICK
        return "ok"
    }

    return "button_not_found"
}

ListDialogs()
{
    result := "["
    WinGet, id, list,,, Program Manager
    Loop, %id%
    {
        this_id := id%A_Index%
        WinGetTitle, title, ahk_id %this_id%
        WinGetClass, cls, ahk_id %this_id%
        if (title != "" and (InStr(title, "Save") or InStr(title, "Open") or InStr(title, "Browse") or InStr(title, "File")))
        {
            if (result != "[")
                result .= ", "
            result .= "{""title"":""" title """,""class"":""" cls """}"
        }
    }
    result .= "]"
    return result
}
