@echo off
REM Build CQSentinel for Windows
REM Simple batch script wrapper for Python build script

echo ============================================================
echo CQSentinel Windows Build
echo ============================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in PATH
    echo Please install Python 3.10+ from python.org
    pause
    exit /b 1
)

REM Check if in virtual environment (optional but recommended)
if not defined VIRTUAL_ENV (
    echo WARNING: Not in a virtual environment
    echo Consider running: python -m venv venv
    echo                   venv\Scripts\activate
    echo.
)

REM Check if PyInstaller is installed
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
)

REM Run the build script
python scripts\build_windows.py --clean --zip

if errorlevel 1 (
    echo.
    echo ============================================================
    echo Build FAILED
    echo ============================================================
    pause
    exit /b 1
)

echo.
echo ============================================================
echo Build SUCCESSFUL
echo ============================================================
echo.
echo Output: dist\CQSentinel\CQSentinel.exe
echo ZIP:    CQSentinel-windows-portable.zip
echo.
pause
