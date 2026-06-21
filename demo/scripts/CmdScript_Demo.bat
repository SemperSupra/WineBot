@echo off
echo ============================================
echo   WineBot CMD Script - Programmatic Execution
echo ============================================
echo.
echo [Step 1] Creating output file...
echo CMD Script Output > C:\artifacts\CmdScript_Output.txt
echo Created via WineBot API >> C:\artifacts\CmdScript_Output.txt
echo.
echo [Step 2] Creating registry key via script...
reg add HKCU\Software\WineBotCmdScript /v ScriptValue /t REG_SZ /d Created_by_cmd_script /f
echo.
echo [Step 3] READING REGISTRY VALUE FROM PART 3...
echo --- Registry Query: HKCU\Software\WineBotDemoKey --- >> C:\artifacts\CmdScript_Output.txt
reg query HKCU\Software\WineBotDemoKey >> C:\artifacts\CmdScript_Output.txt
echo --- End Registry Query --- >> C:\artifacts\CmdScript_Output.txt
echo.
echo [Step 4] Verifying output file...
type C:\artifacts\CmdScript_Output.txt
echo ============================================
echo   CMD Script Complete
echo ============================================
