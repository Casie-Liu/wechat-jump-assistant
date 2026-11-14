@echo off
setlocal
cd /d "%~dp0"
if defined JUMP_BUILD_PYTHON (
    set "JUMP_RELEASE_PYTHON=%JUMP_BUILD_PYTHON%"
) else if exist ".venv\Scripts\python.exe" (
    set "JUMP_RELEASE_PYTHON=%~dp0.venv\Scripts\python.exe"
) else (
    set "JUMP_RELEASE_PYTHON=python"
)
set "PYINSTALLER_CONFIG_DIR=%~dp0build\pyinstaller-cache"
call "%~dp0build.cmd"
if errorlevel 1 exit /b 1
"%JUMP_RELEASE_PYTHON%" tools\collect_licenses.py
if errorlevel 1 exit /b 1
"%JUMP_RELEASE_PYTHON%" -m PyInstaller --noconfirm WeChatJumpAssistant.spec
if errorlevel 1 exit /b 1
echo Built dist\WeChatJumpAssistant-Windows-x64.exe
