@echo off
setlocal
cd /d "%~dp0"
set "JUMP_CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%JUMP_CSC%" (
    echo C# compiler not found: %JUMP_CSC%
    echo Install the .NET Framework build tools or compile PreciseInput.cs with a compatible x64 C# compiler.
    exit /b 1
)
"%JUMP_CSC%" /nologo /optimize+ /platform:x64 /target:exe /out:"%~dp0PreciseInput.exe" "%~dp0PreciseInput.cs"
if errorlevel 1 exit /b 1
echo Built PreciseInput.exe
