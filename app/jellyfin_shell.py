"""Jellyfin 原生前端壳。

MoviePoster 复用本机 Jellyfin Web 前端，避免重新仿制媒体中心 UI。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow


class JellyfinShell(QMainWindow):
    def __init__(self, base_dir: Path):
        super().__init__()
        self.setWindowTitle("小林影业")
        self.resize(1360, 860)
        self.setMinimumSize(1024, 640)

        self.view = QWebEngineView(self)
        profile = QWebEngineProfile("xiaolin-media", self)
        profile.setPersistentStoragePath(str(Path(base_dir) / "data" / "jellyfin-web"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        # 使用持久化 Profile 保存 Jellyfin 登录状态，但不读取或导出浏览器凭据。
        from PySide6.QtWebEngineCore import QWebEnginePage
        self.view.setPage(QWebEnginePage(profile, self.view))
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.FullScreenSupportEnabled, True)
        settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)
        self.setCentralWidget(self.view)
        self.view.load(QUrl("http://127.0.0.1:8096"))
