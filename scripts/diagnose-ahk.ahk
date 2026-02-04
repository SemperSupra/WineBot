; diagnose-ahk.ahk
; Automates Notepad to verify keyboard input via AutoHotkey

Run, notepad.exe
WinWaitActive, Untitled - Notepad, , 10
if ErrorLevel
{
    FileAppend, ERROR: Notepad window not found`n, *
    ExitApp, 1
}

Send, AHK Test Input
Sleep, 500
Send, ^s
WinWaitActive, Save As, , 5
if ErrorLevel
{
    FileAppend, ERROR: Save As dialog not found`n, *
    ExitApp, 1
}

; Save to C:\ahk_test.txt
Send, C:\ahk_test.txt
Sleep, 500
Send, {Enter}
Sleep, 1000

; Verify file exists? AHK can check file exist.
if FileExist("C:\ahk_test.txt")
{
    FileAppend, SUCCESS: AHK test passed.`n, *
    ExitApp, 0
}
else
{
    FileAppend, FAILURE: File not created.`n, *
    ExitApp, 1
}
