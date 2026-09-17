"""PySide6 界面。"""

from __future__ import annotations

import os
import json
import re
import random
import subprocess
import time
import ctypes
import ctypes.wintypes as wintypes
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import (
    QModelIndex,
    QPoint,
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
    QCursor,
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
    QDoubleSpinBox,
    QGraphicsBlurEffect,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
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
    QWidgetAction,
)
from PySide6.QtGui import QStandardItem, QStandardItemModel

from .config import Config
from .douban import DoubanClient
from .store import Store
from .image_provider import ImageProviderManager
from .subscription_dialog import SubscriptionAutoSync, SubscriptionSyncDialog
from .subscriptions import (
    DEFAULT_SUBSCRIPTION_URL,
    _season_number,
    subscription_poster_is_recent,
    subscription_has_undownloaded_update,
    subscription_update_timestamp,
    titles_match,
)
from .workers import (
    ApplySubjectWorker,
    DoubanTask,
    DoubanSignals,
    ManualSearchWorker,
    OrganizeApplyWorker,
    OrganizePlanWorker,
    RecentFilesWorker,
    ScanWorker,
    SubscriptionHighResWorker,
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
    # 顶部“我的媒体”和首页频道标题使用同一套尺寸与字重。
    "title": (15, QFont.DemiBold),
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
QScrollBar:vertical { background: transparent; width: 8px; margin: 0px; }
QScrollBar::handle:vertical { background: rgba(170, 182, 201, 128); border-radius: 4px; min-height: 30px; }
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
QLabel#sectionTitle { color: #f2f4f7; font-size: 15px; font-weight: 600; }
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
        poster_height = _iphone_duo_poster_size(156)[1]
        return QSize(168, poster_height + 12)

    def _pix(self, path: str) -> QPixmap | None:
        if not path or not os.path.exists(path):
            return None
        if path not in self._pix_cache:
            pm = QPixmap(path)
            if not pm.isNull():
                self._pix_cache[path] = pm.scaled(
                    156, _iphone_duo_poster_size(156)[1],
                    Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
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

        poster_width = 156
        poster_height = _iphone_duo_poster_size(poster_width)[1]
        radius = _iphone_duo_corner_radius(poster_width, poster_height)
        card = QRectF(rect.x() + 6, rect.y() + 6, poster_width, poster_height)
        path = QPainterPath()
        path.addRoundedRect(card, radius, radius)

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
        # 首页“我的媒体”两张入口海报按原比例缩小到原来的约三分之二。
        self.setFixedSize(280, 157)
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
        radius = _home_poster_radius(self.width(), self.height())
        path.addRoundedRect(QRectF(self.rect()), radius, radius)
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


class _HoverMenu(QMenu):
    """Popup menu that reports pointer exit so it can close predictably."""

    entered = Signal()
    left = Signal()

    def enterEvent(self, event):
        self.entered.emit()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.left.emit()
        super().leaveEvent(event)


class MediaCategoryTitle(QLabel):
    """首页“我的媒体”标题及其悬停分类菜单。"""

    category_clicked = Signal(str)
    CATEGORIES = ("电视剧", "电影", "欧美剧", "韩国", "中国", "动画片", "演唱会", "科学")

    def __init__(self, text: str = "我的媒体", parent=None):
        super().__init__(text, parent)
        self._menu_enabled = True
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self._menu = _HoverMenu(self)
        self._menu.setAttribute(Qt.WA_TranslucentBackground, True)
        self._menu.setWindowFlag(Qt.FramelessWindowHint, True)
        self._menu.setStyleSheet(
            "QMenu { background: rgba(28, 28, 30, 232); "
            "border: 1px solid rgba(255,255,255,46); border-radius: 13px; padding: 0; }"
        )
        # Avoid a per-hover graphics-effect repaint. The translucent surface
        # and border provide the glass edge without making the popup feel late.
        self._menu.setGraphicsEffect(None)
        self._show_timer = QTimer(self)
        self._show_timer.setSingleShot(True)
        self._show_timer.setInterval(45)
        self._show_timer.timeout.connect(self._show_menu_now)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(120)
        self._hide_timer.timeout.connect(self._hide_menu_if_outside)
        self._menu.entered.connect(self._hide_timer.stop)
        self._menu.left.connect(self._hide_menu_later)
        self._menu.aboutToHide.connect(self._show_timer.stop)
        self._menu.aboutToHide.connect(self._hide_timer.stop)

        panel = QFrame()
        panel.setAttribute(Qt.WA_StyledBackground, True)
        panel.setStyleSheet("QFrame { background: transparent; }")
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(7, 7, 7, 7)
        panel_layout.setSpacing(3)
        action = QWidgetAction(self._menu)
        action.setDefaultWidget(panel)
        self._menu.addAction(action)

        for category in self.CATEGORIES:
            button = QPushButton(category, panel)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(24)
            button.setFont(role_font("meta"))
            button.setStyleSheet(
                "QPushButton { background: rgba(255,255,255,13); "
                "border: 1px solid rgba(255,255,255,26); border-radius: 8px; "
                "padding: 0 8px; color: #f3f4f6; font-size: 10px; } "
                "QPushButton:hover { background: rgba(255,255,255,34); "
                "border-color: rgba(255,255,255,72); }"
            )
            button.clicked.connect(lambda _checked=False, name=category: self._activate(name))
            panel_layout.addWidget(button)
        # Build the popup geometry once. Repeated hover events reuse it.
        self._menu.adjustSize()

    def set_menu_enabled(self, enabled: bool) -> None:
        self._menu_enabled = bool(enabled)
        if not self._menu_enabled:
            self._menu.hide()

    def _activate(self, category: str) -> None:
        self._menu.hide()
        self.category_clicked.emit(category)

    def _show_menu(self, immediate: bool = False) -> None:
        if not self._menu_enabled:
            return
        if self._menu.isVisible():
            return
        if not immediate:
            if not self._show_timer.isActive():
                self._show_timer.start()
            return
        self._show_timer.stop()
        self._show_menu_now()

    def _show_menu_now(self) -> None:
        if not self._menu_enabled or self._menu.isVisible():
            return
        # The title lives in the top navigation now. Anchor to that bar's
        # bottom edge, not to the label's own baseline, so the glass menu never
        # opens inside the navigation row or over the page title.
        anchor = self.parentWidget()
        bar = anchor.parentWidget() if anchor is not None else None
        if bar is not None:
            title_origin = self.mapToGlobal(QPoint(0, 0))
            bar_bottom = bar.mapToGlobal(QPoint(0, bar.height() + 2))
            point = QPoint(title_origin.x(), bar_bottom.y())
        elif anchor is not None:
            point = anchor.mapToGlobal(QPoint(0, anchor.height() + 2))
        else:
            point = self.mapToGlobal(QPoint(0, self.height() + 2))
        screen = QApplication.screenAt(point)
        if screen:
            area = screen.availableGeometry()
            x = max(area.left() + 8, min(point.x(), area.right() - self._menu.width() - 8))
            y = min(point.y(), area.bottom() - self._menu.height() - 8)
            point = QPoint(x, y)
        self._menu.popup(point)

    def _hide_menu_later(self) -> None:
        if self._menu.isVisible():
            self._hide_timer.start()

    def _hide_menu_if_outside(self) -> None:
        if not self._menu.isVisible():
            return
        cursor = QCursor.pos()
        over_title = self.rect().contains(self.mapFromGlobal(cursor))
        over_menu = self._menu.rect().contains(self._menu.mapFromGlobal(cursor))
        if not over_title and not over_menu:
            self._menu.hide()

    def enterEvent(self, event):
        self._show_menu()
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Cancel a popup that has not opened yet.  If it is open, give the
        # pointer a short bridge to the popup, then hide it when it leaves both
        # the title and the menu.
        self._show_timer.stop()
        if self._menu.isVisible():
            self._hide_menu_later()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._show_menu(immediate=True)
        super().mousePressEvent(event)


class ClickableLogo(QLabel):
    """Top-left logo that always returns to the home page when clicked."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _home_poster_radius(width: int, height: int) -> int:
    """按首页海报短边比例计算圆角，保持不同尺寸卡片的视觉比例一致。"""
    # 普通首页竖版海报为 160px 宽、7px 圆角，作为统一视觉基准。
    return max(4, round(min(width, height) * 7.0 / 160.0))


IPHONE_DUO_SCREEN_RATIO = 2670 / 1878
# 从用户提供的 iPhone Duo 图片测量：可见屏幕短边约 788px，角半径约 65px。
IPHONE_DUO_CORNER_RATIO = 65 / 788


def _iphone_duo_poster_size(width: int) -> tuple[int, int]:
    """把竖版订阅海报按竖置 iPhone Duo 可见屏幕的长宽比换算。"""
    return width, round(width * IPHONE_DUO_SCREEN_RATIO)


def _iphone_duo_corner_radius(width: int, height: int) -> int:
    """按 iPhone Duo 图片测得的圆角/短边比例计算圆角。"""
    return max(4, round(min(width, height) * IPHONE_DUO_CORNER_RATIO))


def _rounded_pixmap(pixmap: QPixmap, width: int, height: int, radius: float | None = None) -> QPixmap:
    """Clip artwork corners so a QPushButton icon cannot cover its rounding."""
    if radius is None:
        radius = _home_poster_radius(width, height)
    rounded = QPixmap(width, height)
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, width, height), radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pixmap)
    painter.setClipping(False)
    painter.end()
    return rounded


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
        radius = _home_poster_radius(350, 196)
        button.setStyleSheet(f"QPushButton {{ border: 1px solid #2b3038; border-radius: {radius}px; background: #20252c; }} QPushButton:hover {{ border: 2px solid #d7dde7; }}")
        if poster and os.path.exists(poster):
            pix = win._cover_pixmap(poster, 350, 196)
            button.setIcon(QIcon(_rounded_pixmap(pix, 350, 196, radius)))
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
        # Jellyfin 首页普通竖版海报统一使用竖置 iPhone Duo 的比例。
        self.setFixedWidth(160)
        poster_width, poster_height = _iphone_duo_poster_size(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(7)
        button = QPushButton()
        button.setFixedSize(poster_width, poster_height)
        button.setCursor(Qt.PointingHandCursor)
        radius = _iphone_duo_corner_radius(poster_width, poster_height)
        button.setStyleSheet(f"QPushButton {{ border: 1px solid transparent; border-radius: {radius}px; background: transparent; }} QPushButton:hover {{ border: 2px solid #d7dde7; }}")
        if poster and os.path.exists(poster):
            pix = win._cover_pixmap(poster, poster_width, poster_height)
            button.setIcon(QIcon(_rounded_pixmap(pix, poster_width, poster_height, radius)))
            button.setIconSize(QSize(poster_width, poster_height))
        else:
            button.setText("暂无海报")
        button.clicked.connect(lambda: win._open_detail(item_id))
        layout.addWidget(button)
        name = QLabel(title)
        name.setFont(role_font("card"))
        name.setMaximumWidth(poster_width)
        name.setWordWrap(False)
        name.setStyleSheet("color: #e3e3e3;")
        layout.addWidget(name)
        if subtitle:
            meta = QLabel(subtitle)
            meta.setFont(role_font("meta"))
            meta.setStyleSheet("color: #9d9d9d;")
            layout.addWidget(meta)


class _SubscriptionNewBadge(QLabel):
    """Small yellow 45-degree NEW ribbon used only on subscription posters."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.translate(self.width() / 2, self.height() / 2)
        painter.rotate(45)
        ribbon = QRectF(-32, -11, 64, 22)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#f5c542"))
        painter.drawRoundedRect(ribbon, 5, 5)
        font = QFont()
        font.setBold(True)
        font.setPixelSize(12)
        painter.setFont(font)
        painter.setPen(QColor("#171717"))
        painter.drawText(ribbon, Qt.AlignCenter, "NEW")
        painter.end()
        super().paintEvent(event)


class SubscriptionCard(QWidget):
    """Website-first subscription card with optional local media actions."""

    def __init__(
        self,
        win: "MainWindow",
        item_id: int | None,
        title: str,
        poster: str,
        updated_at: str,
        url: str,
        website_status: str = "",
        play_path: str = "",
        play_resume: bool = False,
        local_state: str = "not_downloaded",
        has_new_update: bool = False,
    ):
        super().__init__()
        poster_width, poster_height = _iphone_duo_poster_size(190)
        self.setFixedSize(204, 390)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        poster_btn = QPushButton()
        poster_btn.setFixedSize(poster_width, poster_height)
        poster_btn.setCursor(Qt.PointingHandCursor)
        radius = _iphone_duo_corner_radius(poster_width, poster_height)
        poster_btn.setStyleSheet(
            f"QPushButton {{ border: 1px solid transparent; border-radius: {radius}px; background: transparent; }} "
            "QPushButton:hover { border: 2px solid #d7dde7; }"
        )
        if poster and os.path.exists(poster):
            pix = win._cover_pixmap(poster, poster_width, poster_height)
            poster_btn.setIcon(QIcon(_rounded_pixmap(pix, poster_width, poster_height, radius)))
            poster_btn.setIconSize(QSize(poster_width, poster_height))
        else:
            poster_btn.setText("暂无海报")
        if has_new_update:
            badge = _SubscriptionNewBadge(poster_btn)
            badge.setGeometry(poster_width - 72, -4, 76, 76)
            badge.show()
            badge.raise_()
        # 订阅海报代表网站条目：点击在 MoviePoster 内打开 dyjie.net 详情页；
        # 本地播放仍由下方“本地播放”按钮负责。
        poster_btn.clicked.connect(lambda: win.open_subscription_page(url))
        layout.addWidget(poster_btn)

        name = QLabel(title)
        name.setFont(role_font("card"))
        name.setMaximumWidth(190)
        name.setWordWrap(True)
        name.setToolTip(title)
        name.setStyleSheet("color: #e3e3e3;")
        layout.addWidget(name)

        updated = QLabel(updated_at)
        updated.setFont(role_font("meta"))
        updated.setStyleSheet("color: #9d9d9d;")
        layout.addWidget(updated)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 14, 0)
        actions.setSpacing(6)
        view = QPushButton(website_status or "查看更新")
        view.setToolTip("在 MoviePoster 内查看 dyjie.net 详情页")
        view.setFixedHeight(28)
        view.clicked.connect(lambda: win.open_subscription_page(url))
        actions.addWidget(view, 1)

        if local_state == "no_next":
            local_text = "本地播放"
            local_enabled = True
        elif local_state == "available" and play_path:
            local_text = "本地播放"
            local_enabled = True
        elif local_state == "inaccessible":
            local_text = "路径不可访问"
            local_enabled = False
        else:
            local_text = "还未下载"
            local_enabled = False
        local = QPushButton(local_text)
        local.setFixedHeight(28)
        local.setEnabled(local_enabled)
        if local_state == "no_next":
            local.clicked.connect(lambda: win._show_playback_message("本地暂无下一集"))
        elif local_enabled:
            local.clicked.connect(lambda: win.play(play_path, resume=play_resume))
        actions.addWidget(local, 1)
        layout.addLayout(actions)
        layout.addStretch(1)

class MainWindow(QMainWindow):
    def __init__(self, config: Config, store: Store):
        super().__init__()
        self.font_family = configure_application_font(QApplication.instance())
        self.logo_path = Path(__file__).resolve().parent.parent / "assets" / "MoviePoster.png"
        if self.logo_path.exists():
            self.setWindowIcon(QIcon(str(self.logo_path)))
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
        self._play_timer.setInterval(1000)
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
        self._home_source_rows = None
        self._recent_sort_generation = 0
        self._recent_sort_keys = None
        self._recent_worker = None
        self._subscription_hd_worker = None
        self._poster_pixmap_cache: OrderedDict[tuple, QPixmap] = OrderedDict()
        self._poster_pixmap_cache_limit = 256
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(lambda: self._search_all(self.search.text()))
        self._closing = False
        self._close_poll_scheduled = False
        self.subscription_items: list[dict[str, str]] = []
        self._subscription_item_ids: set[int] = set()
        self._load_subscription_cache()
        subscription_url = str(self.config.get("subscription_url", DEFAULT_SUBSCRIPTION_URL) or DEFAULT_SUBSCRIPTION_URL)
        self.subscription_auto_sync = SubscriptionAutoSync(self, subscription_url, self.config.data_dir)
        self.subscription_auto_sync.synced.connect(self._subscription_sync_done)
        self.subscription_auto_sync.status.connect(self._subscription_auto_status)

        self.setWindowTitle("小林影视 · NAS")
        self.resize(1180, 780)
        self.setMinimumSize(960, 640)
        self.setStyleSheet(DARK_QSS)
        self._build_ui()
        self._connect()
        # Let the window enter the Qt event loop before doing any first-load
        # work.  NAS scanning and the initial home refresh are both deferred.
        QTimer.singleShot(0, self._show_continue)
        QTimer.singleShot(0, self.scan)
        QTimer.singleShot(0, self._start_subscription_hd_upgrade)
        QTimer.singleShot(12000, self._auto_sync_subscriptions)

    # ---------- UI ----------
    def _load_subscription_cache(self) -> None:
        try:
            data = json.loads(self.config.subscription_cache_path.read_text(encoding="utf-8"))
            items = data.get("items", []) if isinstance(data, dict) else []
            captured_at = self.config.subscription_cache_path.stat().st_mtime
            migrated = False
            self.subscription_items = []
            for item in items:
                if not isinstance(item, dict) or not item.get("title") or not item.get("updated_at"):
                    continue
                updated_at = str(item.get("updated_at", "")).strip()
                updated_epoch = item.get("updated_at_epoch")
                date_only = bool(item.get("updated_at_date_only", False))
                try:
                    updated_epoch = float(updated_epoch) if updated_epoch is not None else None
                except (TypeError, ValueError):
                    updated_epoch = None
                if updated_epoch is None:
                    updated_epoch, date_only = subscription_update_timestamp(updated_at, captured_at)
                    migrated = True
                self.subscription_items.append(
                    {
                        "title": str(item.get("title", "")).strip(),
                        "updated_at": updated_at,
                        "url": str(item.get("url", "")).strip(),
                        "poster": str(item.get("poster", "")).strip(),
                        "hd_poster": str(item.get("hd_poster", "")).strip(),
                        "background": str(item.get("background", "")).strip(),
                        "website_status": str(item.get("website_status", "")).strip(),
                        "latest_season": item.get("latest_season"),
                        "latest_episode": item.get("latest_episode"),
                        "season_final": bool(item.get("season_final", False)),
                        "updated_at_epoch": updated_epoch,
                        "updated_at_date_only": date_only,
                    }
                )
            purged = self._purge_stale_subscription_assets()
            if migrated or purged:
                self._save_subscription_cache()
        except (OSError, ValueError, TypeError):
            self.subscription_items = []
        self._rebuild_subscription_matches()

    def _save_subscription_cache(self) -> None:
        self.config.subscription_cache_path.write_text(
            json.dumps(
                {
                    "source": self.config.get("subscription_url", DEFAULT_SUBSCRIPTION_URL),
                    "items": self.subscription_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _purge_stale_subscription_assets(self) -> bool:
        """Delete only this app's cached artwork for expired subscriptions."""
        cache_roots = {
            (self.config.cache_dir / name).resolve()
            for name in ("posters", "backgrounds", "subscriptions")
        }
        changed = False
        for item in self.subscription_items:
            if self._subscription_item_is_recent(item):
                continue
            for key in ("poster", "hd_poster", "background"):
                raw = str(item.get(key) or "").strip()
                if not raw or raw.startswith(("http://", "https://")):
                    continue
                try:
                    path = Path(raw).resolve()
                    allowed = any(path.is_relative_to(root) for root in cache_roots)
                except (OSError, RuntimeError, ValueError):
                    allowed = False
                    path = None
                if not allowed or path is None:
                    continue
                if path.exists() and path.is_file():
                    try:
                        path.unlink()
                    except OSError:
                        continue
                if item.get(key):
                    item[key] = ""
                    changed = True
        return changed

    @staticmethod
    def _subscription_item_is_recent(item: dict[str, str]) -> bool:
        return subscription_poster_is_recent(
            str(item.get("updated_at", "")),
            item.get("updated_at_epoch"),
            bool(item.get("updated_at_date_only", False)),
        )

    def _rebuild_subscription_matches(self) -> None:
        self._subscription_item_ids = set()
        if not self.subscription_items:
            return
        for item in self.subscription_items:
            matched = self._subscription_local_match(str(item.get("title") or ""))
            if matched and matched[0] is not None:
                self._subscription_item_ids.add(int(matched[0]["id"]))

    def _set_subscription_background(self) -> None:
        candidates = [
            str(item.get("background") or item.get("hd_poster") or item.get("poster", "")).strip()
            for item in self.subscription_items
            if self._subscription_item_is_recent(item)
            and (item.get("background") or item.get("hd_poster") or item.get("poster"))
            and os.path.exists(str(item.get("background") or item.get("hd_poster") or item.get("poster")))
        ]
        self._home_background_path = random.SystemRandom().choice(candidates) if candidates else ""
        self._update_subscription_background()

    def _start_subscription_hd_upgrade(self) -> None:
        if not self.subscription_items or self._subscription_hd_worker is not None:
            return
        items = [dict(item) for item in self.subscription_items]
        worker = SubscriptionHighResWorker(
            items,
            self.config.cache_dir,
            str(self.config.get("tmdb_api_key", "") or ""),
        )
        worker.signals.done.connect(self._subscription_hd_done)
        self._subscription_hd_worker = worker
        self.pool.start(worker)

    def _subscription_hd_done(self, items: object) -> None:
        self._subscription_hd_worker = None
        if not isinstance(items, list):
            return
        by_title = {
            str(item.get("title") or "").strip(): {
                "hd_poster": str(item.get("hd_poster") or "").strip(),
                "background": str(item.get("background") or "").strip(),
            }
            for item in items
            if isinstance(item, dict) and item.get("title")
        }
        changed = False
        for item in self.subscription_items:
            artwork = by_title.get(str(item.get("title") or "").strip(), {})
            highres = artwork.get("hd_poster", "")
            background = artwork.get("background", "")
            if highres and item.get("hd_poster") != highres:
                item["hd_poster"] = highres
                changed = True
            if background and item.get("background") != background:
                item["background"] = background
                changed = True
        if not changed:
            return
        self.config.subscription_cache_path.write_text(
            json.dumps(
                {
                    "source": self.config.get("subscription_url", DEFAULT_SUBSCRIPTION_URL),
                    "items": self.subscription_items,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self._invalidate_home_cache(reset_recent_sort=False)
        self._set_subscription_background()
        if self.stack.currentIndex() == 0:
            self._show_continue()
        self.status_label.setText(f"订阅高清资源已更新：{len(by_title)} 项")

    def _update_subscription_background(self) -> None:
        background = getattr(self, "home_background", None)
        if background is None or not self._home_background_path or not os.path.exists(self._home_background_path):
            if background is not None:
                background.hide()
            return
        width = max(1, self.library_page.width())
        height = max(1, self.library_page.height())
        background.setGeometry(self.library_page.rect())
        background.setPixmap(self._cover_pixmap(self._home_background_path, width, height))
        background.show()
        background.lower()

    def _subscription_local_match(self, title: str):
        """Find local files for the exact subscribed work and season."""
        source = self._home_source_rows
        if source is None:
            source = {
                kind: list(self.store.list_items(kind))
                for kind in ("tv", "movie")
            }
        requested_season = _season_number(title)
        fallback = None
        for rows in source.values():
            for row in rows:
                files = list(self.store.list_files(int(row["id"])))
                # A library title can contain a provider spelling variant or a
                # stale season-bearing metadata title.  Prefer the actual
                # media path as an identity hint, then enforce the requested
                # season below; never bind from the stale metadata alone.
                candidates = [
                    str(row["title"] or ""),
                    str(row["original_title"] or "") if "original_title" in row.keys() else "",
                    str(row["path"] or ""),
                ]
                candidates.extend(str(file_row["path"] or "") for file_row in files)
                if not any(titles_match(candidate, title) for candidate in candidates if candidate):
                    continue
                if requested_season is None:
                    if str(row["kind"] or "") != "movie":
                        continue
                    season_files = [f for f in files if int(f["season"] or 0) == 0]
                else:
                    if str(row["kind"] or "") != "tv":
                        continue
                    season_files = [
                        f for f in files if int(f["season"] or 0) == requested_season
                    ]
                if season_files:
                    return row, season_files
                # Keep a same-title row so the UI can still report “还未下载”
                # when the item exists but has no files for this season.
                if not files:
                    fallback = (row, [])
        return fallback


    @staticmethod
    def _subscription_play_choice(files: list, requested_season: int | None):
        """Return (state, path, resume) from one exact season's files."""
        if not files:
            return "not_downloaded", "", False
        ordered = sorted(
            files,
            key=lambda f: (
                int(f["episode"] or 0) if f["episode"] is not None else 0,
                str(f["filename"] or ""),
            ),
        )
        if requested_season is None:
            # Movies have no next-episode transition; resume the last watched
            # file when available, otherwise open the only/first file.
            played = [f for f in ordered if f["last_played_at"] or f["progress"] or f["watched"]]
            current = max(played, key=lambda f: str(f["last_played_at"] or "")) if played else ordered[0]
            return "available", str(current["path"] or ""), bool(current["progress"] or current["watched"])

        played = [
            f for f in ordered
            if f["last_played_at"] or f["progress"] or f["watched"] or f["playback_state"] == "finished"
        ]
        if not played:
            return "available", str(ordered[0]["path"] or ""), False
        current = max(
            played,
            key=lambda f: (str(f["last_played_at"] or ""), int(f["episode"] or 0)),
        )
        duration = float(current["duration"] or 0)
        finished = bool(current["watched"] or current["playback_state"] == "finished")
        if duration > 0:
            finished = finished or float(current["progress"] or 0) >= duration * 0.95
        if finished:
            current_episode = int(current["episode"] or 0)
            next_file = next(
                (f for f in ordered if int(f["episode"] or 0) > current_episode),
                None,
            )
            if next_file is None:
                return "no_next", "", False
            return "available", str(next_file["path"] or ""), False
        return "available", str(current["path"] or ""), True

    def _subscription_entries(self) -> list[tuple]:
        """Build website-first rows; local rows only enrich actions/artwork."""
        source = self._home_source_rows or {"tv": [], "movie": []}
        result = []
        seen_titles = set()
        visible_items = [
            (index, item)
            for index, item in enumerate(self.subscription_items)
            if self._subscription_item_is_recent(item)
        ]
        visible_items.sort(
            key=lambda pair: (float(pair[1].get("updated_at_epoch") or 0), -pair[0]),
            reverse=True,
        )
        for _, item in visible_items:
            title = str(item.get("title") or "").strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            matched = self._subscription_local_match(title)
            matched_row, season_files = matched if matched else (None, [])
            item_id = int(matched_row["id"]) if matched_row is not None else None
            recent_update = self._subscription_item_is_recent(item)
            local_poster = (
                str(matched_row["poster"] or "")
                if matched_row is not None and recent_update
                else ""
            )
            synced_poster = str(item.get("hd_poster") or item.get("poster", "")).strip() if recent_update else ""
            poster = synced_poster if synced_poster and os.path.exists(synced_poster) else local_poster
            requested_season = _season_number(title)
            local_state, play_path, play_resume = self._subscription_play_choice(
                season_files, requested_season
            )
            has_new_update = subscription_has_undownloaded_update(
                item, season_files, requested_season
            )
            result.append(
                (
                    item_id,
                    title,
                    poster,
                    f"更新：{item['updated_at']}",
                    str(item.get("url", "")),
                    str(item.get("website_status") or ""),
                    play_path,
                    play_resume,
                    local_state,
                    has_new_update,
                )
            )
        return result

    def sync_subscriptions(self) -> None:
        url = str(self.config.get("subscription_url", DEFAULT_SUBSCRIPTION_URL) or DEFAULT_SUBSCRIPTION_URL)
        self.subscription_auto_sync.stop()
        dialog = SubscriptionSyncDialog(
            self,
            url,
            self.config.data_dir,
            profile=self.subscription_auto_sync.profile,
        )
        dialog.synced.connect(self._subscription_sync_done)
        try:
            dialog.exec()
        finally:
            if not self._closing:
                QTimer.singleShot(1000, self._auto_sync_subscriptions)

    def open_subscription_page(self, url: str = "") -> None:
        """Show a dyjie page in MoviePoster and reuse the authenticated profile."""
        if self._closing:
            return
        sync_url = str(
            self.config.get("subscription_url", DEFAULT_SUBSCRIPTION_URL)
            or DEFAULT_SUBSCRIPTION_URL
        )
        self.subscription_auto_sync.stop()
        dialog = SubscriptionSyncDialog(
            self,
            sync_url,
            self.config.data_dir,
            profile=self.subscription_auto_sync.profile,
            initial_url=str(url or sync_url),
        )
        dialog.synced.connect(self._subscription_sync_done)
        try:
            dialog.exec()
        finally:
            if not self._closing:
                QTimer.singleShot(1000, self._auto_sync_subscriptions)

    def _auto_sync_subscriptions(self) -> None:
        if not self._closing:
            self.subscription_auto_sync.sync()

    def _subscription_auto_status(self, message: str) -> None:
        if message.startswith("正在") or "失败" in message or "跳过" in message:
            self.status_label.setText(message)

    def _subscription_sync_done(self, items: object) -> None:
        if not isinstance(items, list):
            return
        captured_at = time.time()
        old_hd = {
            str(item.get("title") or "").strip(): str(item.get("hd_poster") or "").strip()
            for item in self.subscription_items
        }
        old_background = {
            str(item.get("title") or "").strip(): str(item.get("background") or "").strip()
            for item in self.subscription_items
        }
        self.subscription_items = []
        for item in items:
            if not isinstance(item, dict) or not item.get("title") or not item.get("updated_at"):
                continue
            updated = dict(item)
            updated_epoch = updated.get("updated_at_epoch")
            date_only = bool(updated.get("updated_at_date_only", False))
            try:
                updated_epoch = float(updated_epoch) if updated_epoch is not None else None
            except (TypeError, ValueError):
                updated_epoch = None
            if updated_epoch is None:
                updated_epoch, date_only = subscription_update_timestamp(
                    str(updated.get("updated_at") or ""), captured_at
                )
            updated["updated_at_epoch"] = updated_epoch
            updated["updated_at_date_only"] = date_only
            if not updated.get("hd_poster") and old_hd.get(str(updated["title"]).strip()):
                updated["hd_poster"] = old_hd[str(updated["title"]).strip()]
            if not updated.get("background") and old_background.get(str(updated["title"]).strip()):
                updated["background"] = old_background[str(updated["title"]).strip()]
            self.subscription_items.append(updated)
        self._purge_stale_subscription_assets()
        self._save_subscription_cache()
        self._rebuild_subscription_matches()
        self._invalidate_home_cache(reset_recent_sort=True)
        self._set_subscription_background()
        if self.stack.currentIndex() == 0:
            self._show_continue()
        self._start_subscription_hd_upgrade()
        self.status_label.setText(
            f"订阅已同步：{len(self.subscription_items)} 项，匹配媒体 {len(self._subscription_item_ids)} 部"
        )

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
        logo = ClickableLogo()
        logo.setObjectName("appLogo")
        logo.setFixedSize(30, 30)
        logo.setAlignment(Qt.AlignCenter)
        logo.setToolTip("小林影视")
        logo.clicked.connect(self._show_continue)
        if self.logo_path.exists():
            pixmap = QPixmap(str(self.logo_path))
            logo.setPixmap(pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.app_logo = logo
        left_layout.addWidget(logo)
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
        self.section_title = MediaCategoryTitle("我的媒体")
        self.section_title.setObjectName("topMediaMenu")
        self.section_title.setStyleSheet(
            "QLabel#topMediaMenu { color: #f2f4f7; font-size: 15px; font-weight: 600; "
            "padding: 3px 7px; border-radius: 7px; } "
            "QLabel#topMediaMenu:hover { background: rgba(255,255,255,22); color: #ffffff; }"
        )
        self.section_title.category_clicked.connect(self._handle_media_category)
        nav_layout.addWidget(self.section_title, 0, Qt.AlignVCenter)
        # 首页内容承担频道展示；顶部只保留媒体菜单，隐藏旧的按钮式导航。
        self.home_btn.hide()
        self.favorite_btn.hide()
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
        self.search_suggestion_model = QStandardItemModel(self.search_completer)
        self.search_completer.setModel(self.search_suggestion_model)
        self.search.setCompleter(self.search_completer)
        right_layout.addWidget(self.search)
        self.status_label = QLabel("就绪")
        self.status_label.setStyleSheet("color: #9aa4b2;")
        self.status_label.setFont(role_font("meta"))
        self.status_label.setMaximumWidth(320)
        self.status_label.setToolTip("当前媒体库统计；扫描和元数据任务仍在后台运行")
        right_layout.addWidget(self.status_label)
        self.refresh_btn = QPushButton("重新扫描")
        self.settings_btn = QPushButton("设置")
        management = QMenu(self)
        management.addAction("重新扫描", self.scan)
        management.addAction("同步我的订阅", self.sync_subscriptions)
        management.addAction("整理模式", lambda: self._nav_changed(3))
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
        self.library_page.setStyleSheet("background: transparent;")
        self.home_background = QLabel(self.library_page)
        self.home_background.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.home_background.setStyleSheet("background: transparent;")
        opacity = QGraphicsOpacityEffect(self.home_background)
        opacity.setOpacity(0.22)
        self.home_background.setGraphicsEffect(opacity)
        self.home_background.lower()
        self._home_background_path = ""
        library_layout = QVBoxLayout(self.library_page)
        library_layout.setContentsMargins(32, 20, 32, 30)
        library_layout.setSpacing(18)

        self.section_subtitle = QLabel("从上次停下的地方继续播放")
        self.section_subtitle.setObjectName("sectionSubtitle")
        library_layout.addWidget(self.section_subtitle)

        self.home_panel = QWidget()
        self.home_panel.setStyleSheet("background: transparent;")
        self.home_layout = QVBoxLayout(self.home_panel)
        self.home_layout.setContentsMargins(0, 4, 0, 0)
        # 首页不再展示两张媒体库入口海报，分类入口改为标题悬停菜单。
        self.home_layout.setSpacing(0)
        self.home_rows_widget = QWidget()
        self.home_rows_widget.setStyleSheet("background: transparent;")
        self.home_rows = QVBoxLayout(self.home_rows_widget)
        self.home_rows.setContentsMargins(0, 0, 0, 0)
        self.home_rows.setSpacing(20)
        self.home_rows_scroll = QScrollArea()
        self.home_rows_scroll.setWidgetResizable(True)
        self.home_rows_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.home_rows_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._install_cinema_scrollbar(self.home_rows_scroll)
        self.home_rows_scroll.viewport().setStyleSheet("background: transparent;")
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
        # Kept as a compatibility hook for older callers; the two entry cards
        # were intentionally replaced by the top navigation category menu.
        return QVBoxLayout()

    def _handle_media_category(self, category: str) -> None:
        """保留已有电视剧/电影入口行为；其他分类先作为菜单展示项。"""
        if category == "电视剧":
            self._show_kind("tv")
        elif category == "电影":
            self._show_kind("movie")

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
            self._poster_pixmap_cache.move_to_end(key)
            return cached
        source = QPixmap(path)
        scaled = source.scaled(width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        left = max(0, (scaled.width() - width) // 2)
        top = max(0, (scaled.height() - height) // 2)
        result = scaled.copy(left, top, width, height)
        self._poster_pixmap_cache[key] = result
        self._poster_pixmap_cache.move_to_end(key)
        while len(self._poster_pixmap_cache) > self._poster_pixmap_cache_limit:
            self._poster_pixmap_cache.popitem(last=False)
        return result

    def _make_media_row(self, title: str, entries: list[tuple], card_type: str = "poster") -> QWidget:
        section = QWidget()
        section.setStyleSheet("background: transparent;")
        outer = QVBoxLayout(section)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(12)
        heading = QLabel(title + "  ›")
        heading.setObjectName("sectionTitle")
        heading.setFont(role_font("title"))
        accent_titles = {"我的订阅", "最近添加的电视剧", "最近添加的电影", "高评分"}
        if title in accent_titles:
            heading_row = QWidget()
            heading_layout = QHBoxLayout(heading_row)
            heading_layout.setContentsMargins(0, 0, 0, 0)
            heading_layout.setSpacing(9)
            accent = QFrame()
            accent.setObjectName("sectionAccent")
            accent.setFixedWidth(4)
            accent.setFixedHeight(max(1, heading.sizeHint().height()))
            accent.setStyleSheet("QFrame#sectionAccent { background: #f4c542; border-radius: 2px; }")
            heading_layout.addWidget(accent, 0, Qt.AlignVCenter)
            heading_layout.addWidget(heading)
            outer.addWidget(heading_row)
        else:
            outer.addWidget(heading)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        is_continue = card_type == "continue"
        is_subscription = card_type == "subscription"
        row_height = 280 if is_continue else (410 if is_subscription else 320)
        scroll.setFixedHeight(row_height)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        scroll.viewport().setStyleSheet("background: transparent;")
        content = QWidget()
        content.setStyleSheet("background: transparent;")
        line = QHBoxLayout(content)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(18)
        for entry in entries:
            item_id, name, poster, subtitle = entry[:4]
            if is_continue:
                ratio = float(entry[4]) if len(entry) > 4 else 0.0
                play_path = str(entry[5]) if len(entry) > 5 else ""
                line.addWidget(ContinueWatchingCard(self, item_id, name, poster, subtitle, ratio, play_path))
            elif is_subscription:
                url = str(entry[4]) if len(entry) > 4 else ""
                website_status = str(entry[5]) if len(entry) > 5 else ""
                play_path = str(entry[6]) if len(entry) > 6 else ""
                play_resume = bool(entry[7]) if len(entry) > 7 else False
                local_state = str(entry[8]) if len(entry) > 8 else "not_downloaded"
                has_new_update = bool(entry[9]) if len(entry) > 9 else False
                line.addWidget(
                    SubscriptionCard(
                        self,
                        item_id,
                        name,
                        poster,
                        subtitle,
                        url,
                        website_status,
                        play_path,
                        play_resume,
                        local_state,
                        has_new_update,
                    )
                )
            else:
                line.addWidget(PosterCard(self, item_id, name, poster, subtitle))
        line.addStretch(1)
        card_width = 368 if is_continue else (222 if is_subscription else 178)
        content.setFixedWidth(max(card_width, len(entries) * card_width + 20))
        content.setFixedHeight(390 if is_subscription else (280 if is_continue else 274))
        scroll.setWidget(content)
        outer.addWidget(scroll)
        # Keep the section from being compressed by the parent home layout.  In
        # particular, ContinueWatchingCard contains title/subtitle/progress
        # below its 16:9 artwork and must retain the full row height.
        section.setMinimumHeight(row_height + 38)
        return section

    def _invalidate_home_cache(self, reset_recent_sort: bool = False):
        self._home_media_cache = None
        self._home_source_rows = None
        if reset_recent_sort:
            self._recent_sort_keys = None
            self._recent_sort_generation += 1

    def _build_home_cache(self, sort_keys=None):
        source = self._home_source_rows or {"tv": [], "movie": []}

        def rows_for(kind: str):
            rows = list(source.get(kind, []))
            if sort_keys is None:
                rows.sort(key=lambda r: (r["updated_at"] or ""), reverse=True)
            else:
                rows.sort(
                    key=lambda r: (
                        sort_keys.get(int(r["id"]), (0, 0.0))[0],
                        sort_keys.get(int(r["id"]), (0, 0.0))[1],
                        r["updated_at"] or "",
                    ),
                    reverse=True,
                )
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
        return {
            "subscriptions": self._subscription_entries(),
            "tv": entries(tv_rows, "电视剧"),
            "movie": entries(movie_rows, "电影"),
            "rated": [
                (r["id"], r["title"], r["poster"] or "", f"豆瓣 {float(r['rating']):.1f}")
                for r in rated[:18]
            ],
        }

    def _start_recent_sort(self):
        old_worker = self._recent_worker
        if old_worker and old_worker.isRunning():
            old_worker.requestInterruption()
            if not old_worker.wait(3000):
                # Never replace a live worker reference; its result remains
                # valid and will be generation-filtered when it completes.
                return
        self._recent_worker = None
        items = {}
        for rows in (self._home_source_rows or {}).values():
            for row in rows:
                paths = []
                try:
                    paths = [str(f["path"] or "") for f in self.store.list_files(row["id"]) if f["path"]]
                except Exception:
                    pass
                # "最近添加" follows the media directory's last modified
                # time, the same value users see in Windows Explorer.  File
                # timestamps remain a fallback for unavailable NAS folders.
                items[int(row["id"])] = {
                    "root": str(row["path"] or ""),
                    "files": paths,
                }
        self._recent_sort_generation += 1
        worker = RecentFilesWorker(self._recent_sort_generation, items)
        worker.finished_times.connect(self._recent_sort_done)
        worker.error.connect(self._recent_sort_error)
        self._recent_worker = worker
        worker.start()

    def _recent_sort_done(self, generation: int, sort_keys: dict):
        if generation != self._recent_sort_generation:
            return
        # Metadata callbacks can invalidate the display cache while this
        # worker is reading NAS timestamps. The paths did not change, so the
        # measured ordering is still valid; rebuild the source rows before
        # applying it instead of throwing the result away.
        if self._home_source_rows is None:
            self._refresh_library_art()
            self._home_source_rows = {
                kind: [self.store.get_item(i) for i in self.items.get(kind, [])]
                for kind in ("tv", "movie")
            }
            self._home_source_rows = {
                kind: [row for row in rows if row]
                for kind, rows in self._home_source_rows.items()
            }
        self._recent_sort_keys = sort_keys
        self._home_media_cache = self._build_home_cache(sort_keys)
        if self.stack.currentIndex() == 0 and self.current_kind == "continue":
            self._populate_home()

    def _recent_sort_error(self, generation: int, message: str):
        # File-time ordering is an enhancement; database ordering remains valid.
        if generation == self._recent_sort_generation:
            self._recent_worker = None

    def _populate_home(self):
        while self.home_rows.count():
            item = self.home_rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self._home_media_cache is None:
            # 首次进入才读取数据库、解析文件时间和刷新库入口图片。
            self._refresh_library_art()
            self._home_source_rows = {
                kind: [self.store.get_item(i) for i in self.items.get(kind, [])]
                for kind in ("tv", "movie")
            }
            self._home_source_rows = {
                kind: [row for row in rows if row]
                for kind, rows in self._home_source_rows.items()
            }
            # Build immediately from the local cache when available. The
            # first-ever load is refined by RecentFilesWorker without blocking
            # the first paint; later metadata refreshes reuse those measured
            # directory times and never revert to title/ID order.
            self._home_media_cache = self._build_home_cache(self._recent_sort_keys)
            if self._recent_sort_keys is None and not (
                self._recent_worker and self._recent_worker.isRunning()
            ):
                self._start_recent_sort()

        data = self._home_media_cache
        if data["subscriptions"]:
            self.home_rows.addWidget(
                self._make_media_row("我的订阅", data["subscriptions"], card_type="subscription")
            )
        else:
            message = (
                "尚未同步订阅。请打开左上角菜单，选择“同步我的订阅”并登录 dyjie.net。"
                if not self.subscription_items
                else "订阅页有更新，但当前媒体库没有匹配条目。"
            )
            empty = QLabel(f"我的订阅：{message}")
            empty.setStyleSheet("color: #9aa4b2; padding: 18px 0;")
            self.home_rows.addWidget(empty)
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
        """Refresh home artwork without relying on the removed library cards."""
        # The home entry cards are no longer part of the page; their artwork
        # refresh used to abort the whole home population after the cards were
        # removed.  Subscription background selection is handled separately.
        return

    def _connect(self):
        self.nav.currentRowChanged.connect(self._nav_changed)
        self.search.textChanged.connect(self._update_search_suggestions)
        self.search.textChanged.connect(self._queue_search)
        self.refresh_btn.clicked.connect(self.scan)
        self.settings_btn.clicked.connect(lambda: self.stack.setCurrentIndex(3))
        self.grid.activated_item.connect(self._open_detail)
        # DetailPage no longer owns a separate back button; navigation is kept
        # in the shared top bar so every page has the same interaction model.

    # ---------- 扫描 ----------
    def scan(self):
        if self._closing:
            return
        if getattr(self, "worker", None) and self.worker.isRunning():
            self.status_label.setText("扫描正在进行中，请勿重复启动")
            return
        tv_root = self.config.get("tv_root")
        movie_root = self.config.get("movie_root")
        self.refresh_btn.setEnabled(False)
        self.status_label.setText("正在后台扫描 NAS 媒体库，界面仍可浏览…")
        self.worker = ScanWorker(tv_root, movie_root)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.finished_scan.connect(self._scan_done)
        self.worker.cancelled.connect(self._scan_cancelled)
        self.worker.error.connect(lambda e: self._scan_error(e))
        self.worker.start()

    def _scan_error(self, msg: str):
        self.refresh_btn.setEnabled(True)
        self.status_label.setText(f"扫描失败：{msg}")

    def _scan_cancelled(self):
        self.refresh_btn.setEnabled(True)
        if not self._closing:
            self.status_label.setText("扫描已取消，保留原有媒体记录")

    def _scan_done(self):
        worker = self.worker
        tv = list(getattr(worker, "tv_items", ()))
        movies = list(getattr(worker, "movie_items", ()))
        tv_errors = list(getattr(worker, "tv_errors", ()))
        movie_errors = list(getattr(worker, "movie_errors", ()))
        self.refresh_btn.setEnabled(True)
        self._invalidate_home_cache(reset_recent_sort=True)
        self.tv_items = tv
        self.movie_items = movies
        was_detail = self.stack.currentIndex() == 1
        # 入库
        for kind, items, errors in (("tv", tv, tv_errors), ("movie", movies, movie_errors)):
            old_ids = list(self.items.get(kind, ()))
            scanned_ids = []
            for it in items:
                item_id = self.store.upsert_item(kind, it.title, it.path)
                if it.scan_complete and not errors:
                    self.store.replace_files(
                        item_id,
                        [f.path for f in it.files],
                        [f.name for f in it.files],
                        [f.season for f in it.files],
                        [f.episode for f in it.files],
                    )
                scanned_ids.append(item_id)
            self.items[kind] = list(dict.fromkeys(old_ids + scanned_ids)) if errors else scanned_ids
        self._rebuild_subscription_matches()
        issue_count = len(tv_errors) + len(movie_errors)
        suffix = f"；读取问题 {issue_count} 项，旧记录已保留" if issue_count else ""
        self.status_label.setText(f"扫描完成：电视剧 {len(tv)} 部，电影 {len(movies)} 部{suffix}，正在抓取豆瓣信息…")
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
        self.continue_heading.setVisible(False)
        self.section_title.set_menu_enabled(True)
        self.section_title.setText("我的媒体")
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

    def _queue_search(self, _text: str = ""):
        if not self._closing:
            self._search_timer.start()

    def _update_search_suggestions(self, text: str):
        suggestions = self.store.search_suggestions(text)
        model = self.search_suggestion_model
        model.clear()
        for value in suggestions:
            model.appendRow(QStandardItem(value))

    # ---------- 导航 ----------
    def _set_detail_navigation(self, active: bool):
        """Keep the shared top bar consistent across library and detail views."""
        self.detail_back_btn.setVisible(active)
        self.section_title.set_menu_enabled(True)
        self.section_title.setText("我的媒体")
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
        self.section_title.set_menu_enabled(True)
        if not self._home_background_path:
            self._set_subscription_background()
        else:
            self._update_subscription_background()
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
        self._search_timer.stop()

    def _show_kind(self, kind: str):
        self.current_kind = kind
        self._set_detail_navigation(False)
        self.stack.setCurrentIndex(0)
        self.home_panel.setVisible(False)
        self.grid.setVisible(True)
        self.home_background.hide()
        self.section_title.set_menu_enabled(True)
        self.continue_heading.setVisible(False)
        label = "电视剧" if kind == "tv" else "电影"
        self.section_title.setText("我的媒体")
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
        self.section_title.set_menu_enabled(True)
        self.section_title.setText("我的媒体")
        self.detail.load(item_id)
        self._set_detail_navigation(True)
        self.stack.setCurrentIndex(1)

    def _show_playback_message(self, message: str) -> None:
        QMessageBox.information(self, "播放提示", message)

    @staticmethod
    def _potplayer_window_handles(process_id: int | None = None) -> list[int]:
        """Find PotPlayer top-level windows, preferring the launched process."""
        if os.name != "nt":
            return []
        user32 = ctypes.windll.user32
        handles: list[tuple[int, int]] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def callback(hwnd, _lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            name = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(hwnd, name, len(name))
            if "potplayer" not in name.value.casefold():
                return True
            owner = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            handles.append((int(hwnd), int(owner.value)))
            return True

        user32.EnumWindows(callback, 0)
        preferred = [hwnd for hwnd, owner in handles if process_id and owner == process_id]
        return preferred or [hwnd for hwnd, _owner in handles]

    @classmethod
    def _query_potplayer_position(cls, session: dict) -> tuple[float | None, float | None]:
        """Read real PotPlayer position/duration through its WM_USER API."""
        handles = cls._potplayer_window_handles(
            getattr(session.get("process"), "pid", None)
        )
        if not handles or os.name != "nt":
            return None, None
        user32 = ctypes.windll.user32
        user32.SendMessageTimeoutW.argtypes = [
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
            wintypes.UINT,
            wintypes.UINT,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        user32.SendMessageTimeoutW.restype = wintypes.LPARAM

        def command(hwnd: int, code: int) -> int | None:
            result = ctypes.c_size_t()
            ok = user32.SendMessageTimeoutW(
                hwnd,
                0x0400,  # WM_USER
                code,
                0,
                0x0002,  # SMTO_ABORTIFHUNG
                200,
                ctypes.byref(result),
            )
            return int(result.value) if ok else None

        for hwnd in handles:
            raw_position = command(hwnd, 0x5004)
            raw_duration = command(hwnd, 0x5002)
            if raw_position is None or raw_duration is None or raw_duration <= 0:
                continue
            known_duration = float(session.get("duration") or 0)
            scales = (1.0, 0.001, 0.000001, 0.01)
            if known_duration > 0:
                scale = min(scales, key=lambda value: abs(raw_duration * value - known_duration))
            else:
                scale = 0.001 if raw_duration > 100000 else 1.0
            duration = max(0.0, raw_duration * scale)
            position = max(0.0, raw_position * scale)
            if duration > 0:
                position = min(position, duration)
            session["potplayer_hwnd"] = hwnd
            return position, duration
        return None, None

    @staticmethod
    def _seek_argument(seconds: float) -> str:
        total = max(0, int(seconds))
        hours, remainder = divmod(total, 3600)
        minutes, secs = divmod(remainder, 60)
        return f"/seek={hours:02d}:{minutes:02d}:{secs:02d}"

    def play(self, path: str, resume: bool = False):
        pot = self.config.get("potplayer")
        if not pot or not os.path.exists(pot):
            QMessageBox.warning(self, "播放器缺失", "找不到 PotPlayer，请在设置里指定播放器路径。")
            return False
        if not path or not os.path.exists(path):
            QMessageBox.warning(self, "路径不可访问", "NAS 路径暂时不可访问，无法判断本地文件是否可播放。")
            return False
        file_row = self.store.get_file(path)
        previous = float(file_row["progress"] or 0) if file_row else 0.0
        duration = float(file_row["duration"] or 0) if file_row else 0.0
        if duration <= 0:
            duration = self._probe_duration(path)
        cmd = [pot]
        if resume and previous > 0:
            cmd.append(self._seek_argument(previous))
        cmd.append(path)
        try:
            process = subprocess.Popen(cmd)
            # Never invent a positive position. The timer will replace this
            # value with PotPlayer's actual WM_USER position when available.
            self.store.update_play_state(path, "in_progress", previous, duration or None)
            self.store.update_last_played(path)
            self._play_sessions.append({
                "process": process,
                "path": path,
                "base": previous,
                "duration": duration,
            })
            # Hand focus to PotPlayer and keep the library window out of the
            # way.  Only minimize after Popen succeeds, so failed playback
            # attempts leave the diagnostic dialog visible.
            self.showMinimized()
            return True
        except Exception as e:
            QMessageBox.warning(self, "播放失败", str(e))
            return False

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
            duration = float(session.get("duration") or 0)
            live_position, live_duration = self._query_potplayer_position(session)
            if live_duration and live_duration > 0:
                duration = live_duration
                session["duration"] = live_duration
            position = float(live_position) if live_position is not None else float(session.get("base") or 0)
            if duration > 0:
                position = min(position, duration)
            if live_position is not None:
                session["base"] = position
            finished = duration > 0 and position >= duration * 0.95 and live_position is not None
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_subscription_background()

    def closeEvent(self, event):
        # Do not destroy the window while either managed QThread is still
        # running.  Scan code may be inside a NAS call and cannot be force-
        # terminated safely, so close is deferred and polled instead.
        self._closing = True
        if self.refresh_btn:
            self.refresh_btn.setEnabled(False)
        # Capture one last real PotPlayer position before stopping the timer.
        # This keeps a pause/exit of MoviePoster from discarding the latest
        # sampled position; it does not invent progress when WM_USER cannot
        # read a live player window.
        if self._play_sessions:
            self._poll_play_sessions()
        if self._play_timer.isActive():
            self._play_timer.stop()
        if getattr(self, "subscription_auto_sync", None):
            self.subscription_auto_sync.stop()
        scan_running = bool(getattr(self, "worker", None) and self.worker.isRunning())
        recent_running = bool(self._recent_worker and self._recent_worker.isRunning())
        if scan_running:
            self.worker.requestInterruption()
        if recent_running:
            self._recent_worker.requestInterruption()
        if scan_running or recent_running:
            event.ignore()
            if not self._close_poll_scheduled:
                self._close_poll_scheduled = True
                QTimer.singleShot(100, self._poll_close)
            return
        self.pool.clear()
        self.pool.waitForDone(3000)
        super().closeEvent(event)

    def _poll_close(self):
        self._close_poll_scheduled = False
        scan_running = bool(getattr(self, "worker", None) and self.worker.isRunning())
        recent_running = bool(self._recent_worker and self._recent_worker.isRunning())
        if scan_running or recent_running:
            self._close_poll_scheduled = True
            QTimer.singleShot(100, self._poll_close)
            return
        self.close()


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
        preview_width, preview_height = _iphone_duo_poster_size(120)
        preview_radius = _iphone_duo_corner_radius(preview_width, preview_height)
        self.preview_poster = QLabel("暂无海报")
        self.preview_poster.setFixedSize(preview_width, preview_height)
        self.preview_poster.setAlignment(Qt.AlignCenter)
        self.preview_poster.setStyleSheet(
            f"background: #232933; border-radius: {preview_radius}px; color: #9aa4b2;"
        )
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
            width, height = _iphone_duo_poster_size(120)
            radius = _iphone_duo_corner_radius(width, height)
            pix = QPixmap(self._poster_path).scaled(
                width, height, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            self.preview_poster.setPixmap(_rounded_pixmap(pix, width, height, radius))
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
        poster_width, poster_height = _iphone_duo_poster_size(220)
        poster_radius = _iphone_duo_corner_radius(poster_width, poster_height)
        self.poster.setFixedSize(poster_width, poster_height)
        self.poster.setAlignment(Qt.AlignCenter)
        # V8：海报是独立前景层，不参与 backdrop 的模糊和渐变遮罩。
        self.poster.setAttribute(Qt.WA_TranslucentBackground)
        self.poster.setStyleSheet(
            "background: #232933; border: 1px solid rgba(255,255,255,80); "
            f"border-radius: {poster_radius}px; color: #4a5568;"
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
        self.loading_label.setText("正在加载…")
        self._loading_timer.start(5000)
        try:
            self._load_impl(item_id)
        except Exception as exc:
            self.loading_label.setText(f"部分信息加载失败，已保留可用内容：{exc}")
            self._loading_timer.stop()
            return
        self._loading_timer.stop()
        self._finish_loading()

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
            width, height = _iphone_duo_poster_size(220)
            radius = _iphone_duo_corner_radius(width, height)
            pm = self.win._cover_pixmap(poster, width, height)
            self.poster.setPixmap(_rounded_pixmap(pm, width, height, radius))
            self.poster.setFixedSize(width, height)
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
        self.delay = QDoubleSpinBox()
        self.delay.setRange(0, 3)
        self.delay.setDecimals(1)
        self.delay.setSingleStep(0.1)
        self.delay.setValue(float(win.config.get("request_delay", 0.4)))
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
        old_tv_root = str(cfg.get("tv_root", ""))
        old_movie_root = str(cfg.get("movie_root", ""))
        new_tv_root = self.tv_root.text().strip()
        new_movie_root = self.movie_root.text().strip()
        path_changed = old_tv_root != new_tv_root or old_movie_root != new_movie_root
        cfg.values.update({
            "tv_root": new_tv_root,
            "movie_root": new_movie_root,
            "potplayer": self.potplayer.text().strip(),
            "douban_enabled": self.douban.isChecked(),
            "request_delay": self.delay.value(),
        })
        cfg.save()
        self.win.client = DoubanClient(cfg.cache_dir, delay=float(self.delay.value()))
        if path_changed:
            self.win.scan()
        else:
            self.win.status_label.setText("设置已保存，未重新扫描媒体库")
