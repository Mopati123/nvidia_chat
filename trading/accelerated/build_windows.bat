@echo off
REM Windows Cython Build Helper
REM This script sets up the Visual Studio environment and builds Cython extensions

echo ==========================================
echo ApexQuantumICT Cython Build for Windows
echo ==========================================

REM Check for Visual Studio paths in priority order
REM Priority: v18 (internal version with compiler) > 2022 x64 > 2022 x86

set "VS2022_V18=C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools"
set "VS2022_PATH=C:\Program Files\Microsoft Visual Studio\2022\BuildTools"
set "VS2022_PATH_X86=C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools"

REM Check for VS 2022 with internal version number FIRST (has compiler)
if exist "%VS2022_V18%" (
    echo Found VS 2022 BuildTools v18 - has compiler
    set "VS_PATH=%VS2022_V18%"
    goto :found_vs
)

if exist "%VS2022_PATH%" (
    echo Found VS 2022 BuildTools (x64)
    set "VS_PATH=%VS2022_PATH%"
    goto :found_vs
)

if exist "%VS2022_PATH_X86%" (
    echo Found VS 2022 BuildTools (x86)
    set "VS_PATH=%VS2022_PATH_X86%"
    goto :found_vs
)

REM Check for Visual Studio 2019
set "VS2019_PATH=C:\Program Files\Microsoft Visual Studio\2019\BuildTools"
set "VS2019_PATH_X86=C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools"

if exist "%VS2019_PATH%" (
    echo Found VS 2019 BuildTools (x64)
    set "VS_PATH=%VS2019_PATH%"
    goto :found_vs
)

if exist "%VS2019_PATH_X86%" (
    echo Found VS 2019 BuildTools (x86)
    set "VS_PATH=%VS2019_PATH_X86%"
    goto :found_vs
)

echo ERROR: Visual Studio Build Tools not found!
echo Please install from: https://visualstudio.microsoft.com/visual-cpp-build-tools/
echo Make sure to install "Desktop development with C++" workload
echo.
echo Alternatively, the system works fine with NumPy fallback (just slower)
exit /b 1

:found_vs
echo VS Path: %VS_PATH%

REM Set up VC environment - check multiple locations
set "VCVARS_PATH=%VS_PATH%\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VCVARS_PATH%" (
    set "VCVARS_PATH=%VS_PATH%\VC\Auxiliary\Build\vcvars32.bat"
)
if not exist "%VCVARS_PATH%" (
    set "VCVARS_PATH=%VS_PATH%\VC\Auxiliary\Build\vcvarsall.bat"
)
if not exist "%VCVARS_PATH%" (
    set "VCVARS_PATH=%VS_PATH%\Common7\Tools\VsDevCmd.bat"
)

if not exist "%VCVARS_PATH%" (
    echo ERROR: Could not find vcvars script at:
    echo   %VS_PATH%\VC\Auxiliary\Build\vcvars64.bat
    echo   %VS_PATH%\VC\Auxiliary\Build\vcvars32.bat
    echo   %VS_PATH%\Common7\Tools\VsDevCmd.bat
    echo.
    echo Please verify Visual Studio C++ build tools are installed.
    exit /b 1
)

echo Setting up compiler environment...
call "%VCVARS_PATH%"

REM Verify cl.exe is now available
where cl.exe >nul 2>&1
if errorlevel 1 (
    echo ERROR: cl.exe still not available after setup
    exit /b 1
)

echo.
echo Compiler found: 
where cl.exe
echo.

REM Build the extensions
echo Building Cython extensions...
python setup.py build_ext --inplace

if errorlevel 1 (
    echo.
    echo ERROR: Build failed
    exit /b 1
)

echo.
echo ==========================================
echo Build Complete!
echo ==========================================
echo.
echo Verify with: python -c "from trading.accelerated import CYTHON_AVAILABLE; print(CYTHON_AVAILABLE)"
echo.
pause
