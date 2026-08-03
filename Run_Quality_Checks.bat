@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if errorlevel 1 (
    echo Python Launcher "py" was not found.
    pause
    exit /b 1
)

py -3 -m unittest discover -s tests -q || goto :failed
py -3 tools\check_locales.py || goto :failed
py -3 tools\check_source_quality.py || goto :failed
py -3 tools\check_icon_assets.py || goto :failed
py -3 tools\gui_smoke_test.py || goto :failed

echo.
echo All quality checks passed.
pause
exit /b 0

:failed
echo.
echo Quality checks failed.
pause
exit /b 1
