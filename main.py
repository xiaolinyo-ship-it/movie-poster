"""MoviePoster 入口。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app.config import Config
from app.store import Store
from app.ui import MainWindow


def main() -> int:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path(__file__).resolve().parent
    config = Config(base)
    store = Store(str(config.db_path))
    app = QApplication(sys.argv)
    app.setApplicationName("小林影视")
    win = MainWindow(config, store)
    win.show()
    code = app.exec()
    store.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
