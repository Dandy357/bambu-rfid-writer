@echo off
setlocal
cd /d "%~dp0"

where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "%~dp0Bambu_RFID_Writer.pyw"
    exit /b 0
)

where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "%~dp0Bambu_RFID_Writer.pyw"
    exit /b 0
)

echo Python nebyl nalezen. Je nutne nainstalovat Python 3 a zvolit "Add Python to PATH".
echo Python was not found. Install Python 3 and select "Add Python to PATH".
pause
exit /b 1

