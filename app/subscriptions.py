"""Parse the authenticated dyjie subscription page.

The site exposes the user's subscription dashboard as HTML rather than as a
machine-readable feed.  MoviePoster therefore keeps the web session in its
own QtWebEngine profile and only stores the parsed, non-sensitive update list.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from html.parser import HTMLParser
import re
import unicodedata


DEFAULT_SUBSCRIPTION_URL = "https://dyjie.net/user/rss/"


class SubscriptionPageError(ValueError):
    """The page did not contain a usable recent-updates table."""


class SubscriptionLoginRequired(SubscriptionPageError):
    """The page is the login form instead of the authenticated dashboard."""


@dataclass(frozen=True)
class SubscriptionItem:
    title: str
    updated_at: str
    url: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class _Cell:
    def __init__(self) -> None:
        self.text: list[str] = []
        self.href = ""

    def value(self) -> str:
        return " ".join("".join(self.text).split())


class _TableParser(HTMLParser):
    """Small table parser that keeps the first link in each cell."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[_Cell]]] = []
        self._table: list[list[_Cell]] | None = None
        self._row: list[_Cell] | None = None
        self._cell: _Cell | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = _Cell()
            self._row.append(self._cell)
        elif tag == "a" and self._cell is not None and not self._cell.href:
            self._cell.href = dict(attrs).get("href", "") or ""

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.text.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"}:
            self._cell = None
        elif tag == "tr" and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def _compact_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = re.sub(r"第[0-9一二三四五六七八九十百]+季", "", value)
    value = re.sub(r"s\d{1,2}$", "", value, flags=re.IGNORECASE)
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)


def titles_match(local_title: str, subscription_title: str) -> bool:
    """Match the site's season-bearing title to a local media title safely."""

    local = _compact_title(local_title)
    subscribed = _compact_title(subscription_title)
    if not local or not subscribed:
        return False
    if local == subscribed:
        return True
    shorter = min(len(local), len(subscribed))
    longer = max(len(local), len(subscribed))
    return shorter >= 4 and shorter / longer >= 0.6 and (local in subscribed or subscribed in local)


def parse_recent_updates(html: str) -> list[SubscriptionItem]:
    """Extract the site's ``最近更新的影视`` table from an authenticated page."""

    if not html or re.search(r"用户登录|input_password|name=[\"']password[\"']", html, re.I):
        raise SubscriptionLoginRequired("请先在订阅窗口登录 dyjie.net")

    parser = _TableParser()
    parser.feed(html)
    items: list[SubscriptionItem] = []
    seen: set[str] = set()
    for table in parser.tables:
        header_index = None
        name_index = None
        updated_index = None
        for index, row in enumerate(table):
            values = [cell.value() for cell in row]
            for col, value in enumerate(values):
                if "名称" in value:
                    name_index = col
                if "更新时间" in value or value == "更新时间":
                    updated_index = col
            if name_index is not None and updated_index is not None:
                header_index = index
                break
        if header_index is None or name_index is None or updated_index is None:
            continue
        for row in table[header_index + 1 :]:
            values = [cell.value() for cell in row]
            if max(name_index, updated_index) >= len(values):
                continue
            title = values[name_index].strip()
            updated_at = values[updated_index].strip()
            if not title or title in {"暂无", "暂无数据"} or not updated_at:
                continue
            key = _compact_title(title)
            if not key or key in seen:
                continue
            seen.add(key)
            href = next((cell.href for cell in row if cell.href), "")
            items.append(SubscriptionItem(title=title, updated_at=updated_at, url=href))
    if not items:
        raise SubscriptionPageError("订阅页中没有找到最近更新的影视")
    return items
