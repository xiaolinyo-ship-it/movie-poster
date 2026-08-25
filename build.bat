@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo Building MoviePoster...
python -m pip install --quiet -r requirements.txt
python -m pip install --quiet pyinstaller
python -m PyInstaller --noconfirm --clean MoviePoster.spec

if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

echo.
echo Build complete: dist\MoviePoster\MoviePoster.exe
echo NOTE: config.json, databases, caches and local media are intentionally NOT bundled.
endlocal
