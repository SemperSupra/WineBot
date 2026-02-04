; diagnose-autoit.au3
; Automates Notepad to verify keyboard input via AutoIt

Run("notepad.exe")
WinWaitActive("[CLASS:Notepad]", "", 10)
If WinActive("[CLASS:Notepad]") Then
    Send("AutoIt Test Input")
    Sleep(500)
    Send("^s")
    WinWaitActive("Save As", "", 5)
    If WinActive("Save As") Then
        Send("C:\autoit_test.txt")
        Sleep(500)
        Send("{ENTER}")
        Sleep(1000)
        
        If FileExists("C:\autoit_test.txt") Then
            ConsoleWrite("SUCCESS: AutoIt test passed." & @CRLF)
            Exit(0)
        Else
            ConsoleWrite("FAILURE: File not created." & @CRLF)
            Exit(1)
        EndIf
    Else
        ConsoleWrite("ERROR: Save As dialog not found" & @CRLF)
        Exit(1)
    EndIf
Else
    ConsoleWrite("ERROR: Notepad window not found" & @CRLF)
    Exit(1)
EndIf
