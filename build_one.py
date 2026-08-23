"""后台打包脚本。"""

import sys

sys.argv = [
    "pyinstaller",
    "--noconfirm",
    "--clean",
    "--noconsole",
    "--name",
    "MoviePoster",
    "--hidden-import",
    "PySide6.QtSvg",
    "main.py",
]
from PyInstaller.__main__ import run  # noqa: E402

run()
