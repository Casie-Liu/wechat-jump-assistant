@echo off
setlocal
cd /d "%~dp0"
if not exist "PreciseInput.exe" (
    call "%~dp0build.cmd"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" jump_assistant.pyw
) else (
    python jump_assistant.pyw
)
if errorlevel 1 pause
