@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在打包为 exe ...
python -m pip install --quiet pyinstaller -i https://pypi.tuna.tsinghua.edu.cn/simple
python -m PyInstaller --noconfirm --clean --noconsole --name MoviePoster --icon assets\MoviePoster.ico --add-data "config.json;." main.py
echo.
echo 打包完成：dist\MoviePoster\MoviePoster.exe
pause
