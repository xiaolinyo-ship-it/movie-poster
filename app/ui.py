"""PySide6 界面。"""

from __future__ import annotations

import os
import re
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QRect,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QFontDatabase,
    QIcon,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCompleter,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QStyledItemDelegate,
    QStyle,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel

from .config import Config
from .douban import DoubanClient
from .store import Store
from .image_provider import ImageProviderManager
from .workers import (
    ApplySubjectWorker,
    DoubanTask,
    DoubanSignals,
    ManualSearchWorker,
    OrganizeApplyWorker,
    OrganizePlanWorker,
    ScanWorker,
    TmdbTask,
    TmdbSignals,
    TmdbLinkTask,
    TmdbLinkSignals,
    TmdbEpisodeTask,
    TmdbEpisodeSignals,
    TmdbRelationTask,
    TmdbRelationSignals,
    UndoWorker,
)


FONT_SYSTEM = {
    # Jellyfin 首页频道标题使用中等字号与字重，避免管理后台式的大黑体。
    "title": (24, QFont.DemiBold),
    "navigation": (14, QFont.Normal),
    "card": (14, QFont.Normal),
    "meta": (12, QFont.Normal),
}
_FONT_CONFIGURED = False


def configure_application_font(app: QApplication | None = None) -> str:
    """Register a guaranteed Windows CJK font and make it QApplication-wide."""
    global _FONT_CONFIGURED
    app = app or QApplication.instance()
    if app is None:
        return ""
    if _FONT_CONFIGURED:
        return app.font().family()

    # Register the files explicitly so Qt does not depend on the process
    # environment's fontconfig database (important for packaged/offscreen runs).
    font_files = (
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\Noto Sans SC (TrueType).otf",
        r"C:\Windows\Fonts\simsun.ttc",
    )
    for path in font_files:
        if os.path.exists(path):
            QFontDatabase.addApplicationFont(path)

    available = set(QFontDatabase.families())
    candidates = (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "Noto Sans SC",
        "SimSun",
        "NSimSun",
    )
    family = next((name for name in candidates if name in available), "Sans Serif")
    font = QFont(family)
    font.setStyleHint(QFont.SansSerif)
    font.setPixelSize(14)
    app.setFont(font)
    _FONT_CONFIGURED = True
    return family


def role_font(role: str) -> QFont:
    size, weight = FONT_SYSTEM.get(role, FONT_SYSTEM["meta"])
    font = QFont()
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


DARK_QSS = """
QMainWindow, QWidget { background: #101010; color: #e8eaed; }
QWidget { font-size: 13px; }
QLabel { background: transparent; }
QListWidget#nav { background: #111419; border: none; border-right: 1px solid #262b33; padding-top: 14px; }
QListWidget#nav::item { height: 44px; padding-left: 16px; border: none; border-radius: 6px; margin: 2px 6px; }
QListWidget#nav::item:selected { background: #243b5a; color: #ffffff; border-left: 3px solid #5ea1ff; }
QListWidget#nav::item:hover { background: #232933; }
QLineEdit, QSpinBox, QComboBox { background: #1f242c; border: 1px solid #2d3340; border-radius: 6px; padding: 6px 10px; color: #e8eaed; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #4c8bf5; }
QPushButton { background: #2a3240; border: 1px solid #38414f; border-radius: 6px; padding: 7px 14px; color: #e8eaed; }
QPushButton:hover { background: #35404f; }
QPushButton:disabled { color: #6b7280; background: #232830; }
QPushButton#primary { background: #3b82f6; border: none; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #4c8bf5; }
QPushButton#danger { background: #7f1d1d; border: none; color: #fecaca; }
QTableView, QTreeWidget, QTableWidget { background: #1b1f26; border: 1px solid #262b33; border-radius: 8px; gridline-color: #262b33; }
QHeaderView::section { background: #20242c; border: none; border-bottom: 1px solid #2d3340; padding: 8px; color: #9aa4b2; font-weight: 600; }
QTableView::item, QTreeWidget::item, QTableWidget::item { padding: 6px; }
QTableView::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected { background: #2b3a55; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: #38414f; border-radius: 5px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QProgressBar { background: #1f242c; border: none; border-radius: 4px; text-align: center; height: 12px; }
QProgressBar::chunk { background: #3b82f6; border-radius: 4px; }
QTextBrowser { background: #1b1f26; border: 1px solid #262b33; border-radius: 8px; padding: 8px; }
QTabWidget::pane { border: 1px solid #262b33; }
QToolTip { background: #262b33; color: #e8eaed; border: 1px solid #38414f; }
QFrame#hero { background: #1b2533; border: 1px solid #2b405e; border-radius: 10px; }
QLabel#heroKicker { color: #8fb8ec; font-size: 11px; font-weight: 700; }
QLabel#heroTitle { color: #f6f8fb; font-size: 21px; font-weight: 700; }
QLabel#heroMeta { color: #aebbd0; font-size: 13px; }
QLabel#sectionTitle { color: #f2f4f7; font-size: 24px; font-weight: 600; }
QLabel#sectionSubtitle { color: #8e99a8; font-size: 12px; }
QLabel#stat { color: #8e99a8; font-size: 12px; }
QLabel#statValue { color: #f2f4f7; font-size: 15px; font-weight: 700; }
"""


def fmt_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def rating_color(rating: float | None) -> QColor:
    if rating is None:
        return QColor("#5b6472")
    if rating >= 9.0:
        return QColor("#f5c518")
    if rating >= 8.0:
        return QColor("#3eb489")
    if rating >= 7.0:
        return QColor("#58a6ff")
    return QColor("#8b95a5")


class PosterDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._pix_cache: dict[str, QPixmap] = {}

    def sizeHint(self, option, index):
        return QSize(168, 252)

    def _pix(self, path: str) -> QPixmap | None:
        if not path or not os.path.exists(path):
            return None
        if path not in self._pix_cache:
            pm = QPixmap(path)
            if not pm.isNull():
                self._pix_cache[path] = pm.scaled(
                    156, 216, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
        return self._pix_cache.get(path)

    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect
        title = index.data(Qt.DisplayRole) or ""
        rating = index.data(Qt.UserRole + 1)
        progress = index.data(Qt.UserRole + 2) or 0.0
        poster_path = index.data(Qt.UserRole + 3) or ""
        watched = index.data(Qt.UserRole + 4)
        has_progress = index.data(Qt.UserRole + 5)

        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)

        card = QRectF(rect.x() + 6, rect.y() + 6, 156, 240)
        path = QPainterPath()
        path.addRoundedRect(card, 8, 8)

        if hover:
            painter.setPen(QPen(QColor("#4c8bf5"), 2))
        elif selected:
            painter.setPen(QPen(QColor("#7aa7f8"), 2))
        else:
            painter.setPen(QPen(QColor("#2b313b"), 1))

        pix = self._pix(poster_path)
        if pix:
            painter.setClipPath(path)
            painter.drawPixmap(card.toRect(), pix)
            painter.setClipping(False)
        else:
            painter.fillPath(path, QColor("#232933"))
            painter.setPen(QColor("#4a5568"))
            f = QFont()
            f.setPointSize(30)
            painter.setFont(f)
            first = title[0] if title else "?"
            painter.drawText(card.adjusted(0, 50, 0, -50), Qt.AlignCenter, first)
            painter.setPen(QColor("#6b7280"))
            f2 = QFont()
            f2.setPointSize(8)
            painter.setFont(f2)
            painter.drawText(card.adjusted(0, 110, 0, -40), Qt.AlignCenter, "暂无海报")
        painter.setPen(QPen(QColor("#2b313b"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

        # 底部标题渐变
        title_bar = QRectF(card.left(), card.bottom() - 52, card.width(), 52)
        grad_path = QPainterPath()
        grad_path.addRoundedRect(title_bar, 8, 8)
        painter.setClipPath(grad_path)
        painter.fillRect(title_bar, QColor(10, 12, 16, 210))
        painter.setClipping(False)

        # 评分徽章
        if rating is not None:
            badge = QRectF(card.right() - 46, card.top() + 8, 40, 22)
            bp = QPainterPath()
            bp.addRoundedRect(badge, 6, 6)
            painter.fillPath(bp, QColor(20, 22, 28, 200))
            painter.setPen(rating_color(rating))
            f3 = QFont()
            f3.setPointSize(10)
            f3.setBold(True)
            painter.setFont(f3)
            painter.drawText(badge, Qt.AlignCenter, f"{rating:.1f}")

        # 进度角标
        if has_progress:
            tag = QRectF(card.right() - 70, card.top() + 34, 64, 18)
            tp = QPainterPath()
            tp.addRoundedRect(tag, 5, 5)
            painter.fillPath(tp, QColor(232, 82, 68, 230))
            f4 = QFont()
            f4.setPointSize(8)
            f4.setBold(True)
            painter.setFont(f4)
            painter.setPen(QColor("white"))
            painter.drawText(tag, Qt.AlignCenter, "续播")

        if watched:
            tag = QRectF(card.left() + 8, card.top() + 8, 58, 20)
            tp = QPainterPath()
            tp.addRoundedRect(tag, 5, 5)
            painter.fillPath(tp, QColor(34, 128, 90, 235))
            painter.setFont(f4)
            painter.setPen(QColor("white"))
            painter.drawText(tag, Qt.AlignCenter, "已看完")

        # 标题 + 进度条
        f5 = QFont()
        f5.setPointSize(10)
        f5.setBold(True)
        painter.setFont(f5)
        painter.setPen(QColor("#f2f4f7"))
        elided = painter.fontMetrics().elidedText(title, Qt.ElideRight, int(card.width()) - 12)
        painter.drawText(QRectF(card.left() + 6, card.bottom() - 48, card.width() - 12, 20), Qt.AlignLeft | Qt.AlignVCenter, elided)

        if progress > 0:
            bar_y = int(card.bottom()) - 8
            painter.fillRect(int(card.left()) + 6, bar_y, int(card.width()) - 12, 4, QColor("#2d3540"))
            painter.fillRect(int(card.left()) + 6, bar_y, max(2, int((card.width() - 12) * min(progress, 1.0))), 4, QColor("#f59e0b"))

        painter.restore()


class PosterGrid(QListView):
    """海报网格视图。"""

    activated_item = Signal(int)  # item_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(8)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setItemDelegate(PosterDelegate(self))
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._source = QStandardItemModel(self)
        self.model = QSortFilterProxyModel(self)
        self.model.setSourceModel(self._source)
        self.setModel(self.model)
        self.doubleClicked.connect(self._on_double)

    def _on_double(self, index: QModelIndex):
        item = self._source.itemFromIndex(self.model.mapToSource(index))
        if item:
            self.activated_item.emit(int(item.data(Qt.UserRole)))

    def clear(self):
        self._source.clear()
        self.model.setFilterFixedString("")

    def add_item(self, item_id: int, title: str, rating, progress: float,
                 poster_path: str, watched: bool, has_progress: bool):
        it = QStandardItem(title)
        it.setData(item_id, Qt.UserRole)
        it.setData(rating, Qt.UserRole + 1)
        it.setData(progress, Qt.UserRole + 2)
        it.setData(poster_path, Qt.UserRole + 3)
        it.setData(watched, Qt.UserRole + 4)
        it.setData(has_progress, Qt.UserRole + 5)
        it.setToolTip(title)
        self._source.appendRow(it)

    def update_item(self, item_id: int, rating, poster_path: str):
        for r in range(self._source.rowCount()):
            item = self._source.item(r)
            if item and int(item.data(Qt.UserRole)) == item_id:
                item.setData(rating, Qt.UserRole + 1)
                item.setData(poster_path, Qt.UserRole + 3)
                self.viewport().update()
                return

    def filter_text(self, text: str):
        self.model.setFilterFixedString(text)


class MediaLibraryCard(QFrame):
    """Jellyfin-style library entry: art fills the card, title overlays the bottom."""

    clicked = Signal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self._pixmap = QPixmap()
        self.setFixedSize(420, 236)
        self.setCursor(Qt.PointingHandCursor)

    def set_art(self, path: str):
        self._pixmap = QPixmap(path) if path and os.path.exists(path) else QPixmap()
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(path)
        painter.fillRect(self.rect(), QColor("#26313d"))
        if not self._pixmap.isNull():
            scaled = self._pixmap.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            left = max(0, (scaled.width() - self.width()) // 2)
            top = max(0, (scaled.height() - self.height()) // 2)
            painter.drawPixmap(0, 0, scaled, left, top, self.width(), self.height())
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.35, QColor(10, 12, 16, 0))
        gradient.setColorAt(1.0, QColor(10, 12, 16, 235))
        painter.fillRect(self.rect(), gradient)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(role_font("card"))
        painter.drawText(QRectF(16, self.height() - 48, self.width() - 32, 34), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#3a424d"), 1))
        painter.drawPath(path)
        painter.end()


class ContinueWatchingCard(QWidget):
    """16:9 resume card with title, subtitle and a visible progress bar."""

    def __init__(self, win: "MainWindow", item_id: int, title: str, poster: str, subtitle: str, progress: float, play_path: str = ""):
        super().__init__()
        self.setFixedSize(350, 280)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        button = QPushButton()
        button.setFixedSize(350, 196)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet("QPushButton { border: 1px solid #2b3038; border-radius: 7px; background: #20252c; } QPushButton:hover { border: 2px solid #d7dde7; }")
        if poster and os.path.exists(poster):
            pix = win._cover_pixmap(poster, 350, 196)
            button.setIcon(QIcon(pix))
            button.setIconSize(QSize(350, 196))
        else:
            button.setText(title[:16])
        if play_path:
            button.clicked.connect(lambda: win.play(play_path, resume=False))
        else:
            button.clicked.connect(lambda: win._open_detail(item_id))
        layout.addWidget(button)
        name = QLabel(title)
        name.setFont(role_font("card"))
        name.setStyleSheet("color: #e3e3e3;")
        layout.addWidget(name)
        meta = QLabel(subtitle)
        meta.setFont(role_font("meta"))
        meta.setStyleSheet("color: #9d9d9d;")
        layout.addWidget(meta)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(max(0, min(100, int(progress * 100))))
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setStyleSheet("QProgressBar { background: #30343b; border: none; } QProgressBar::chunk { background: #8ab4f8; }")
        layout.addWidget(bar)


class PosterCard(QWidget):
    """Standard 2:3 poster card used by ordinary media channels."""

    def __init__(self, win: "MainWindow", item_id: int, title: str, poster: str, subtitle: str = ""):
        super().__init__()
        # Jellyfin 首页的竖版海报更克制，保持 2:3 比例并减少首屏拥挤。
        self.setFixedWidth(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        button = QPushButton()
        button.setFixedSize(160, 240)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet("QPushButton { border: 1px solid #2b3038; border-radius: 7px; background: #20252c; } QPushButton:hover { border: 2px solid #d7dde7; }")
        if poster and os.path.exists(poster):
            pix = win._cover_pixmap(poster, 160, 240)
            button.setIcon(QIcon(pix))
            button.setIconSize(QSize(160, 240))
        else:
            button.setText("暂无海报")
        button.clicked.connect(lambda: win._open_detail(item_id))
        layout.addWidget(button)
        name = QLabel(title)
        name.setFont(role_font("card"))
        name.setMaximumWidth(160)
        name.setWordWrap(False)
        name.setStyleSheet("color: #e3e3e3;")
        layout.addWidget(name)
        if subtitle:
            meta = QLabel(subtitle)
            meta.setFont(role_font("meta"))
            meta.setStyleSheet("color: #9d9d9d;")
            layout.addWidget(meta)


class MainWindow(QMainWindow):
    def __init__(self, config: Config, store: Store):
        super().__init__()
        self.font_family = configure_application_font(QApplication.instance())
        self.config = config
        self.store = store
        self.images = ImageProviderManager(store, config.cache_dir)
        self.client = DoubanClient(config.cache_dir, delay=float(config.get("request_delay", 0.4)))
        from .tmdb import TmdbClient
        self.tmdb_client = TmdbClient(config.cache_dir, str(config.get("tmdb_api_key", "")))
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(1)
        # PotPlayer is an external process, so keep a lightweight local session
        # tracker and periodically persist an approximate position.  This is
        # what makes Next Up usable without embedding or replacing PotPlayer.
        self._play_sessions: list[dict] = []
        self._play_timer = QTimer(self)
        self._play_timer.setInterval(5000)
        self._play_timer.timeout.connect(self._poll_play_sessions)
        self._play_timer.start()
        # 启动即从数据库加载已有条目，后台扫描完成后刷新
        self.items = {
            "tv": [r["id"] for r in store.list_items("tv")],
            "movie": [r["id"] for r in store.list_items("movie")],
        }
        self.current_kind = "tv"
        self.poster_paths: dict[int, str] = {}
        self._home_media_cache = None
        self._poster_pixmap_cache: dict[tuple, QPixmap] = {}

        self.setWindowTitle("小林影业 · NAS")
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(DARK_QSS)
        self._build_ui()
        self._connect()
        self._show_continue()
        self.scan()

    # ---------- UI ----------
    def _build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 顶栏：影院入口优先；扫描、整理、设置等后台能力收进菜单
        top = QWidget()
        top.setStyleSheet("background: #202020; border-bottom: 1px solid #2b2b2b;")
        tl = QGridLayout(top)
        tl.setContentsMargins(16, 10, 16, 10)
        tl.setHorizontalSpacing(12)
        tl.setColumnStretch(0, 1)
        tl.setColumnStretch(1, 1)
        tl.setColumnStretch(2, 1)
        # Use a broadly supported symbol instead of an icon-font glyph that can
        # render as a tofu square in packaged Qt environments.
        menu = QPushButton("≡")
        menu.setFixedSize(38, 38)
        menu.setStyleSheet("font-size: 22px; border: none; background: transparent; color: #d7d7d7;")
        left_bar = QWidget()
        left_layout = QHBoxLayout(left_bar)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(4)
        left_layout.addWidget(menu)
        title = QLabel("小林影业")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #f2f4f7;")
        left_layout.addWidget(title)
        brand = QLabel("NAS")
        brand.setStyleSheet("font-size: 10px; color: #6f7f94; letter-spacing: 1px;")
        left_layout.addWidget(brand)
        left_layout.addStretch(1)
        tl.addWidget(left_bar, 0, 0, Qt.AlignVCenter | Qt.AlignLeft)
        self.home_btn = QPushButton("首页")
        self.favorite_btn = QPushButton("★ 我的最爱")
        self.detail_back_btn = QPushButton("返回")
        self.detail_back_btn.setObjectName("topNav")
        self.detail_back_btn.setCheckable(False)
        self.detail_back_btn.setVisible(False)
        for nav_btn in (self.home_btn, self.favorite_btn):
            nav_btn.setObjectName("topNav")
            nav_btn.setCheckable(True)
            nav_btn.setFont(role_font("navigation"))
            nav_btn.setStyleSheet(
                "QPushButton#topNav { border: 1px solid transparent; border-radius: 8px; "
                "padding: 8px 16px; color: #aeb4bb; background: transparent; } "
                "QPushButton#topNav:hover { color: #ffffff; background: #2a3039; } "
                "QPushButton#topNav:checked { color: #ffffff; background: #394b63; border-color: #536b88; }"
            )
        nav_bar = QWidget()
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(8)
        for nav_btn in (self.home_btn, self.favorite_btn):
            nav_layout.addWidget(nav_btn)
        self.detail_back_btn.setStyleSheet(
            "QPushButton#topNav { border: 1px solid #394351; border-radius: 8px; "
            "padding: 8px 16px; color: #d8dee8; background: #252b34; } "
            "QPushButton#topNav:hover { color: #ffffff; background: #354153; }"
        )
        nav_layout.addWidget(self.detail_back_btn)
        nav_layout.addStretch(1)
        tl.addWidget(nav_bar, 0, 1, Qt.AlignCenter)
        right_bar = QWidget()
        right_layout = QHBoxLayout(right_bar)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索片名…")
        self.search.setFixedWidth(220)
        self.search_completer = QCompleter(self)
        self.search_completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.search_completer.setFilterMode(Qt.MatchContains)
        self.search.setCompleter(self.search_completer)
        right_layout.addWidget(self.search)
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #9aa4b2;")
        self.status_label.setFont(role_font("meta"))
        self.status_label.setMaximumWidth(320)
        self.status_label.setToolTip("当前媒体库统计；扫描和元数据任务仍在后台运行")
        right_layout.addWidget(self.status_label)
        self.refresh_btn = QPushButton("重新扫描")
        self.radarr_btn = QPushButton("Radarr")
        self.radarr_btn.setToolTip("打开电影搜片与下载管理")
        self.settings_btn = QPushButton("设置")
        management = QMenu(self)
        management.addAction("重新扫描", self.scan)
        management.addAction("整理模式", lambda: self._nav_changed(3))
        management.addAction("Radarr", lambda: QDesktopServices.openUrl(QUrl("http://127.0.0.1:7878")))
        management.addAction("设置", lambda: self.stack.setCurrentIndex(3))
        menu.clicked.connect(lambda: management.popup(menu.mapToGlobal(menu.rect().bottomLeft())))
        tl.addWidget(right_bar, 0, 2, Qt.AlignVCenter | Qt.AlignRight)
        root.addWidget(top)

        # 隐藏的导航模型保留原有业务逻辑，视觉上由顶部导航驱动
        self.nav = QListWidget()
        self.nav.setObjectName("nav")
        self.nav.setVisible(False)
        for name in ["继续观看", "电视剧", "电影", "整理模式"]:
            QListWidgetItem(name, self.nav)
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Jellyfin 风格的媒体库工作区：页面头部 + 统计横幅 + 海报网格
        self.library_page = QWidget()
        self.library_page.setStyleSheet("background-color: #101010;")
        library_layout = QVBoxLayout(self.library_page)
        library_layout.setContentsMargins(32, 20, 32, 30)
        library_layout.setSpacing(18)

        self.section_title = QLabel("继续观看")
        self.section_title.setObjectName("sectionTitle")
        self.section_title.setFont(role_font("title"))
        library_layout.addWidget(self.section_title)
        self.section_subtitle = QLabel("从上次停下的地方继续播放")
        self.section_subtitle.setObjectName("sectionSubtitle")
        library_layout.addWidget(self.section_subtitle)

        self.tv_library_btn = MediaLibraryCard("电视剧")
        self.movie_library_btn = MediaLibraryCard("电影")

        self.home_panel = QWidget()
        self.home_layout = QVBoxLayout(self.home_panel)
        self.home_layout.setContentsMargins(0, 4, 0, 0)
        # V13：媒体库入口紧跟“我的媒体”标题，避免首屏出现大块空白。
        self.home_layout.setSpacing(0)
        self.home_layout.addLayout(self._home_library_row())
        self.home_rows_widget = QWidget()
        self.home_rows = QVBoxLayout(self.home_rows_widget)
        self.home_rows.setContentsMargins(0, 0, 0, 0)
        self.home_rows.setSpacing(20)
        self.home_rows_scroll = QScrollArea()
        self.home_rows_scroll.setWidgetResizable(True)
        self.home_rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.home_rows_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._install_cinema_scrollbar(self.home_rows_scroll)
        self.home_rows_scroll.setWidget(self.home_rows_widget)
        self.home_layout.addWidget(self.home_rows_scroll)
        library_layout.addWidget(self.home_panel, 1)

        self.continue_heading = QLabel("接下来")
        self.continue_heading.setObjectName("sectionTitle")
        self.continue_heading.setVisible(False)
        library_layout.addWidget(self.continue_heading)

        self.hero = QFrame()
        self.hero.setObjectName("hero")
        self.hero.setFixedHeight(112)
        self.hero.setVisible(False)
        hero_layout = QHBoxLayout(self.hero)
        hero_layout.setContentsMargins(20, 16, 20, 16)
        hero_layout.setSpacing(28)
        hero_copy = QVBoxLayout()
        kicker = QLabel("YOUR LIBRARY")
        kicker.setObjectName("heroKicker")
        hero_copy.addWidget(kicker)
        self.hero_title = QLabel("电影与电视剧，集中在一个地方")
        self.hero_title.setObjectName("heroTitle")
        hero_copy.addWidget(self.hero_title)
        self.hero_meta = QLabel("正在读取 NAS 媒体库…")
        self.hero_meta.setObjectName("heroMeta")
        hero_copy.addWidget(self.hero_meta)
        hero_copy.addStretch(1)
        hero_layout.addLayout(hero_copy, 1)
        stats = QHBoxLayout()
        self.movie_stat = self._stat_block("电影", "0")
        self.tv_stat = self._stat_block("电视剧", "0")
        stats.addWidget(self.movie_stat)
        stats.addWidget(self.tv_stat)
        hero_layout.addLayout(stats)
        library_layout.addWidget(self.hero)

        # 视图
        self.grid = PosterGrid()
        library_layout.addWidget(self.grid, 1)
        self.grid.setVisible(False)
        self.stack.addWidget(self.library_page)  # 0 首页 + 电影/电视剧共用
        self.detail = DetailPage(self)
        self.stack.addWidget(self.detail)        # 1
        self.organize = OrganizePage(self)
        self.stack.addWidget(self.organize)      # 2
        self.settings = SettingsPage(self)
        self.stack.addWidget(self.settings)      # 3

        self.setCentralWidget(central)

        self.home_btn.clicked.connect(self._show_continue)
        self.favorite_btn.clicked.connect(lambda: self.nav.setCurrentRow(0))
        self.detail_back_btn.clicked.connect(self._back_to_grid)
        self.tv_library_btn.clicked.connect(lambda: self.nav.setCurrentRow(1))
        self.movie_library_btn.clicked.connect(lambda: self.nav.setCurrentRow(2))
        # 菜单按钮现在只打开后台入口菜单，影院导航始终保持简洁。

    def _stat_block(self, label: str, value: str) -> QWidget:
        block = QWidget()
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        value_label = QLabel(value)
        value_label.setObjectName("statValue")
        caption = QLabel(label)
        caption.setObjectName("stat")
        layout.addWidget(value_label)
        layout.addWidget(caption)
        block.value_label = value_label
        return block

    def _home_library_row(self) -> QVBoxLayout:
        row = QVBoxLayout()
        row.setSpacing(8)
        cards = QHBoxLayout()
        cards.setSpacing(28)
        for button in (self.tv_library_btn, self.movie_library_btn):
            cards.addWidget(button)
        cards.setAlignment(Qt.AlignLeft)
        row.addLayout(cards)
        return row

    @staticmethod
    def _install_cinema_scrollbar(scroll: QScrollArea) -> None:
        """Use a hidden-by-default 4px scrollbar that fades after inactivity."""
        hidden_style = (
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 0px; background: transparent; margin: 0; }"
            "QScrollBar::handle:vertical { background: transparent; min-height: 24px; border-radius: 2px; }"
        )
        visible_style = (
            "QScrollArea { border: none; background: transparent; }"
            "QScrollBar:vertical { width: 4px; background: transparent; margin: 0; }"
            "QScrollBar::handle:vertical { background: rgba(220,230,245,150); min-height: 24px; border-radius: 2px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(255,255,255,210); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )
        scroll.setStyleSheet(hidden_style)
        timer = QTimer(scroll)
        timer.setSingleShot(True)
        timer.setInterval(2000)
        timer.timeout.connect(lambda: scroll.setStyleSheet(hidden_style))
        scroll._cinema_scroll_timer = timer

        def reveal(_value=0):
            scroll.setStyleSheet(visible_style)
            timer.start()

        scroll.verticalScrollBar().valueChanged.connect(reveal)

    def _cover_pixmap(self, path: str, width: int, height: int) -> QPixmap:
        """Crop cached art to the exact card box, matching cinema backdrop cards."""
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            stamp = 0
        key = (path, width, height, stamp)
        cached = self._poster_pixmap_cache.get(key)
        if cached is not None:
            return cached
        source = QPixmap(path)
        scaled = source.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        left = max(0, (scaled.width() - width) // 2)
        top = max(0, (scaled.height() - height) // 2)
        result = scaled.copy(left, top, width, height)
        self._poster_pixmap_cache[key] = result
        return result

    def _make_media_row(self, title: str, entries: list[tuple], card_type: str = "poster") -> QWidget:
        section = QWidget()
        outer = QVBoxLayout(section)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        heading = QLabel(title + "  ›")
        heading.setObjectName("sectionTitle")
        heading.setFont(role_font("title"))
        outer.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        is_continue = card_type == "continue"
        row_height = 280 if is_continue else 320
        scroll.setFixedHeight(row_height)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        content = QWidget()
        line = QHBoxLayout(content)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(18)
        for entry in entries:
            item_id, name, poster, subtitle = entry[:4]
            if is_continue:
                ratio = float(entry[4]) if len(entry) > 4 else 0.0
                play_path = str(entry[5]) if len(entry) > 5 else ""
                line.addWidget(ContinueWatchingCard(self, item_id, name, poster, subtitle, ratio, play_path))
            else:
                line.addWidget(PosterCard(self, item_id, name, poster, subtitle))
        line.addStretch(1)
        card_width = 368 if is_continue else 178
        content.setFixedWidth(max(card_width, len(entries) * card_width + 20))
        content.setFixedHeight(280 if is_continue else 274)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        # Keep the section from being compressed by the parent home layout.  In
        # particular, ContinueWatchingCard contains title/subtitle/progress
        # below its 16:9 artwork and must retain the full row height.
        section.setMinimumHeight(row_height + 38)
        return section

    def _invalidate_home_cache(self):
        self._home_media_cache = None

    def _populate_home(self):
        while self.home_rows.count():
            item = self.home_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._home_media_cache is None:
            # 首次进入才读取数据库、解析文件时间和刷新库入口图片。
            self._refresh_library_art()
            next_entries = self._next_up_entries()

            def rows_for(kind: str):
                rows = [self.store.get_item(i) for i in self.items.get(kind, [])]
                rows = [r for r in rows if r]

                def recent_key(row):
                    file_times = []
                    try:
                        files = self.store.list_files(row["id"])
                    except Exception:
                        files = []
                    for file_row in files:
                        path = str(file_row["path"] or "")
                        try:
                            file_times.append(os.path.getmtime(path))
                        except (OSError, ValueError):
                            try:
                                file_times.append(os.path.getctime(path))
                            except (OSError, ValueError):
                                continue
                    if file_times:
                        return (1, max(file_times), "")
                    return (0, 0.0, row["updated_at"] or "")

                rows.sort(key=recent_key, reverse=True)
                return rows

            def entries(rows, subtitle):
                return [(r["id"], r["title"], r["poster"] or "", subtitle) for r in rows[:18]]

            tv_rows = rows_for("tv")
            movie_rows = rows_for("movie")
            rated = sorted(
                [r for r in tv_rows + movie_rows if r["rating"] is not None],
                key=lambda r: (float(r["rating"] or 0), r["updated_at"] or ""),
                reverse=True,
            )
            self._home_media_cache = {
                "next": next_entries,
                "tv": entries(tv_rows, "电视剧"),
                "movie": entries(movie_rows, "电影"),
                "rated": [
                    (r["id"], r["title"], r["poster"] or "", f"豆瓣 {float(r['rating']):.1f}")
                    for r in rated[:18]
                ],
            }

        data = self._home_media_cache
        if data["next"]:
            self.home_rows.addWidget(self._make_media_row("接下来", data["next"], card_type="continue"))
        self.home_rows.addWidget(self._make_media_row("最近添加的电视剧", data["tv"]))
        self.home_rows.addWidget(self._make_media_row("最近添加的电影", data["movie"]))
        self.home_rows.addWidget(self._make_media_row("高评分", data["rated"]))

    @staticmethod
    def _episode_name(filename: str) -> str:
        stem = Path(filename or "").stem
        match = re.search(r"(?i)s\d{1,2}e\d{1,3}", stem)
        label = stem[match.end():] if match else stem
        label = re.split(r"(?i)\b(?:2160p|1080p|720p|WEB[- .]?DL|BluRay|x264|x265)\b", label)[0]
        label = re.sub(r"[._]+", " ", label).strip(" -_[]()")
        # Episode subtitles are not release metadata; never expose a year here.
        label = re.sub(r"\b(?:19|20)\d{2}\b", "", label)
        label = re.sub(r"\s{2,}", " ", label).strip(" -_[]()")
        return label or "本集"

    @classmethod
    def _episode_title(cls, file_row) -> str:
        """Read an episode title when a metadata-rich row provides one.

        Older SQLite rows only contain ``filename``; the fallback keeps those
        installations compatible while ensuring the UI never shows a year as
        the episode subtitle.
        """
        keys = set(file_row.keys()) if hasattr(file_row, "keys") else set()
        for key in ("episode_title", "episode_name", "title"):
            if key in keys and file_row[key]:
                value = re.sub(r"\b(?:19|20)\d{2}\b", "", str(file_row[key]))
                value = re.sub(r"\s{2,}", " ", value).strip(" -_[]()")
                if value:
                    return value
        return cls._episode_name(file_row["filename"] if "filename" in keys else "")

    def _next_up_entries(self) -> list[tuple]:
        """Build Jellyfin-style Next Up rows from existing file progress data."""
        result = []
        seen = set()
        for row, _series_ratio in self.store.continuing_items():
            files = self.store.list_files(row["id"])
            episodes = [f for f in files if f["episode"] is not None]
            episodes.sort(key=lambda f: (int(f["season"] or 1), int(f["episode"] or 0)))
            for current in episodes:
                position = float(current["progress"] or 0)
                duration = float(current["duration"] or 0)
                if position <= 0 or duration <= 0 or position >= duration:
                    continue
                current_key = (int(current["season"] or 1), int(current["episode"] or 0))
                next_file = next((f for f in episodes if (int(f["season"] or 1), int(f["episode"] or 0)) > current_key), None)
                if next_file is None or next_file["path"] in seen:
                    continue
                seen.add(next_file["path"])
                season = int(next_file["season"] or 1)
                number = int(next_file["episode"] or 0)
                episode_row = self.store.get_episode_for_file(row["id"], season, number)
                subtitle_title = (
                    episode_row["episode_title"]
                    if episode_row and episode_row["episode_title"]
                    else self._episode_title(next_file)
                )
                subtitle = f"S{season:02d}E{number:02d} - {subtitle_title}"
                ratio = min(1.0, max(0.0, position / duration))
                result.append((row["id"], row["title"], row["poster"] or "", subtitle, ratio, next_file["path"]))
                break
        return result

    def _refresh_library_art(self):
        """Jellyfin-style library tile art: prefer backdrop/fanart over poster."""
        for kind, button in (("tv", self.tv_library_btn), ("movie", self.movie_library_btn)):
            candidates = []
            for item_id in self.items.get(kind, []):
                row = self.store.get_item(item_id)
                if not row:
                    continue
                for key in ("backdrop", "fanart", "poster"):
                    try:
                        value = row[key]
                    except Exception:
                        value = None
                    if value and os.path.exists(value):
                        candidates.append(value)
                        break
            button.set_art(candidates[0] if candidates else "")

    def _connect(self):
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.search.textChanged.connect(self._update_search_suggestions)
        self.search.textChanged.connect(self._search_all)
        self.refresh_btn.clicked.connect(self.scan)
        self.radarr_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("http://127.0.0.1:7878")))
        self.settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.grid.activated_item.connect(self._open_detail)
        # DetailPage no longer owns a separate back button; navigation is kept
        # in the shared top bar so every page has the same interaction model.

    # ---------- 扫描 ----------
    def scan(self):
        tv_root = self.config.get("tv_root")
        movie_root = self.config.get("movie_root")
        if not tv_root or not os.path.isdir(tv_root) or not os.path.isdir(movie_root):
            self.status_label.setText("NAS 路径不可访问，请在设置中检查")
            QMessageBox.warning(self, "路径错误", "NAS 目录不可访问，请到设置里确认路径。")
            return
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("正在扫描 NAS 媒体库（首次约 40 秒），完成后自动刷新…")
        self.worker = ScanWorker(tv_root, movie_root)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.finished_scan.connect(self._scan_done)
        self.worker.error.connect(lambda e: self._scan_error(e))
        self.worker.start()

    def _scan_error(self, msg: str):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(f"扫描失败：{msg}")

    def _scan_done(self, tv, movies):
        self.refresh_btn.setEnabled(True)
        self._invalidate_home_cache()
        self.tv_items = tv
        self.movie_items = movies
        was_detail = self.stack.currentIndex() == 1
        # 入库
        for kind, items in (("tv", tv), ("movie", movies)):
            self.items[kind] = []
            for it in items:
                item_id = self.store.upsert_item(kind, it.title, it.path)
                self.store.replace_files(
                    item_id,
                    [f.path for f in it.files],
                    [f.name for f in it.files],
                    [f.season for f in it.files],
                    [f.episode for f in it.files],
                )
                self.items[kind].append(item_id)
        self.status_label.setText(f"扫描完成：电视剧 {len(tv)} 部，电影 {len(movies)} 部，正在抓取豆瓣信息…")
        self._update_library_stats()
        self._start_douban()
        self._start_tmdb()
        self._back_to_grid()
        if was_detail and self.detail.item_id:
            self.detail.load(self.detail.item_id)
            self.stack.setCurrentIndex(1)

    def _start_douban(self):
        self._douban_total = 0
        self._douban_done = 0
        self._douban_failed = 0
        self._douban_handles: list = []
        todo = []
        for kind in ("tv", "movie"):
            for item_id in self.items[kind]:
                row = self.store.get_item(item_id)
                if row and not row["rating"] and self.config.get("douban_enabled", True):
                    todo.append((item_id, row["title"], kind, row["douban_id"] or None))
                elif row:
                    self.poster_paths[item_id] = row["poster"] or ""
        self._douban_total = len(todo)
        if not todo:
            self._update_library_stats()
            return
        for item_id, title, kind, sid in todo:
            sig = DoubanSignals()
            sig.done.connect(self._douban_done_cb)
            sig.failed.connect(self._douban_failed_cb)
            self._douban_handles.append(sig)
            task = DoubanTask(self.client, item_id, title, kind, sid, sig)
            task.setAutoDelete(False)
            self._douban_tasks = getattr(self, "_douban_tasks", [])
            self._douban_tasks.append(task)
            self.pool.start(task)

    def _start_tmdb(self):
        """Bind TV IDs, then synchronize episodes; never overwrite Douban fields."""
        if not self.tmdb_client.enabled:
            return
        self._tmdb_link_tasks = []
        self._tmdb_link_handles = []
        self._episode_tasks = []
        self._episode_handles = []
        self._relation_tasks = []
        self._relation_handles = []
        for kind in ("tv", "movie"):
            for item_id in self.items.get(kind, []):
                row = self.store.get_item(item_id)
                if not row:
                    continue
                if row["tmdb_id"]:
                    if kind == "tv":
                        self._start_episode_sync(item_id, str(row["tmdb_id"]))
                    self._start_relation_sync(item_id, str(row["tmdb_id"]), kind)
                else:
                    self._queue_tmdb_link(row)

    def _queue_tmdb_link(self, row):
        if not self.tmdb_client.enabled or row["tmdb_id"]:
            return
        self._tmdb_link_tasks = getattr(self, "_tmdb_link_tasks", [])
        self._tmdb_link_handles = getattr(self, "_tmdb_link_handles", [])
        if any(getattr(task, "item_id", None) == row["id"] for task in self._tmdb_link_tasks):
            return
        queries = [x for x in (row["douban_title"], row["title"]) if x]
        if not queries:
            return
        sig = TmdbLinkSignals()
        sig.done.connect(self._tmdb_link_done_cb)
        sig.failed.connect(lambda _item_id: None)
        self._tmdb_link_handles.append(sig)
        task = TmdbLinkTask(self.tmdb_client, row["id"], row["kind"], queries, row["year"], sig)
        task.setAutoDelete(False)
        self._tmdb_link_tasks.append(task)
        self.pool.start(task)

    def _tmdb_link_done_cb(self, item_id: int, tmdb_id: str):
        """Write only items.tmdb_id, then open the episode sync path."""
        self.store.update_meta(item_id, tmdb_id=str(tmdb_id))
        row = self.store.get_item(item_id)
        if row and row["kind"] == "tv":
            self._start_episode_sync(item_id, str(tmdb_id))
        if row:
            self._start_relation_sync(item_id, str(tmdb_id), row["kind"])

    def _start_relation_sync(self, item_id: int, tmdb_id: str, kind: str):
        if not self.tmdb_client.enabled or not tmdb_id:
            return
        sig = TmdbRelationSignals()
        sig.done.connect(self._tmdb_relation_done_cb)
        sig.failed.connect(lambda _item_id: None)
        task = TmdbRelationTask(self.tmdb_client, item_id, tmdb_id, kind, sig)
        task.setAutoDelete(False)
        self._relation_handles.append(sig)
        self._relation_tasks.append(task)
        self.pool.start(task)

    def _tmdb_relation_done_cb(self, item_id: int, data: dict):
        self.store.replace_item_relations(
            item_id,
            genres=data.get("genres", []),
            directors=data.get("directors", []),
            actors=data.get("actors", []),
        )

    def _tmdb_done_cb(self, item_id: int, meta: dict, backdrop_path: str):
        fields = {
            "tmdb_id": meta.get("tmdb_id"),
            "original_title": meta.get("original_title") or None,
            "runtime_minutes": meta.get("runtime_minutes"),
            "metadata_status": "ready",
        }
        if backdrop_path:
            fields["backdrop"] = backdrop_path
        # Never write TMDB title, score or summary over the existing Douban values.
        self.store.update_meta(item_id, **fields)
        self.store.replace_item_metadata(
            item_id,
            genres=meta.get("genres", []),
            countries=meta.get("countries", []),
            directors=meta.get("directors", []),
            actors=meta.get("actors", []),
        )
        if self.store.get_item(item_id)["kind"] == "tv" and meta.get("tmdb_id"):
            self._start_episode_sync(item_id, str(meta["tmdb_id"]))
        if self.detail.item_id == item_id:
            self.detail.load(item_id)

    def _start_episode_sync(self, item_id: int, tmdb_id: str):
        """Fetch episode names for an already identified TV series."""
        for file_row in self.store.list_files(item_id):
            if file_row["episode"] is None:
                continue
            season = int(file_row["season"] or 1)
            episode = int(file_row["episode"])
            sig = TmdbEpisodeSignals()
            sig.done.connect(self._tmdb_episode_done_cb)
            sig.failed.connect(lambda *_args: None)
            task = TmdbEpisodeTask(self.tmdb_client, item_id, tmdb_id, season, episode, sig)
            task.setAutoDelete(False)
            self._episode_handles.append(sig)
            self._episode_tasks.append(task)
            self.pool.start(task)

    def _tmdb_episode_done_cb(self, item_id: int, season: int, episode: int, data: dict):
        self._invalidate_home_cache()
        self.store.upsert_episode(
            item_id, season, episode,
            episode_title=data.get("episode_title", ""),
            overview=data.get("overview", ""),
            air_date=data.get("air_date", ""),
            tmdb_episode_id=data.get("tmdb_episode_id", ""),
        )
        if self.stack.currentIndex() == 0:
            self._show_continue()

    def _douban_done_cb(self, item_id: int, meta: dict, poster_path: str | None):
        self._invalidate_home_cache()
        self._douban_done += 1
        fields = {
            "douban_id": meta.get("douban_id"),
            "douban_title": meta.get("douban_title"),
            "rating": meta.get("rating"),
            "votes": meta.get("votes"),
            "year": meta.get("year"),
            "summary": meta.get("summary"),
            "poster": poster_path or "",
        }
        self.store.update_meta(item_id, **fields)
        # A freshly completed Douban match may not have existed when the TMDB
        # pass started. Queue its ID binding now, without changing Douban data.
        if self.tmdb_client.enabled:
            row = self.store.get_item(item_id)
            if row and not row["tmdb_id"]:
                self._queue_tmdb_link(row)
        self.poster_paths[item_id] = poster_path or ""
        self._update_library_stats()
        self.grid.update_item(item_id, fields["rating"], poster_path or "")
        self._release_douban_handle()

    def _douban_failed_cb(self, item_id: int):
        self._douban_failed += 1
        self._update_library_stats()
        self._release_douban_handle()

    def _release_douban_handle(self):
        if self._douban_handles:
            self._douban_handles.pop(0)
        if getattr(self, "_douban_tasks", None):
            self._douban_tasks.pop(0)

    def _back_to_grid(self):
        if self.current_kind == "continue":
            self._show_continue()
        elif self.current_kind == "search":
            self._search_all(self.search.text())
        else:
            self._show_kind(self.current_kind)

    def _search_all(self, text: str):
        """Render full-library search results instead of filtering a hidden grid."""
        keyword = (text or "").strip()
        if not keyword:
            self._show_continue()
            return
        self.current_kind = "search"
        self._set_detail_navigation(False)
        self.stack.setCurrentIndex(0)
        self.home_panel.setVisible(False)
        self.grid.setVisible(True)
        self.tv_library_btn.setVisible(False)
        self.movie_library_btn.setVisible(False)
        self.continue_heading.setVisible(False)
        self.section_title.setText(f"搜索结果：{keyword}")
        self.section_subtitle.setText("电影和电视剧")
        self.grid.clear()
        for row in self.store.search_all(keyword):
            label = row["title"]
            if row["kind"] == "tv":
                label = f"{label} · {int(row['episode_count'] or 0)}集"
            if row["matched_by"]:
                label = f"{label} · 匹配：{row['matched_by']}"
            self.grid.add_item(
                row["id"], label, row["rating"], 0.0,
                row["poster"] or "", False, False,
            )

    def _update_search_suggestions(self, text: str):
        suggestions = self.store.search_suggestions(text)
        model = QStandardItemModel(self.search_completer)
        for value in suggestions:
            model.appendRow(QStandardItem(value))
        self.search_completer.setModel(model)

    # ---------- 导航 ----------
    def _set_detail_navigation(self, active: bool):
        """Keep the shared top bar consistent across library and detail views."""
        self.detail_back_btn.setVisible(active)
        self.home_btn.setChecked(not active and self.current_kind == "continue")
        self.favorite_btn.setChecked(False)

    def _nav_changed(self, row: int):
        if self.stack.currentIndex() == 1:
            self._set_detail_navigation(False)
        if row == 0:
            self._show_continue()
        elif row == 1:
            self._show_kind("tv")
        elif row == 2:
            self._show_kind("movie")
        elif row == 3:
            self.organize.refresh()
            self.stack.setCurrentIndex(2)

    def _show_continue(self):
        self.current_kind = "continue"
        self._set_detail_navigation(False)
        self.stack.setCurrentIndex(0)
        self.home_panel.setVisible(True)
        self.grid.setVisible(False)
        self.tv_library_btn.setVisible(True)
        self.movie_library_btn.setVisible(True)
        # “接下来” is rendered as a home channel inside home_rows; keep the
        # legacy grid heading hidden so it cannot duplicate the channel title.
        self.continue_heading.setVisible(False)
        self.section_title.setText("我的媒体")
        self.section_subtitle.setText("")
        self.section_subtitle.hide()
        self._update_library_stats()
        self._populate_home()
        self.grid.clear()
        self.search.clear()

    def _show_kind(self, kind: str):
        self.current_kind = kind
        self._set_detail_navigation(False)
        self.stack.setCurrentIndex(0)
        self.home_panel.setVisible(False)
        self.grid.setVisible(True)
        self.tv_library_btn.setVisible(False)
        self.movie_library_btn.setVisible(False)
        self.continue_heading.setVisible(False)
        label = "电视剧" if kind == "tv" else "电影"
        self.section_title.setText(label)
        self.section_subtitle.setText("按海报浏览，双击进入详情")
        self.section_subtitle.show()
        self.hero_title.setText(f"{label}库")
        self.hero_meta.setText("NAS 媒体库已连接，元数据会在后台持续补全")
        self.grid.clear()
        for item_id in self.items.get(kind, []):
            row = self.store.get_item(item_id)
            if not row:
                continue
            files = self.store.list_files(item_id)
            done, total = self.store.item_progress(item_id)
            progress = done / total if total else 0.0
            has_progress = any(f["progress"] > 0 for f in files)
            watched = done >= total and total > 0
            self.grid.add_item(
                item_id, row["title"], row["rating"], progress,
                row["poster"] or "", watched, has_progress,
            )

        self._update_library_stats()

    def _update_library_stats(self):
        movie_count = len(self.items.get("movie", []))
        tv_count = len(self.items.get("tv", []))
        self.movie_stat.value_label.setText(str(movie_count))
        self.tv_stat.value_label.setText(str(tv_count))
        self.status_label.setText(f"电影 {movie_count} 部 · 电视剧 {tv_count} 部")

    # ---------- 详情 ----------
    def _open_detail(self, item_id: int):
        self._previous_stack_index = self.stack.currentIndex()
        self._previous_kind = self.current_kind
        self.detail.load(item_id)
        self._set_detail_navigation(True)
        self.stack.setCurrentIndex(1)

    def play(self, path: str, resume: bool = False):
        pot = self.config.get("potplayer")
        if not pot or not os.path.exists(pot):
            QMessageBox.warning(self, "播放器缺失", "找不到 PotPlayer，请在设置里指定播放器路径。")
            return
        cmd = [pot]
        if resume:
            f = self.store.get_file(path)
            if f and f["progress"] > 0:
                cmd.append(f"/seek={int(f['progress'])}")
        cmd.append(path)
        try:
            process = subprocess.Popen(cmd)
            file_row = self.store.get_file(path)
            previous = float(file_row["progress"] or 0) if file_row else 0.0
            duration = float(file_row["duration"] or 0) if file_row else 0.0
            if duration <= 0:
                duration = self._probe_duration(path)
            # A launch is a real viewing interaction. Persist a small positive
            # position immediately, then refine it while PotPlayer is running.
            # This also works when PotPlayer is closed before its first poll.
            start_position = previous if previous > 0 else 1.0
            if duration > 0 and start_position >= duration:
                start_position = max(0.5, duration * 0.01)
            self.store.update_play_state(path, "in_progress", start_position, duration or None)
            self.store.update_last_played(path)
            self._play_sessions.append({
                "process": process,
                "path": path,
                "started": time.monotonic(),
                "base": start_position,
                "duration": duration,
            })
        except Exception as e:
            QMessageBox.warning(self, "播放失败", str(e))

    @staticmethod
    def _probe_duration(path: str) -> float:
        """Read media duration when available; failure is non-fatal."""
        try:
            result = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, timeout=8,
            )
            return max(0.0, float((result.stdout or "").strip()))
        except Exception:
            return 0.0

    def _poll_play_sessions(self):
        remaining = []
        home_changed = False
        for session in self._play_sessions:
            process = session["process"]
            elapsed = max(0.0, time.monotonic() - session["started"])
            duration = float(session.get("duration") or 0)
            position = session["base"] + elapsed
            if duration > 0:
                position = min(position, duration)
            finished = duration > 0 and position >= duration * 0.95
            try:
                process_done = process.poll() is not None
            except Exception:
                process_done = False
            if finished:
                self.store.update_play_state(session["path"], "finished", position, duration or None)
                self.store.set_watched(session["path"], True)
                home_changed = True
            else:
                self.store.update_play_state(session["path"], "in_progress", position, duration or None)
                if not process_done:
                    remaining.append(session)
                else:
                    home_changed = True
        self._play_sessions = remaining
        if home_changed and self.stack.currentIndex() == 0:
            self._invalidate_home_cache()
            self._show_continue()

    def closeEvent(self, event):
        # 优雅停止后台豆瓣任务，避免退出时线程报错
        self.pool.clear()
        self.pool.waitForDone(3000)
        if self._play_timer.isActive():
            self._play_timer.stop()
        super().closeEvent(event)


class BackdropBanner(QFrame):
    """A lightweight cinema backdrop with a readability gradient."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap = QPixmap()
        self.setMinimumHeight(230)
        blur = QGraphicsBlurEffect(self)
        blur.setBlurRadius(10)
        self.setGraphicsEffect(blur)

    def set_path(self, path: str, fallback: str = ""):
        chosen = path if path and os.path.exists(path) else fallback
        self._pixmap = QPixmap(chosen) if chosen and os.path.exists(chosen) else QPixmap()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#1b2028"))
        if not self._pixmap.isNull():
            enlarged = QSize(int(self.width() * 1.08), int(self.height() * 1.08))
            scaled = self._pixmap.scaled(enlarged, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            painter.drawPixmap(-x, -y, scaled)
        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, QColor(0, 0, 0, 180))
        gradient.setColorAt(0.45, QColor(0, 0, 0, 115))
        gradient.setColorAt(1.0, QColor(0, 0, 0, 50))
        painter.fillRect(self.rect(), gradient)
        bottom_gradient = QLinearGradient(0, 0, 0, self.height())
        bottom_gradient.setColorAt(0.35, QColor(0, 0, 0, 0))
        bottom_gradient.setColorAt(1.0, QColor(0, 0, 0, 185))
        painter.fillRect(self.rect(), bottom_gradient)
        painter.end()


class ManualMetadataDialog(QDialog):
    """详情页手动豆瓣资料修正；预览后才写入当前条目。"""

    def __init__(self, page: "DetailPage", row):
        super().__init__(page)
        self.page = page
        self.row = row
        self._meta = None
        self._poster_path = ""
        self.setWindowTitle("手动更新影片资料")
        self.setMinimumSize(620, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        root.addWidget(QLabel("豆瓣影片 URL"))
        url_row = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://movie.douban.com/subject/xxxxx/")
        self.fetch_btn = QPushButton("获取资料")
        self.fetch_btn.clicked.connect(self._fetch)
        url_row.addWidget(self.url_input, 1)
        url_row.addWidget(self.fetch_btn)
        root.addLayout(url_row)

        self.status = QLabel("输入豆瓣 subject 链接后获取预览")
        self.status.setStyleSheet("color: #9aa4b2;")
        root.addWidget(self.status)
        preview = QHBoxLayout()
        self.preview_poster = QLabel("暂无海报")
        self.preview_poster.setFixedSize(120, 170)
        self.preview_poster.setAlignment(Qt.AlignCenter)
        self.preview_poster.setStyleSheet("background: #232933; border-radius: 6px; color: #9aa4b2;")
        preview.addWidget(self.preview_poster, 0, Qt.AlignTop)
        details = QVBoxLayout()
        self.preview_title = QLabel("标题：")
        self.preview_year = QLabel("年份：")
        self.preview_directors = QLabel("导演：")
        self.preview_actors = QLabel("演员：")
        self.preview_summary = QTextBrowser()
        self.preview_summary.setReadOnly(True)
        self.preview_summary.setMaximumHeight(150)
        self.preview_summary.setStyleSheet("QTextBrowser { border: none; background: transparent; color: #d8dde5; }")
        for label in (self.preview_title, self.preview_year, self.preview_directors, self.preview_actors):
            label.setWordWrap(True)
            details.addWidget(label)
        details.addWidget(self.preview_summary, 1)
        preview.addLayout(details, 1)
        root.addLayout(preview, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.confirm_btn = buttons.addButton("确认更新", QDialogButtonBox.AcceptRole)
        self.confirm_btn.setEnabled(False)
        buttons.rejected.connect(self.reject)
        self.confirm_btn.clicked.connect(self._confirm)
        root.addWidget(buttons)

    def _fetch(self):
        match = re.search(r"/subject/(\d+)", self.url_input.text().strip())
        if not match:
            match = re.search(r"\b(\d{4,})\b", self.url_input.text().strip())
        if not match:
            self.status.setText("请输入有效的豆瓣 subject URL")
            return
        self.fetch_btn.setEnabled(False)
        self.confirm_btn.setEnabled(False)
        self.status.setText("正在获取资料…")
        worker = ApplySubjectWorker(
            self.page.win.client,
            int(self.page.item_id),
            self.row["title"],
            self.row["kind"],
            match.group(1),
        )
        worker.done.connect(self._show_preview)
        worker.failed.connect(lambda _item_id: self._fetch_failed())
        worker.finished.connect(lambda: self.fetch_btn.setEnabled(True))
        self._worker = worker
        worker.start()

    def _fetch_failed(self):
        self.status.setText("获取失败，请检查链接或稍后重试")

    def _show_preview(self, _item_id: int, meta: dict, poster_path: str):
        self._meta = meta
        self._poster_path = poster_path or ""
        # fetch_item_meta 已把详情写入豆瓣缓存；从同一详情对象读取人物，
        # 这样预览和确认更新都能复用现有关系数据格式。
        detail = self.page.win.client.detail(str(meta.get("douban_id") or "")) if meta.get("douban_id") else None
        if detail:
            meta["directors"] = detail.get("directors") or []
            meta["actors"] = detail.get("actors") or []
        self.status.setText("资料预览已加载，确认后才会写入")
        self.preview_title.setText(f"标题：{meta.get('douban_title') or self.row['title']}")
        self.preview_year.setText(f"年份：{meta.get('year') or '暂无'}")
        directors = "、".join(a.get("name", "") for a in meta.get("directors", [])) or "暂无"
        actors = "、".join(a.get("name", "") for a in meta.get("actors", [])[:12]) or "暂无"
        self.preview_directors.setText(f"导演：{directors}")
        self.preview_actors.setText(f"演员：{actors}")
        self.preview_summary.setPlainText(meta.get("summary") or "暂无简介")
        if self._poster_path and os.path.exists(self._poster_path):
            self.preview_poster.setPixmap(QPixmap(self._poster_path).scaled(120, 170, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            self.preview_poster.setText("")
        self.confirm_btn.setEnabled(True)

    def _confirm(self):
        if self._meta:
            self.page._apply_manual_metadata(self._meta, self._poster_path)
        self.accept()


class DetailPage(QWidget):
    back_clicked = Signal()

    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.item_id = None
        self._loading_timer = QTimer(self)
        self._loading_timer.setSingleShot(True)
        self._loading_timer.timeout.connect(self._finish_loading)
        self.loading_label = QLabel("正在加载…")
        self.loading_label.setStyleSheet("color: #9aa4b2; padding: 4px;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 16)
        lay.setSpacing(0)

        # Jellyfin 二级页面导航：返回、首页、菜单保持在内容上方，不再使用管理页式按钮。
        secondary = QWidget()
        secondary.setStyleSheet("background: #080808;")
        secondary_lay = QHBoxLayout(secondary)
        secondary_lay.setContentsMargins(22, 6, 22, 6)
        secondary_lay.setSpacing(12)
        self.secondary_back = QPushButton("‹")
        self.secondary_home = QPushButton("⌂")
        self.secondary_menu = QPushButton("≡")
        for button in (self.secondary_back, self.secondary_home, self.secondary_menu):
            button.setFixedSize(38, 32)
            button.setStyleSheet(
                "QPushButton { border: none; background: transparent; color: #eeeeee; "
                "font-size: 27px; } QPushButton:hover { color: #8fc7ff; background: #20242b; border-radius: 8px; }"
            )
            secondary_lay.addWidget(button)
        secondary_lay.addStretch(1)
        self.secondary_back.clicked.connect(self.win._back_to_grid)
        self.secondary_home.clicked.connect(self.win._show_continue)
        # V7：详情页只保留主导航，旧二级工具栏不再显示。
        secondary.hide()

        top = QHBoxLayout()
        top.setContentsMargins(24, 4, 24, 0)
        top.addStretch(1)
        self.douban_link = QPushButton("豆瓣页面 ↗")
        self.douban_link.setFixedHeight(36)
        self.douban_link.setStyleSheet(
            "QPushButton { border: 1px solid rgba(255,255,255,120); border-radius: 7px; "
            "background: transparent; color: #d8dde5; padding: 0 14px; } "
            "QPushButton:hover { border-color: rgba(255,255,255,200); background: rgba(255,255,255,30); }"
        )
        self.douban_link.clicked.connect(self._open_douban)

        self.backdrop = BackdropBanner()
        self.backdrop.setMinimumHeight(320)
        lay.addWidget(self.loading_label)

        info = QHBoxLayout()
        info.setSpacing(16)
        info.setContentsMargins(52, 0, 32, 0)
        info.setAlignment(Qt.AlignTop)
        self.poster = QLabel()
        self.poster.setFixedSize(220, 290)
        self.poster.setAlignment(Qt.AlignCenter)
        # V8：海报是独立前景层，不参与 backdrop 的模糊和渐变遮罩。
        self.poster.setAttribute(Qt.WA_TranslucentBackground)
        self.poster.setStyleSheet(
            "background: #232933; border: 1px solid rgba(255,255,255,80); "
            "border-radius: 8px; color: #4a5568;"
        )
        poster_shadow = QGraphicsDropShadowEffect(self.poster)
        poster_shadow.setBlurRadius(24)
        poster_shadow.setOffset(0, 8)
        poster_shadow.setColor(QColor(0, 0, 0, 180))
        self.poster.setGraphicsEffect(poster_shadow)
        info.addWidget(self.poster, 0, Qt.AlignTop)

        right = QVBoxLayout()
        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 34px; font-weight: 700; color: #f2f4f7;")
        right.addWidget(self.title_label)
        self.rating_label = QLabel()
        self.rating_label.setStyleSheet("font-size: 16px; color: #c7cbd1;")
        right.addWidget(self.rating_label)
        self.original_label = QLabel()
        self.original_label.setStyleSheet("font-size: 13px; color: #aeb8c6;")
        right.addWidget(self.original_label)
        self.meta_label = QLabel()
        self.meta_label.setWordWrap(True)
        self.meta_label.setStyleSheet("font-size: 16px; color: #c7cbd1;")
        right.addWidget(self.meta_label)

        self.people_label = QLabel()
        self.people_label.setWordWrap(True)
        self.people_label.setMaximumHeight(34)
        self.people_label.setStyleSheet("font-size: 14px; color: #b8c1cd; padding: 2px 0;")
        right.addWidget(self.people_label)

        # V10：前景文字增加轻微阴影，确保在模糊 backdrop 上始终清晰。
        for foreground_label in (self.title_label, self.rating_label, self.original_label, self.meta_label, self.people_label):
            text_shadow = QGraphicsDropShadowEffect(foreground_label)
            text_shadow.setBlurRadius(8)
            text_shadow.setOffset(1, 1)
            text_shadow.setColor(QColor(0, 0, 0, 220))
            foreground_label.setGraphicsEffect(text_shadow)

        actions = QHBoxLayout()
        self.play_primary = QPushButton("播放")
        self.play_primary.setObjectName("primary")
        self.play_primary.setFixedHeight(40)
        self.play_primary.setStyleSheet(
            "QPushButton#primary { background: #3b82f6; border: none; border-radius: 10px; "
            "padding: 0 18px; color: white; font-weight: 600; } "
            "QPushButton#primary:hover { background: #5798ff; }"
        )
        self.play_primary.clicked.connect(self._play_first)
        self.favorite_btn = QPushButton("收藏")
        self.favorite_btn.clicked.connect(self._toggle_favorite)
        self.watched_btn = QPushButton("标记已观看")
        self.watched_btn.clicked.connect(self._toggle_all_watched)
        glass_button = (
            "QPushButton { border: 1px solid rgba(255,255,255,128); border-radius: 7px; "
            "background: rgba(255,255,255,24); color: #f2f4f7; padding: 7px 14px; } "
            "QPushButton:hover { border-color: rgba(255,255,255,190); background: rgba(255,255,255,45); }"
        )
        self.favorite_btn.setStyleSheet(glass_button)
        self.watched_btn.setStyleSheet(glass_button)
        self.favorite_btn.setFixedHeight(36)
        self.watched_btn.setFixedHeight(36)
        actions.addWidget(self.play_primary)
        actions.addWidget(self.favorite_btn)
        actions.addWidget(self.watched_btn)
        actions.addWidget(self.douban_link)
        actions.addStretch(1)
        right.addLayout(actions)

        # 手动搜豆瓣补全
        manual_widget = QWidget()
        manual = QHBoxLayout(manual_widget)
        manual.setContentsMargins(0, 0, 0, 0)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("片名搜不到？在这里搜豆瓣条目补全评分和海报")
        self.search_input.setClearButtonEnabled(True)
        self.search_btn = QPushButton("搜索")
        self.search_input.setStyleSheet(
            "QLineEdit { border: 1px solid rgba(255,255,255,128); border-radius: 7px; "
            "background: rgba(255,255,255,18); color: #f2f4f7; padding: 7px 10px; } "
            "QLineEdit:focus { border-color: rgba(255,255,255,190); }"
        )
        self.search_btn.setStyleSheet(glass_button)
        self.search_btn.setFixedHeight(36)
        self.search_btn.clicked.connect(self._manual_search)
        self.search_input.returnPressed.connect(self._manual_search)
        manual.addWidget(self.search_input, 1)
        manual.addWidget(self.search_btn)
        manual_widget.hide()
        right.addWidget(manual_widget)
        self.manual_widget = manual_widget

        self.more_btn = QPushButton("⋯ 更多")
        self.more_btn.setFixedHeight(32)
        self.more_btn.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #b9c3d0; padding: 2px 0; } "
            "QPushButton:hover { color: #ffffff; }"
        )
        more_menu = QMenu(self)
        more_menu.addAction("补全豆瓣资料", lambda: self.manual_widget.setVisible(not self.manual_widget.isVisible()))
        more_menu.addAction("手动修正影片资料", self._open_manual_metadata)
        more_menu.addAction("打开豆瓣页面", self._open_douban)
        self.more_btn.setMenu(more_menu)
        actions.addWidget(self.more_btn)

        self.search_results = QListWidget()
        self.search_results.setMaximumHeight(130)
        self.search_results.hide()
        self.search_results.itemDoubleClicked.connect(self._apply_selected)
        right.addWidget(self.search_results)

        self.summary = QTextBrowser()
        self.summary.setStyleSheet(
            "QTextBrowser { border: none; background: transparent; color: #d8dde5; "
            "padding: 2px 0; }"
        )
        self.summary.setOpenExternalLinks(True)
        self.summary.setMaximumHeight(64)
        right.addWidget(self.summary)
        self.summary_toggle = QPushButton("展开简介")
        self.summary_toggle.setCheckable(True)
        self.summary_toggle.setStyleSheet(
            "QPushButton { border: none; background: transparent; color: #8fbfff; padding: 2px 0; } "
            "QPushButton:hover { color: #ffffff; }"
        )
        self.summary_toggle.clicked.connect(self._toggle_summary)
        right.addWidget(self.summary_toggle, 0, Qt.AlignLeft)
        info.addLayout(right, 1)

        # V11：Hero 高度由海报/信息内容自动撑开，避免标题顶部被裁切。
        hero = QWidget()
        hero.setMinimumHeight(320)
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        hero.setAttribute(Qt.WA_TranslucentBackground)
        hero_grid = QGridLayout(hero)
        # V12.1：仅提升前景信息层，不改变 backdrop 和海报尺寸。
        hero_grid.setContentsMargins(0, 0, 0, 32)
        hero_grid.setSpacing(0)
        hero_grid.addWidget(self.backdrop, 0, 0)
        info_container = QWidget()
        info_container.setAttribute(Qt.WA_TranslucentBackground)
        info_container.setStyleSheet("background-color: rgba(0, 0, 0, 0);")
        info_container.setLayout(info)
        hero_grid.addWidget(info_container, 0, 0, Qt.AlignBottom)
        lay.addWidget(hero)

        file_header = QHBoxLayout()
        ft = QLabel("文件")
        self.file_header_label = ft
        ft.setStyleSheet("font-size: 15px; font-weight: 600;")
        file_header.addWidget(ft)
        file_header.addStretch(1)
        self.file_count = QLabel("")
        self.file_count.setStyleSheet("color: #9aa4b2;")
        file_header.addWidget(self.file_count)
        lay.addLayout(file_header)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["集号", "集标题", "简介", "进度", "状态", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        for c in (1, 3, 4, 5):
            self.table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        lay.addWidget(self.table, 1)
        self.episode_scroll = QScrollArea()
        self.episode_scroll.setWidgetResizable(True)
        self.episode_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        MainWindow._install_cinema_scrollbar(self.episode_scroll)
        self.episode_cards = QWidget()
        self.episode_cards_layout = QVBoxLayout(self.episode_cards)
        self.episode_cards_layout.setContentsMargins(0, 0, 0, 0)
        self.episode_cards_layout.setSpacing(8)
        self.episode_scroll.setWidget(self.episode_cards)
        lay.addWidget(self.episode_scroll, 1)
        self.episode_scroll.hide()
        self.loading_label.hide()

    def _finish_loading(self):
        self.loading_label.hide()

    def load(self, item_id: int):
        """Load details without allowing a failed enrichment step to hang the page."""
        self.loading_label.show()
        self._loading_timer.start(5000)
        try:
            self._load_impl(item_id)
        except Exception as exc:
            self.loading_label.setText(f"部分信息加载失败，已保留可用内容：{exc}")
        finally:
            self._finish_loading()
            self._loading_timer.stop()

    def _toggle_summary(self, expanded: bool):
        self.summary.setMaximumHeight(300 if expanded else 64)
        self.summary_toggle.setText("收起简介" if expanded else "展开简介")

    def _manual_search(self):
        query = self.search_input.text().strip()
        if not query or not self.item_id:
            return
        self.search_btn.setEnabled(False)
        self.search_results.clear()
        self.search_results.show()
        self.search_results.addItem("正在搜索豆瓣…")
        worker = ManualSearchWorker(self.win.client, query)
        worker.result.connect(self._show_results)
        worker.finished_search.connect(lambda: self.search_btn.setEnabled(True))
        worker.finished_search.connect(lambda: worker.deleteLater())
        self._manual_worker = worker
        worker.start()

    def _show_results(self, results: list):
        self.search_results.clear()
        if not results:
            self.search_results.addItem("没有找到，换个关键词试试")
            return
        for r in results:
            rating = f"{r['rating']:.1f} 分" if r.get("rating") is not None else "暂无评分"
            year = r.get("year") or ""
            text = f"{r['title']} ({year}) {rating}  [id:{r['id']}]"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, r["id"])
            self.search_results.addItem(item)
        self.search_results.addItem("双击条目即可写入评分和海报")

    def _apply_selected(self, item: QListWidgetItem):
        sid = item.data(Qt.UserRole)
        if not sid or not self.item_id:
            return
        row = self.win.store.get_item(self.item_id)
        if not row:
            return
        self.search_results.addItem("正在抓取详情与海报…")
        worker = ApplySubjectWorker(self.win.client, self.item_id, row["title"], row["kind"], sid)
        worker.done.connect(self._subject_applied)
        worker.failed.connect(self._subject_failed)
        self._apply_worker = worker
        worker.start()

    def _subject_applied(self, item_id: int, meta: dict, poster_path: str):
        fields = {
            "douban_id": meta.get("douban_id"),
            "douban_title": meta.get("douban_title"),
            "rating": meta.get("rating"),
            "votes": meta.get("votes"),
            "year": meta.get("year"),
            "summary": meta.get("summary"),
            "poster": poster_path or "",
        }
        self.win.store.update_meta(item_id, **fields)
        self.search_results.clear()
        self.search_results.addItem("已写入豆瓣信息，评分和海报已更新")
        self.load(item_id)
        self.win.grid.update_item(item_id, fields["rating"], poster_path or "")

    def _subject_failed(self, item_id: int):
        self.search_results.clear()
        self.search_results.addItem("抓取失败，稍后再试或换一个条目")

    def _open_manual_metadata(self):
        if not self.item_id:
            return
        row = self.win.store.get_item(self.item_id)
        if row:
            dialog = ManualMetadataDialog(self, row)
            dialog.exec()

    def _apply_manual_metadata(self, meta: dict, poster_path: str):
        """只更新当前条目的展示资料，不触碰文件、播放和收藏数据。"""
        if not self.item_id:
            return
        row = self.win.store.get_item(self.item_id)
        if not row:
            return
        old_poster = str(row["poster"] or "")
        self._invalidate_poster_cache(old_poster, poster_path)
        fields = {}
        title = meta.get("douban_title")
        if title:
            fields["title"] = title
        if meta.get("year"):
            fields["year"] = meta["year"]
        if meta.get("summary"):
            fields["summary"] = meta["summary"]
        if poster_path:
            fields["poster"] = poster_path
        if fields:
            self.win.store.update_meta(self.item_id, **fields)
        if "directors" in meta or "actors" in meta:
            self.win.store.replace_item_metadata(
                self.item_id,
                directors=meta.get("directors", []),
                actors=meta.get("actors", []),
            )
        self.load(self.item_id)
        self.win.grid.update_item(self.item_id, row["rating"], fields.get("poster", row["poster"] or ""))

    def _invalidate_poster_cache(self, old_path: str, new_path: str):
        """清掉旧的 images 优先记录，确保 resolve() 使用最新 poster 字段。"""
        try:
            self.win.store.conn.execute(
                "DELETE FROM images WHERE item_id=? AND type='poster'", (self.item_id,)
            )
            self.win.store.conn.commit()
        except Exception:
            # 兼容尚未创建 images 表的旧数据库。
            pass
        if not old_path or old_path == new_path or not os.path.isfile(old_path):
            return
        try:
            cache_root = os.path.abspath(str(self.win.config.cache_dir))
            old_abs = os.path.abspath(old_path)
            if os.path.commonpath((cache_root, old_abs)) == cache_root:
                os.remove(old_abs)
        except (OSError, ValueError):
            pass

    def _open_douban(self):
        if self.item_id:
            row = self.win.store.get_item(self.item_id)
            if row and row["douban_id"]:
                QDesktopServices.openUrl(QUrl(f"https://movie.douban.com/subject/{row['douban_id']}/"))

    def _load_impl(self, item_id: int):
        self.item_id = item_id
        row = self.win.store.get_item(item_id)
        if not row:
            return
        self.title_label.setText(row["title"])
        self.original_label.setText(f"原名：{row['original_title']}" if row["original_title"] else "")
        rating = row["rating"]
        parts = []
        if rating:
            parts.append(f"豆瓣 {rating:.1f} 分")
        if row["votes"]:
            parts.append(f"{row['votes']:,} 人评分")
        if row["year"]:
            parts.append(str(row["year"]))
        self.rating_label.setText(" · ".join(parts) if parts else "暂无豆瓣评分")
        metadata = self.win.store.get_item_metadata(item_id)
        genres = "、".join(metadata["genres"]) or "暂无类型"
        countries = "、".join(metadata["countries"])
        runtime = row["runtime_minutes"]
        meta_parts = [genres]
        if countries:
            meta_parts.append(countries)
        if runtime:
            meta_parts.append(f"{int(runtime)} 分钟")
        self.meta_label.setText(" · ".join(meta_parts))
        directors = "、".join(metadata["directors"]) or "暂无"
        actors = "、".join(a["name"] for a in metadata["actors"][:12]) or "暂无"
        self.people_label.setText(f"导演：{directors}    演员：{actors}")
        self.summary.setPlainText(row["summary"] or "暂无简介")
        self.summary_toggle.setChecked(False)
        self._toggle_summary(False)
        poster = self.win.images.resolve(row, "poster") or (row["poster"] or "")
        backdrop = self.win.images.resolve(row, "backdrop") or (row["backdrop"] or "")
        self.backdrop.set_path(backdrop, poster)
        if poster and os.path.exists(poster):
            pm = QPixmap(poster).scaled(220, 290, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            self.poster.setPixmap(pm)
            self.poster.setFixedSize(220, 290)
        else:
            self.poster.setText("暂无海报")
            self.poster.setPixmap(QPixmap())

        files = self.win.store.list_files(item_id)
        if row["kind"] == "tv":
            season = next((int(f["season"]) for f in files if f["season"]), 1)
            self.file_header_label.setText(f"第 {season} 季")
        else:
            self.file_header_label.setText("文件")
        self.favorite_btn.setText("取消收藏" if self.win.store.is_favorite(item_id) else "收藏")
        watched_count = sum(1 for f in files if f["watched"])
        self.watched_btn.setText("取消已观看" if files and watched_count == len(files) else "标记已观看")
        self.play_primary.setText("继续播放" if any(f["progress"] > 0 and not f["watched"] for f in files) else "播放")
        self.file_count.setText(f"{len(files)} 个文件")
        self.table.setRowCount(len(files))
        for i, f in enumerate(files):
            ep = f"{f['season']:02d}E{f['episode']:02d}" if f["season"] and f["episode"] else ("-")
            self.table.setItem(i, 0, QTableWidgetItem(f"S{ep}" if ep != "-" else "-"))
            self.table.setItem(i, 1, QTableWidgetItem(f["episode_title"] or f["filename"]))
            self.table.setItem(i, 2, QTableWidgetItem(f["overview"] or "暂无简介"))
            prog = f["progress"]
            dur = f["duration"]
            if prog > 0 and dur > 0:
                pct = min(100, int(prog / dur * 100))
                self.table.setItem(i, 3, QTableWidgetItem(f"{fmt_time(prog)} / {fmt_time(dur)} ({pct}%)"))
            elif prog > 0:
                self.table.setItem(i, 3, QTableWidgetItem(f"{fmt_time(prog)}"))
            else:
                self.table.setItem(i, 3, QTableWidgetItem("未观看"))
            self.table.setItem(i, 4, QTableWidgetItem("已看完" if f["watched"] else (f["playback_state"] or "未观看")))

            cell = QWidget()
            hl = QHBoxLayout(cell)
            hl.setContentsMargins(4, 2, 4, 2)
            hl.setSpacing(6)
            play = QPushButton("播放")
            play.clicked.connect(lambda _, p=f["path"]: self.win.play(p, resume=True))
            more = QPushButton("更多")
            more.setMenu(self._episode_menu(f))
            hl.addWidget(play)
            hl.addWidget(more)
            hl.addStretch(1)
            self.table.setCellWidget(i, 5, cell)

        is_tv = row["kind"] == "tv"
        self.file_header_label.setVisible(not is_tv)
        self.file_count.setVisible(not is_tv)
        self.table.setVisible(not is_tv)
        self.episode_scroll.setVisible(is_tv)
        if is_tv:
            self._render_episode_cards(files, poster)

    def _render_episode_cards(self, files, fallback_image: str = ""):
        while self.episode_cards_layout.count():
            item = self.episode_cards_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        groups = {}
        for file_row in files:
            groups.setdefault(int(file_row["season"] or 0), []).append(file_row)
        seasons = sorted(groups.items())
        if not seasons:
            self.episode_cards_layout.addStretch(1)
            return

        # V8：Season 使用横向 tabs；下面的内容区只保留当前选中的一季。
        tabs = QWidget()
        tab_layout = QHBoxLayout(tabs)
        tab_layout.setContentsMargins(0, 0, 0, 8)
        tab_layout.setSpacing(8)
        stack = QStackedWidget()
        stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._season_stack = stack
        self._season_tabs = []

        for index, (season, season_files) in enumerate(seasons):
            tab = QPushButton(f"第 {season} 季")
            tab.setCheckable(True)
            tab.setFixedHeight(36)
            tab.setMinimumWidth(80)
            tab.clicked.connect(lambda checked=False, i=index: self._select_season_tab(i))
            tab_layout.addWidget(tab)
            self._season_tabs.append(tab)

            content = QWidget()
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(0, 0, 0, 8)
            content_layout.setSpacing(6)
            for file_row in season_files:
                card = self._make_episode_card(file_row)
                content_layout.addWidget(card)
            stack.addWidget(content)

        tab_layout.addStretch(1)
        self.episode_cards_layout.addWidget(tabs)
        self.episode_cards_layout.addWidget(stack, 1)
        self.episode_cards_layout.addStretch(1)
        self._select_season_tab(0)

    def _select_season_tab(self, index: int):
        """切换当前季，只显示对应的 Episode 列表。"""
        tabs = getattr(self, "_season_tabs", [])
        stack = getattr(self, "_season_stack", None)
        if not tabs or stack is None or not (0 <= index < len(tabs)):
            return
        stack.setCurrentIndex(index)
        for i, tab in enumerate(tabs):
            selected = i == index
            tab.setChecked(selected)
            tab.setStyleSheet(
                "QPushButton { border: 1px solid rgba(255,255,255,40); border-radius: 8px; "
                "background: rgba(255,255,255,18); color: #d7dce4; padding: 0 18px; } "
                "QPushButton:hover { background: rgba(255,255,255,35); color: #ffffff; }"
                if not selected else
                "QPushButton { border: none; border-radius: 8px; background: #3b82f6; "
                "color: #ffffff; padding: 0 18px; font-weight: 600; } "
                "QPushButton:hover { background: #5798ff; }"
            )

    def _make_episode_card(self, file_row):
            card = QFrame()
            card.setFixedHeight(54)
            card.setObjectName("episodeCard")
            card.setStyleSheet(
                "QFrame#episodeCard { background: transparent; border: none; border-radius: 8px; } "
                "QFrame#episodeCard:hover { background: rgba(255,255,255,10); }"
            )
            card_lay = QHBoxLayout(card)
            card_lay.setContentsMargins(10, 1, 8, 1)
            card_lay.setSpacing(8)

            season = int(file_row["season"] or 0)
            episode = int(file_row["episode"] or 0)
            number = f"S{season:02d}E{episode:02d}" if season and episode else "剧集"
            number_label = QLabel(number)
            number_label.setStyleSheet("font-size: 11px; color: #9aa4b2;")
            title = QLabel(file_row["episode_title"] or f"第{episode}集")
            title.setStyleSheet("font-size: 14px; font-weight: 600; color: #f2f4f7;")
            identity = QVBoxLayout()
            identity.setContentsMargins(0, 0, 0, 0)
            identity.setSpacing(0)
            identity.addWidget(number_label)
            identity.addWidget(title)
            identity_widget = QWidget()
            identity_widget.setStyleSheet("background: transparent;")
            identity_widget.setLayout(identity)
            identity_widget.setFixedWidth(150)
            card_lay.addWidget(identity_widget)

            middle = QHBoxLayout()
            middle.setContentsMargins(0, 0, 0, 0)
            middle.setSpacing(10)
            overview = QLabel(file_row["overview"] or "暂无简介")
            overview.setStyleSheet("color: #9aa4b2; font-size: 12px;")
            overview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            middle.addWidget(overview, 1)
            progress = file_row["progress"] or 0
            duration = file_row["duration"] or 0
            progress_text = f"{fmt_time(progress)} / {fmt_time(duration)}" if duration else "未观看"
            if file_row["watched"]:
                state_text = "观看完成"
            elif progress and duration:
                state_text = f"{min(100, int(progress / duration * 100))}% 已观看"
            else:
                state_text = "未观看"
            meta = QLabel(state_text if state_text == "未观看" else f"{progress_text} · {state_text}")
            meta.setStyleSheet("color: #8fbfff; font-size: 11px;")
            meta.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            middle.addWidget(meta)
            middle_widget = QWidget()
            middle_widget.setStyleSheet("background: transparent;")
            middle_widget.setLayout(middle)
            card_lay.addWidget(middle_widget, 1)

            play = QPushButton("▶播放")
            play.setFixedHeight(30)
            play.setFixedWidth(76)
            play.setStyleSheet(
                "QPushButton { background: #3b82f6; border: none; border-radius: 6px; "
                "color: #ffffff; padding: 0 8px; } "
                "QPushButton:hover { background: #5798ff; }"
            )
            play.clicked.connect(lambda _, p=file_row["path"]: self.win.play(p, resume=True))
            card_lay.addWidget(play)
            more = QPushButton("⋮")
            more.setFixedSize(28, 32)
            more.setStyleSheet("QPushButton { border: none; background: transparent; color: #cbd5e1; font-size: 20px; } QPushButton:hover { color: white; }")
            more.setMenu(self._episode_menu(file_row))
            card_lay.addWidget(more)
            return card

    def _episode_menu(self, file_row):
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #202020; color: #f2f2f2; border: 1px solid #3a3a3a; "
            "border-radius: 6px; padding: 5px; } "
            "QMenu::item { padding: 7px 24px 7px 12px; border-radius: 4px; } "
            "QMenu::item:selected { background: #3a3a3a; color: #ffffff; }"
        )
        menu.addAction("继续播放", lambda p=file_row["path"]: self.win.play(p, resume=True))
        menu.addAction("打开文件位置", lambda p=file_row["path"]: self._open_file_location(p))
        watched = bool(file_row["watched"])
        menu.addAction("标记未观看" if watched else "标记已观看",
                       lambda p=file_row["path"], w=watched: self._toggle_watched(p, w))
        menu.addSeparator()
        menu.addAction("删除文件", lambda p=file_row["path"]: self._delete_file(p))
        return menu

    @staticmethod
    def _open_file_location(path: str):
        if os.path.exists(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])

    def _delete_file(self, path: str):
        name = os.path.basename(path)
        answer = QMessageBox.question(
            self, "确认删除", f"确定要删除文件吗？\n{name}\n此操作不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
            self.win.store.delete_file_record(path)
            if self.item_id:
                self.load(self.item_id)
        except Exception as exc:
            QMessageBox.warning(self, "删除失败", str(exc))

    def _play_first(self):
        if not self.item_id:
            return
        files = self.win.store.list_files(self.item_id)
        if files:
            self.win.play(files[0]["path"], resume=True)

    def _toggle_favorite(self):
        if not self.item_id:
            return
        if self.win.store.is_favorite(self.item_id):
            self.win.store.remove_favorite(self.item_id)
        else:
            self.win.store.add_favorite(self.item_id)
        self.load(self.item_id)

    def _toggle_all_watched(self):
        if not self.item_id:
            return
        files = self.win.store.list_files(self.item_id)
        mark_watched = not files or not all(f["watched"] for f in files)
        for f in files:
            self.win.store.set_watched(f["path"], mark_watched)
        self.load(self.item_id)

    def _toggle_watched(self, path: str, watched: bool):
        self.win.store.set_watched(path, not watched)
        if self.item_id:
            self.load(self.item_id)
            self.win._show_kind(self.win.current_kind) if self.win.current_kind in ("tv", "movie") else None


class OrganizePage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        self.plan = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)

        head = QHBoxLayout()
        t = QLabel("整理模式")
        t.setStyleSheet("font-size: 20px; font-weight: 700;")
        head.addWidget(t)
        head.addStretch(1)
        self.refresh_btn = QPushButton("重新扫描整理计划")
        self.refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self.refresh_btn)
        self.apply_btn = QPushButton("执行整理")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply)
        head.addWidget(self.apply_btn)
        self.undo_btn = QPushButton("撤销上次整理")
        self.undo_btn.clicked.connect(self.undo)
        head.addWidget(self.undo_btn)
        lay.addLayout(head)

        tip = QLabel("说明：自动归类乱放文件并清理垃圾——样片、下载残留移入本地回收站（可撤销），空目录删除，"
                     "电影目录里的剧集归位到电视剧目录。被占用（正在播放/做种）的文件会自动跳过，所有操作都可撤销。")
        tip.setWordWrap(True)
        tip.setStyleSheet("color: #9aa4b2; padding: 4px 0 8px 0;")
        lay.addWidget(tip)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["整理项", "来源 → 目标"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.tree.header().setSectionResizeMode(1, QHeaderView.Stretch)
        lay.addWidget(self.tree, 3)

        self.log = QTextBrowser()
        self.log.setMaximumHeight(140)
        lay.addWidget(self.log, 1)

    def refresh(self):
        self.tree.clear()
        self.log.clear()
        self.refresh_btn.setEnabled(False)
        self.worker = OrganizePlanWorker(
            self.win.config.get("tv_root"),
            self.win.config.get("movie_root"),
            str(self.win.config.trash_dir),
        )
        self.worker.finished_plan.connect(self._plan_done)
        self.worker.error.connect(lambda e: self.log.append(f"错误：{e}"))
        self.worker.finished_plan.connect(lambda _: self.refresh_btn.setEnabled(True))
        self.worker.error.connect(lambda _: self.refresh_btn.setEnabled(True))
        self.log.append("正在扫描整理计划…")
        self.worker.start()

    def _plan_done(self, plan):
        self.plan = plan
        groups: dict[str, list] = {}
        for op in plan.ops:
            groups.setdefault(op.kind, []).append(op)
        order = ["movie_to_tv", "tv_flatten", "movie_flatten", "sample_trash", "junk_trash", "empty_dir_del"]
        labels = {
            "movie_to_tv": "剧集归位（电影目录 → 电视剧目录）",
            "tv_flatten": "电视剧：单集发布组目录提升",
            "movie_flatten": "电影：嵌套目录提升",
            "sample_trash": "样片清理（移入本地回收站）",
            "junk_trash": "下载残留清理（移入本地回收站）",
            "empty_dir_del": "空目录删除",
        }
        for gname in order:
            ops = groups.get(gname)
            if not ops:
                continue
            label = labels.get(gname, gname)
            top = QTreeWidgetItem([label, f"{len(ops)} 项"])
            for op in ops:
                child = QTreeWidgetItem([op.label, f"{op.source}  →  {op.target}"])
                child.setCheckState(0, Qt.Checked)
                child.setData(0, Qt.UserRole, f"{op.source}\t{op.target}")
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(True)
        self.apply_btn.setEnabled(plan.count > 0)
        self.log.append(f"发现 {plan.count} 项可整理内容")

    def apply(self):
        if not self.plan or self.plan.count == 0:
            return
        selected = []
        has_tv_move = False
        for i in range(self.tree.topLevelItemCount()):
            top = self.tree.topLevelItem(i)
            for j in range(top.childCount()):
                child = top.child(j)
                if child.checkState(0) == Qt.Checked:
                    src, dst = child.data(0, Qt.UserRole).split("\t")
                    selected.append((src, dst))
                    if top.text(0).startswith("剧集归位"):
                        has_tv_move = True
        if not selected:
            self.log.append("没有勾选任何整理项")
            return
        if has_tv_move:
            ret = QMessageBox.question(
                self, "确认整理",
                "包含剧集归位（从电影目录移到电视剧目录）。\n"
                "跨共享移动会先复制文件再删除原文件，体积大的剧集可能需要较长时间。\n\n"
                "继续执行吗？",
            )
            if ret != QMessageBox.Yes:
                return
        from .organize import MoveOp, OrganizePlan
        plan = OrganizePlan(ops=[MoveOp(s, d, "sel", "") for s, d in selected])
        self.apply_btn.setEnabled(False)
        self.worker = OrganizeApplyWorker(plan, str(self.win.config.undo_path))
        self.worker.log_line.connect(self.log.append)
        self.worker.finished_apply.connect(self._after_apply)
        self.worker.start()

    def _after_apply(self):
        self.apply_btn.setEnabled(True)
        self.log.append("整理完成，请重新扫描媒体库（主界面右上角）。")

    def undo(self):
        self.undo_btn.setEnabled(False)
        self.worker = UndoWorker(str(self.win.config.undo_path))
        self.worker.log_line.connect(self.log.append)
        self.worker.finished_undo.connect(lambda: self.undo_btn.setEnabled(True))
        self.worker.start()


class SettingsPage(QWidget):
    def __init__(self, win: MainWindow):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        t = QLabel("设置")
        t.setStyleSheet("font-size: 20px; font-weight: 700;")
        lay.addWidget(t)

        form = QFormLayout()
        form.setVerticalSpacing(14)
        self.tv_root = QLineEdit(str(win.config.get("tv_root", "")))
        self.movie_root = QLineEdit(str(win.config.get("movie_root", "")))
        self.potplayer = QLineEdit(str(win.config.get("potplayer", "")))
        self.douban = QCheckBox("自动抓取豆瓣评分与海报")
        self.douban.setChecked(bool(win.config.get("douban_enabled", True)))
        self.delay = QSpinBox()
        self.delay.setRange(0, 3)
        self.delay.setSingleStep(1)
        self.delay.setValue(int(float(win.config.get("request_delay", 0.4))))
        form.addRow("电视剧目录", self.tv_root)
        form.addRow("电影目录", self.movie_root)
        form.addRow("PotPlayer 路径", self.potplayer)
        form.addRow("", self.douban)
        form.addRow("豆瓣请求间隔(秒)", self.delay)
        lay.addLayout(form)

        btn_row = QHBoxLayout()
        save = QPushButton("保存并重新扫描")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        btn_row.addWidget(save)
        btn_row.addStretch(1)
        lay.addLayout(btn_row)
        lay.addStretch(1)

    def _save(self):
        cfg = self.win.config
        cfg.set("tv_root", self.tv_root.text().strip())
        cfg.set("movie_root", self.movie_root.text().strip())
        cfg.set("potplayer", self.potplayer.text().strip())
        cfg.set("douban_enabled", self.douban.isChecked())
        cfg.set("request_delay", self.delay.value())
        self.win.client = DoubanClient(cfg.cache_dir, delay=float(self.delay.value()))
        self.win.scan()
