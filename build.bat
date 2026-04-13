@echo off
REM ============================================================
REM  Ren'Py Translator Pro — One-Click Build Script (Windows)
REM ============================================================

echo.
echo  ====================================
echo   Ren'Py Translator Pro Build Script
echo  ====================================
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH. Install Python 3.10+ first.
    pause
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] pip install failed.
    pause
    exit /b 1
)

echo [2/4] Installing PyInstaller...
pip install pyinstaller --quiet

echo [3/4] Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist  rmdir /s /q dist

echo [4/4] Building executable...
pyinstaller RenPyTranslator.spec --noconfirm

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed. Check output above.
    pause
    exit /b 1
)

echo.
echo  ====================================
echo   BUILD SUCCESSFUL!
echo   Location: dist\RenPyTranslator.exe
echo  ====================================
echo.
pause
