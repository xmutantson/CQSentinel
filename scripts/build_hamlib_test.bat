@echo off
setlocal enabledelayedexpansion
REM Build standalone hamlib test executable for Windows
REM This creates a single .exe file that can be copied to another machine

echo ========================================
echo Building Hamlib RF Controls Test
echo ========================================
echo.

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    pip install pyinstaller
    if errorlevel 1 (
        echo ERROR: Failed to install PyInstaller
        pause
        exit /b 1
    )
)

REM Use bundled hamlib from external/hamlib
echo.
echo Locating bundled hamlib...
set RIGCTLD_DIR=external\hamlib\bin\
set RIGCTLD_PATH=%RIGCTLD_DIR%rigctld.exe

if not exist "%RIGCTLD_PATH%" (
    echo ERROR: Bundled hamlib not found at: %RIGCTLD_PATH%
    echo.
    echo The external/hamlib/bin/ directory should contain hamlib binaries.
    echo Please ensure hamlib is installed in external/hamlib/
    pause
    exit /b 1
)

echo Found bundled rigctld: %RIGCTLD_PATH%

echo.
echo Building standalone executable...
echo   Including rigctld from: %RIGCTLD_DIR%
echo.

REM Build with PyInstaller, bundling rigctld.exe and DLLs
pyinstaller --onefile --console ^
    --name "HamlibRFTest" ^
    --add-binary "%RIGCTLD_PATH%;." ^
    --add-binary "%RIGCTLD_DIR%libgcc_s_sjlj-1.dll;." ^
    --add-binary "%RIGCTLD_DIR%libhamlib-4.dll;." ^
    --add-binary "%RIGCTLD_DIR%libusb-1.0.dll;." ^
    --add-binary "%RIGCTLD_DIR%libwinpthread-1.dll;." ^
    test_hamlib_levels_standalone.py

if errorlevel 1 (
    echo.
    echo ERROR: Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build complete!
echo ========================================
echo.
echo Executable location:
echo   dist\HamlibRFTest.exe
echo.
echo This is a SINGLE FILE that includes:
echo   - Python runtime
echo   - Test script
echo   - rigctld.exe
echo   - All hamlib DLLs
echo.
echo Copy this file to your IC-705 machine and run it.
echo It will start rigctld automatically!
echo.
pause
