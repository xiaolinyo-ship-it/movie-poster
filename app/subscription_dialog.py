"""Login-and-sync dialog for the user's dyjie subscription dashboard."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .subscriptions import parse_recent_updates


class SubscriptionSyncDialog(QDialog):
    """Use an app-owned web profile so credentials never enter MoviePoster config."""

    synced = Signal(object)

    def __init__(self, parent, url: str, data_dir: Path):
        super().__init__(parent)
        self.setWindowTitle("同步我的订阅")
        self.resize(1120, 760)
        self.setMinimumSize(900, 620)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)
        self.status = QLabel("请在页面中登录 dyjie.net，然后点击“读取最近更新”")
        self.status.setStyleSheet("color: #9aa4b2;")
        root.addWidget(self.status)

        self.view = QWebEngineView(self)
        profile = QWebEngineProfile("movie-poster-dyjie", self)
        profile.setPersistentStoragePath(str(Path(data_dir) / "dyjie-web"))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.view.setPage(QWebEnginePage(profile, self.view))
        self.view.loadFinished.connect(self._load_finished)
        root.addWidget(self.view, 1)

        actions = QHBoxLayout()
        reload_btn = QPushButton("重新加载")
        reload_btn.clicked.connect(self.view.reload)
        actions.addWidget(reload_btn)
        self.sync_btn = QPushButton("读取最近更新")
        self.sync_btn.setObjectName("primary")
        self.sync_btn.clicked.connect(self._sync)
        actions.addWidget(self.sync_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        actions.addWidget(close_btn)
        actions.addStretch(1)
        root.addLayout(actions)
        self.view.load(QUrl(url))

    def _load_finished(self, ok: bool) -> None:
        if not ok:
            self.status.setText("订阅页加载失败，请检查网络后重试")
        else:
            self.status.setText("页面已加载；登录后点击“读取最近更新”")

    def _sync(self) -> None:
        self.sync_btn.setEnabled(False)
        self.status.setText("正在读取订阅页…")
        self.view.page().toHtml(self._html_ready)

    def _html_ready(self, html: str) -> None:
        try:
            items = parse_recent_updates(html)
        except ValueError as exc:
            self.status.setText(str(exc))
            self.sync_btn.setEnabled(True)
            return
        self.synced.emit([item.to_dict() for item in items])
        self.accept()
