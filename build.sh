#!/bin/bash
# ============================================================
#  Ren'Py Translator Pro — Build Script (Linux/macOS)
# ============================================================

set -e

echo ""
echo " ===================================="
echo "  Ren'Py Translator Pro Build Script"
echo " ===================================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found."
    exit 1
fi

echo "[1/4] Installing dependencies..."
pip3 install -r requirements.txt -q

echo "[2/4] Installing PyInstaller..."
pip3 install pyinstaller -q

echo "[3/4] Cleaning previous builds..."
rm -rf build dist

echo "[4/4] Building executable..."
python3 -m PyInstaller RenPyTranslator.spec --noconfirm

echo ""
echo " ===================================="
echo "  BUILD SUCCESSFUL!"
echo "  Location: dist/RenPyTranslator"
echo " ===================================="
echo ""
