@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo Python Launcher "py" was not found.
    echo Python Launcher "py" nebyl nalezen.
    echo.
    echo Building an EXE is optional. Run_Bambu_RFID_Writer.bat still works when Python 3 is installed.
    echo Vytvoreni EXE je volitelne. Run_Bambu_RFID_Writer.bat funguje s nainstalovanym Pythonem 3.
    pause
    exit /b 1
)

set "BUILD_ENV=%~dp0.build-tools"
set "BUILD_PY=%BUILD_ENV%\Scripts\python.exe"

if not exist "%BUILD_PY%" (
    echo Creating a local build environment...
    echo Vytvarim lokalni prostredi pro sestaveni...
    py -3 -m venv "%BUILD_ENV%"
    if errorlevel 1 goto :build_environment_failed
)

"%BUILD_PY%" -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller into the local build environment...
    echo Instaluji PyInstaller do lokalniho prostredi pro sestaveni...
    "%BUILD_PY%" -m pip install --disable-pip-version-check "pyinstaller>=6,<7"
    if errorlevel 1 goto :pyinstaller_install_failed
)

echo Building Bambu_RFID_Writer.exe...
echo Vytvarim Bambu_RFID_Writer.exe...
"%BUILD_PY%" "%~dp0tools\build_exe.py"
if errorlevel 1 goto :build_failed

echo.
echo Done / Hotovo: %~dp0dist\Bambu_RFID_Writer.exe
echo The local .build-tools folder is only used for future EXE builds.
echo Slozka .build-tools slouzi pouze pro dalsi sestaveni EXE.
pause
exit /b 0

:build_environment_failed
echo Failed to create the local build environment.
echo Nepodarilo se vytvorit lokalni prostredi pro sestaveni.
pause
exit /b 1

:pyinstaller_install_failed
echo PyInstaller installation failed. Check the internet connection and pip output above.
echo Instalace PyInstalleru selhala. Zkontrolujte internetove pripojeni a vystup pip vyse.
pause
exit /b 1

:build_failed
echo EXE build failed.
echo Vytvoreni EXE selhalo.
pause
exit /b 1
