@echo off
rem QuickNotes launcher
rem Prefer the packaged exe (release\ or dist\), fall back to source run.
rem NOTE: keep this file ASCII-only. cmd.exe reads .bat using the system codepage,
rem so any Chinese character inside will corrupt command parsing.
cd /d "%~dp0"

if exist "release\QuickNotes.exe" (
    start "" "release\QuickNotes.exe"
    exit /b 0
)

if exist "dist\QuickNotes.exe" (
    start "" "dist\QuickNotes.exe"
    exit /b 0
)

rem Source mode: dev venv lives outside the project folder
set "VENV=%~dp0..\_dev_env\qn-venv\Scripts\pythonw.exe"
if exist "%VENV%" (
    start "" "%VENV%" main.py
    exit /b 0
)

rem Last resort: system pythonw (requires PyQt6 installed)
where pythonw >nul 2>&1
if %errorlevel%==0 (
    start "" pythonw main.py
) else (
    echo No runnable environment found.
    echo Please run release\QuickNotes.exe directly, or install Python + PyQt6.
    pause
)
