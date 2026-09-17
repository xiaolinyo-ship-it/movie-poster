"""Embedded authenticated subscription-page reader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from PySide6.QtWebEngineWidgets import QWebEngineView

from .subscriptions import (
    DEFAULT_SUBSCRIPTION_URL,
    SubscriptionLoginRequired,
    SubscriptionPageError,
    parse_recent_updates,
    parse_detail_poster,
    parse_detail_update_status,
)
from .credential_store import clear_credentials, load_credentials, save_credentials


_LOGIN_FORM_SCRIPT = "Boolean(document.querySelector(\"form[action*=\\\"/user/login\\\"]\"))"


def _login_script(email: str, password: str) -> str:
    """Fill the known dyjie login form and submit it without logging secrets."""
    email_literal = json.dumps(email, ensure_ascii=False)
    password_literal = json.dumps(password, ensure_ascii=False)
    return f"""
        (() => {{
            const form = document.querySelector('form[action*=\"/user/login\"]');
            const email = document.querySelector('#input_email');
            const password = document.querySelector('#input_password');
            if (!form || !email || !password) return false;
            email.value = {email_literal};
            password.value = {password_literal};
            for (const element of [email, password]) {{
                element.dispatchEvent(new Event('input', {{bubbles: true}}));
                element.dispatchEvent(new Event('change', {{bubbles: true}}));
            }}
            const submit = document.querySelector('#btn_submit') || form.querySelector('button[type=submit]');
            if (submit) submit.click();
            else form.submit();
            return true;
        }})()
    """


def _flush_persistent_session(profile: QWebEngineProfile) -> None:
    """Ask Chromium to persist cookies/storage without exposing credentials."""
    try:
        cookie_store = profile.cookieStore()
        flush = getattr(cookie_store, "flush", None)
        if callable(flush):
            flush()
    except Exception:
        # Session persistence is additive; a provider-specific flush failure
        # must not interrupt displaying already-read subscription data.
        pass


class SubscriptionSyncDialog(QDialog):
    """Let the user log in locally, then read only the recent update table."""

    synced = Signal(object)

    def __init__(
        self,
        parent,
        url: str = DEFAULT_SUBSCRIPTION_URL,
        data_dir: Path | None = None,
        profile: QWebEngineProfile | None = None,
        initial_url: str | None = None,
    ):
        super().__init__(parent)
        self.setWindowTitle("同步我的订阅")
        self.resize(1100, 760)
        self.url = url or DEFAULT_SUBSCRIPTION_URL
        self.initial_url = initial_url or self.url

        data_dir = Path(data_dir or Path.cwd() / "data")
        profile_dir = data_dir / "dyjie-web"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self.poster_dir = data_dir / "cache" / "subscriptions"
        self.poster_dir.mkdir(parents=True, exist_ok=True)
        self.profile = profile or QWebEngineProfile("movie-poster-dyjie", self)
        if profile is None:
            self.profile.setPersistentStoragePath(str(profile_dir))
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.page = QWebEnginePage(self.profile, self)
        self.detail_page = QWebEnginePage(self.profile, self)
        self.view = QWebEngineView(self)
        self.view.setPage(self.page)
        self.network = QNetworkAccessManager(self)
        self._items: list[dict[str, str]] = []
        self._poster_index = 0
        self._active_item: dict[str, str] | None = None
        self._active_poster_url = ""
        self.credentials_path = data_dir / "dyjie-credentials.bin"
        self._credentials = load_credentials(self.credentials_path)
        self._auto_login_attempted = False
        self._auto_login_in_flight = False
        self._read_after_auth = self.initial_url == self.url
        self._pending_read = False
        self._next_page_after_login = self.initial_url

        self.status = QLabel("请在下方页面登录 dyjie.net，然后点击“读取最近更新”")
        self.status.setWordWrap(True)
        credentials = QFormLayout()
        self.email_input = QLineEdit(self._credentials[0] if self._credentials else "")
        self.email_input.setPlaceholderText("dyjie.net 登录邮箱")
        self.password_input = QLineEdit(self._credentials[1] if self._credentials else "")
        self.password_input.setPlaceholderText("登录密码")
        self.password_input.setEchoMode(QLineEdit.Password)
        credentials.addRow("登录邮箱", self.email_input)
        credentials.addRow("登录密码", self.password_input)
        credentials_row = QHBoxLayout()
        self.login_btn = QPushButton("保存登录信息并登录")
        self.clear_login_btn = QPushButton("清除已保存账号")
        credentials_row.addWidget(self.login_btn)
        credentials_row.addWidget(self.clear_login_btn)
        credentials_row.addStretch(1)
        self.reload_btn = QPushButton("重新加载")
        self.sync_btn = QPushButton("读取最近更新")
        self.close_btn = QPushButton("关闭")
        buttons = QDialogButtonBox()
        buttons.addButton(self.reload_btn, QDialogButtonBox.ActionRole)
        buttons.addButton(self.sync_btn, QDialogButtonBox.AcceptRole)
        buttons.addButton(self.close_btn, QDialogButtonBox.RejectRole)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addLayout(credentials)
        layout.addLayout(credentials_row)
        layout.addWidget(self.view, 1)
        layout.addWidget(buttons)
        self.reload_btn.clicked.connect(lambda: self.view.load(QUrl(self.initial_url)))
        self.login_btn.clicked.connect(self._save_and_login)
        self.clear_login_btn.clicked.connect(self._clear_saved_login)
        self.sync_btn.clicked.connect(self._load_sync_page_and_read)
        self.close_btn.clicked.connect(self.reject)
        self.view.loadFinished.connect(self._load_finished)
        self.detail_page.loadFinished.connect(self._detail_loaded)
        self.view.load(QUrl(self.initial_url))

    def _load_finished(self, ok: bool) -> None:
        if not ok:
            self.status.setText("订阅页加载失败，请检查网络后重新加载")
            return
        QTimer.singleShot(250, self._inspect_loaded_page)

    def _inspect_loaded_page(self) -> None:
        self.page.runJavaScript(_LOGIN_FORM_SCRIPT, self._login_form_detected)

    def _login_form_detected(self, has_login_form: object) -> None:
        if bool(has_login_form):
            if self._auto_login_attempted:
                self._auto_login_in_flight = False
                self.status.setText("自动登录未成功，请检查登录邮箱和密码")
                return
            credentials = self._credentials or load_credentials(self.credentials_path)
            if not credentials:
                self.status.setText("请填写上方登录邮箱和密码，点击“保存登录信息并登录”")
                return
            self._credentials = credentials
            self._auto_login_attempted = True
            self._auto_login_in_flight = True
            self.status.setText("正在自动登录 dyjie.net…")
            self.page.runJavaScript(_login_script(*credentials), self._login_submitted)
            return

        if self._auto_login_in_flight:
            self._auto_login_in_flight = False
            _flush_persistent_session(self.profile)
            target = self._next_page_after_login
            QTimer.singleShot(800, lambda: self.view.load(QUrl(target)))
            return
        if self._pending_read:
            self._pending_read = False
            self._read_page()
        elif self._read_after_auth:
            self._read_after_auth = False
            self._read_page()

    def _login_submitted(self, submitted: object) -> None:
        if not bool(submitted):
            self._auto_login_in_flight = False
            self.status.setText("未找到 dyjie.net 登录表单，请检查页面")
        else:
            self.status.setText("已提交登录，正在打开订阅内容…")

    def _save_and_login(self) -> None:
        email = self.email_input.text().strip()
        password = self.password_input.text()
        if not email or not password:
            self.status.setText("请输入登录邮箱和密码")
            return
        try:
            save_credentials(self.credentials_path, email, password)
        except (OSError, RuntimeError, ValueError) as exc:
            self.status.setText(f"登录信息保存失败：{exc}")
            return
        self._credentials = (email, password)
        self._auto_login_attempted = False
        self._auto_login_in_flight = False
        self._next_page_after_login = self.initial_url
        self._read_after_auth = self.initial_url == self.url
        self.status.setText("登录信息已加密保存，正在登录…")
        self.view.load(QUrl(self.initial_url))

    def _clear_saved_login(self) -> None:
        clear_credentials(self.credentials_path)
        self._credentials = None
        self.email_input.clear()
        self.password_input.clear()
        self._auto_login_attempted = False
        self.status.setText("已清除保存的登录信息；当前网站会话仍可继续使用")

    def _load_sync_page_and_read(self) -> None:
        self._pending_read = True
        self._next_page_after_login = self.url
        self.sync_btn.setEnabled(False)
        self.status.setText("正在打开订阅更新列表…")
        if self.page.url().toString().rstrip("/") == self.url.rstrip("/"):
            self._inspect_loaded_page()
        else:
            self.view.load(QUrl(self.url))

    def _read_page(self) -> None:
        self.sync_btn.setEnabled(False)
        self.status.setText("正在读取订阅更新…")
        self.view.page().toHtml(self._on_html)

    def _on_html(self, html: str) -> None:
        try:
            items = parse_recent_updates(html)
        except SubscriptionLoginRequired as exc:
            self.status.setText(str(exc))
            self.sync_btn.setEnabled(True)
            return
        except SubscriptionPageError as exc:
            self.status.setText(f"读取失败：{exc}")
            self.sync_btn.setEnabled(True)
            return
        self._items = [item.to_dict() for item in items]
        self._poster_index = 0
        self._sync_next_poster()

    def _sync_next_poster(self) -> None:
        if self._poster_index >= len(self._items):
            poster_count = sum(bool(item.get("poster")) for item in self._items)
            self.status.setText(f"同步完成：{len(self._items)} 项，已同步海报 {poster_count} 张")
            _flush_persistent_session(self.profile)
            self.synced.emit(self._items)
            self.accept()
            return
        item = self._items[self._poster_index]
        self.status.setText(f"正在同步海报 {self._poster_index + 1}/{len(self._items)}：{item['title']}")
        self._active_item = item
        url = item.get("url", "")
        if not url:
            self._poster_index += 1
            self._sync_next_poster()
            return
        self.detail_page.load(QUrl(url))

    def _detail_loaded(self, ok: bool) -> None:
        if not self._active_item:
            return
        if not ok:
            self._poster_index += 1
            self._sync_next_poster()
            return
        self.detail_page.toHtml(self._detail_html_ready)

    def _detail_html_ready(self, html: str) -> None:
        if not self._active_item:
            return
        poster_url = parse_detail_poster(html, self._active_item.get("url", ""))
        self._active_item.update(parse_detail_update_status(html, self._active_item.get("title", "")))
        if not poster_url:
            self._poster_index += 1
            self._sync_next_poster()
            return
        self._active_poster_url = poster_url
        request = QNetworkRequest(QUrl(poster_url))
        request.setRawHeader(b"Referer", self._active_item.get("url", "").encode("utf-8"))
        request.setRawHeader(b"User-Agent", b"MoviePoster/1.0")
        reply = self.network.get(request)
        reply.finished.connect(lambda: self._poster_download_finished(reply))

    def _poster_download_finished(self, reply: QNetworkReply) -> None:
        if self._active_item and reply.error() == QNetworkReply.NoError:
            image = QImage()
            if image.loadFromData(reply.readAll()) and not image.isNull():
                filename = hashlib.sha1(self._active_poster_url.encode("utf-8")).hexdigest()[:20] + ".jpg"
                path = self.poster_dir / filename
                if image.save(str(path), "JPG", 95):
                    self._active_item["poster"] = str(path)
        reply.deleteLater()
        self._poster_index += 1
        self._sync_next_poster()


class SubscriptionAutoSync(QObject):
    """Read the authenticated update table without opening a dialog."""

    synced = Signal(object)
    status = Signal(str)

    def __init__(self, parent, url: str = DEFAULT_SUBSCRIPTION_URL, data_dir: Path | None = None):
        super().__init__(parent)
        self.url = url or DEFAULT_SUBSCRIPTION_URL
        data_dir = Path(data_dir or Path.cwd() / "data")
        profile_dir = data_dir / "dyjie-web"
        profile_dir.mkdir(parents=True, exist_ok=True)
        self.profile = QWebEngineProfile("movie-poster-dyjie", self)
        self.profile.setPersistentStoragePath(str(profile_dir))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)
        self.page = QWebEnginePage(self.profile, self)
        self.page.loadFinished.connect(self._loaded)
        self.detail_page = QWebEnginePage(self.profile, self)
        self.detail_page.loadFinished.connect(self._detail_loaded)
        self._running = False
        self._items: list[dict] = []
        self._detail_index = 0
        self._active_item: dict | None = None
        self.credentials_path = data_dir / "dyjie-credentials.bin"
        self._auto_login_attempted = False
        self._auto_login_in_flight = False

    def sync(self) -> None:
        if self._running:
            return
        self._running = True
        self._auto_login_attempted = False
        self._auto_login_in_flight = False
        self.status.emit("正在自动同步订阅…")
        self.page.load(QUrl(self.url))

    def stop(self) -> None:
        self._running = False
        for page in (self.page, self.detail_page):
            try:
                page.triggerAction(QWebEnginePage.WebAction.Stop)
            except Exception:
                pass
        _flush_persistent_session(self.profile)

    def _loaded(self, ok: bool) -> None:
        if not self._running:
            return
        if not ok:
            self._finish("自动同步失败：订阅页加载失败")
            return
        self.page.runJavaScript(_LOGIN_FORM_SCRIPT, self._login_form_detected)

    def _login_form_detected(self, has_login_form: object) -> None:
        if not self._running:
            return
        if bool(has_login_form):
            credentials = load_credentials(self.credentials_path)
            if not credentials:
                self._finish("自动同步跳过：请在 MoviePoster 内保存 dyjie.net 登录信息")
                return
            if self._auto_login_attempted:
                self._finish("自动同步失败：dyjie.net 自动登录未成功")
                return
            self._auto_login_attempted = True
            self._auto_login_in_flight = True
            self.status.emit("正在自动登录 dyjie.net…")
            self.page.runJavaScript(_login_script(*credentials), self._login_submitted)
            return
        if self._auto_login_in_flight:
            self._auto_login_in_flight = False
            _flush_persistent_session(self.profile)
            QTimer.singleShot(800, lambda: self.page.load(QUrl(self.url)))
            return
        self.page.toHtml(self._html_ready)

    def _login_submitted(self, submitted: object) -> None:
        if not self._running:
            return
        if not bool(submitted):
            self._finish("自动同步失败：未找到 dyjie.net 登录表单")
        else:
            self.status.emit("已提交登录，正在读取订阅更新…")

    def _html_ready(self, html: str) -> None:
        if not self._running:
            return
        try:
            items = parse_recent_updates(html)
        except SubscriptionLoginRequired:
            self._finish("自动同步跳过：请先在“同步我的订阅”窗口登录 dyjie.net")
            return
        except SubscriptionPageError as exc:
            self._finish(f"自动同步失败：{exc}")
            return
        self._items = [item.to_dict() for item in items]
        self._detail_index = 0
        self._load_next_detail()

    def _load_next_detail(self) -> None:
        if not self._running:
            return
        if self._detail_index >= len(self._items):
            _flush_persistent_session(self.profile)
            self.synced.emit(self._items)
            self._finish("自动同步完成")
            return
        self._active_item = self._items[self._detail_index]
        self._detail_index += 1
        url = str(self._active_item.get("url") or "").strip()
        if not url:
            self._load_next_detail()
            return
        self.detail_page.load(QUrl(url))

    def _detail_loaded(self, ok: bool) -> None:
        if not self._running:
            return
        if not ok or self._active_item is None:
            self._load_next_detail()
            return
        self.detail_page.toHtml(self._detail_html_ready)

    def _detail_html_ready(self, html: str) -> None:
        if not self._running:
            return
        if self._active_item is not None:
            self._active_item.update(
                parse_detail_update_status(html, str(self._active_item.get("title") or ""))
            )
        self._load_next_detail()

    def _finish(self, message: str) -> None:
        self._running = False
        self.status.emit(message)
