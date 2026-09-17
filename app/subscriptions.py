"""Parse the authenticated dyjie.net subscription update table."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from html.parser import HTMLParser
import re
import time
import unicodedata
from urllib.parse import urljoin


DEFAULT_SUBSCRIPTION_URL = "https://dyjie.net/user/rss/"
SUBSCRIPTION_MAX_POSTER_AGE_DAYS = 45


class SubscriptionPageError(ValueError):
    """Raised when the page is not a usable authenticated update table."""


class SubscriptionLoginRequired(SubscriptionPageError):
    """Raised when dyjie.net returned its login page."""


@dataclass(frozen=True)
class SubscriptionItem:
    title: str
    updated_at: str
    url: str = ""
    poster: str = ""
    updated_at_epoch: float | None = None
    updated_at_date_only: bool = False

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "updated_at": self.updated_at,
            "url": self.url,
            "poster": self.poster,
            "updated_at_epoch": self.updated_at_epoch,
            "updated_at_date_only": self.updated_at_date_only,
        }


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[tuple[str, str]]]] = []
        self._table: list[list[tuple[str, str]]] | None = None
        self._row: list[tuple[str, str]] | None = None
        self._cell: list[str] | None = None
        self._href = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
            self._href = ""
        elif tag == "a" and self._cell is not None:
            self._href = dict(attrs).get("href", "") or ""

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self._row is not None and self._cell is not None:
            text = " ".join("".join(self._cell).split())
            self._row.append((text, self._href.strip()))
            self._cell = None
            self._href = ""
        elif tag == "tr" and self._table is not None and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


class _PosterParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.candidates: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() == "meta":
            marker = (values.get("property") or values.get("name") or "").casefold()
            if marker in {"og:image", "twitter:image", "image_src"} and values.get("content"):
                self.candidates.append(values["content"])
        elif tag.lower() == "img":
            for key in ("data-original", "data-src", "src"):
                if values.get(key):
                    self.candidates.append(values[key])
                    break


class _VisibleTextParser(HTMLParser):
    """Collect readable detail-page text while ignoring script/style bodies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"}:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "template", "noscript"} and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _cn_number(token: str) -> int | None:
    token = unicodedata.normalize("NFKC", token or "").strip()
    if token.isdigit():
        return int(token)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100}
    if token in digits:
        return digits[token]
    if len(token) == 2 and token[0] == "十" and token[1] in digits:
        return 10 + digits[token[1]]
    if len(token) == 2 and token[1] == "十" and token[0] in digits:
        return digits[token[0]] * 10
    return None


def parse_detail_update_status(html: str, title: str) -> dict[str, object]:
    """Extract only explicit season/episode or finale markers from a detail page.

    The detail page is authoritative for this field.  Missing or ambiguous
    markers intentionally return an empty status instead of inferring a finale
    from local files or from the absence of a new release.
    """
    parser = _VisibleTextParser()
    parser.feed(html or "")
    text = " ".join(" ".join(parser.parts).split())
    if not text:
        return {}

    target_season = _season_number(title)
    episodes: list[tuple[int, int]] = []
    for match in re.finditer(r"(?i)\bS\s*0?(\d{1,2})\s*E\s*0?(\d{1,3})\b", text):
        episodes.append((int(match.group(1)), int(match.group(2))))

    # Some detail pages render Chinese labels rather than SxxExx codes.
    for match in re.finditer(
        r"第\s*([\d一二三四五六七八九十百]+)\s*季[^。；;\n]{0,100}?第\s*([\d一二三四五六七八九十百]+)\s*集",
        text,
        flags=re.IGNORECASE,
    ):
        season = _cn_number(match.group(1))
        episode = _cn_number(match.group(2))
        if season is not None and episode is not None:
            episodes.append((season, episode))

    if target_season is None:
        return {}

    season_episodes = [episode for season, episode in episodes if season == target_season]
    season_words = {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}
    season_labels = f"{target_season}|{re.escape(season_words.get(target_season, str(target_season)))}"
    finale_pattern = re.compile(
        rf"(?:S\s*0?{target_season}|第\s*(?:{season_labels})\s*季)"
        r"[^。；;\n]{0,80}(?:剧终|完结|全季|大结局)",
        flags=re.IGNORECASE,
    )
    explicit_finale = bool(
        finale_pattern.search(text)
        or re.search(r"(?:本季|该季)[^。；;\n]{0,20}(?:剧终|完结|全季|大结局)", text, flags=re.IGNORECASE)
    )
    result: dict[str, object] = {
        "latest_season": target_season,
        "season_final": explicit_finale,
    }
    if explicit_finale:
        result["website_status"] = f"S{target_season:02d}剧终"
    elif season_episodes:
        result["latest_episode"] = max(season_episodes)
        result["website_status"] = f"S{target_season:02d}E{max(season_episodes):02d}"
    return result


def parse_detail_poster(html: str, base_url: str) -> str:
    """Return the first canonical poster candidate without inventing a URL."""
    parser = _PosterParser()
    parser.feed(html or "")
    for candidate in parser.candidates:
        value = urljoin(base_url, candidate.strip())
        if value.startswith(("https://", "http://")):
            return value
    return ""


def _compact_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    # Provider/library metadata can use the common ``副本`` spelling while
    # dyjie uses ``复本``.  Normalize this known title variant only for
    # matching; the original display metadata is never rewritten.
    value = value.replace("副本", "复本")
    value = re.sub(r"\s*第\s*[\d一二三四五六七八九十百]+\s*季\s*", " ", value)
    value = re.sub(r"\s*s\d{1,2}\b", " ", value)
    value = re.sub(r"[\s·:：.。_\-—]+", "", value)
    return value


def _season_number(value: str) -> int | None:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    match = re.search(r"第\s*([\d一二三四五六七八九十百]+)\s*季", value)
    if not match:
        match = re.search(r"\bs(\d{1,2})\b", value)
    if not match:
        match = re.search(r"\bseason\s*(\d{1,2})\b", value)
    if not match:
        return None
    token = match.group(1)
    if token.isdigit():
        return int(token)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100}
    if token in digits:
        return digits[token]
    if len(token) == 2 and token[0] == "十" and token[1] in digits:
        return 10 + digits[token[1]]
    if len(token) == 2 and token[1] == "十" and token[0] in digits:
        return digits[token[0]] * 10
    return None


def titles_match(local_title: str, subscription_title: str) -> bool:
    """Match titles without allowing one season to bind to another season."""
    local_season = _season_number(local_title)
    subscription_season = _season_number(subscription_title)
    if local_season is not None and subscription_season is not None and local_season != subscription_season:
        return False
    left = _compact_title(local_title)
    right = _compact_title(subscription_title)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return len(shorter) >= 4 and shorter in longer and len(shorter) / len(longer) >= 0.6


def subscription_has_undownloaded_update(
    item: dict[str, object],
    local_files: list,
    requested_season: int | None,
) -> bool:
    """Return whether the site's known update is absent from local files.

    ``local_files`` must already be restricted to the exact subscribed season.
    This keeps the badge about a missing website update, rather than about a
    different season or a stale local title.
    """
    if requested_season is None:
        return not local_files

    latest_season = item.get("latest_season")
    try:
        latest_season = int(latest_season) if latest_season is not None else None
    except (TypeError, ValueError):
        latest_season = None
    if latest_season is not None and latest_season != requested_season:
        return False

    latest_episode = item.get("latest_episode")
    try:
        latest_episode = int(latest_episode) if latest_episode is not None else None
    except (TypeError, ValueError):
        latest_episode = None
    if latest_episode is not None and latest_episode > 0:
        local_episodes = {
            int(file_row["episode"] or 0)
            for file_row in local_files
            if file_row["episode"] is not None
        }
        return latest_episode not in local_episodes

    # A finale is an explicit site state but may not expose a numeric episode.
    # With no exact-season file we can still safely flag the missing update;
    # with files present, do not invent a missing episode.
    return bool(item.get("season_final")) and not local_files


def subscription_update_timestamp(
    value: str,
    reference_epoch: float | None = None,
) -> tuple[float | None, bool]:
    """Convert a site display value using the time at which it was fetched."""
    text = unicodedata.normalize("NFKC", value or "").strip().casefold()
    if not text:
        return None, False
    reference_epoch = time.time() if reference_epoch is None else float(reference_epoch)
    if "刚刚" in text or "刚才" in text:
        return reference_epoch, False
    if "昨天" in text:
        return reference_epoch - 86400, False
    if "前天" in text:
        return reference_epoch - 2 * 86400, False
    relative = re.search(r"(\d+)\s*(分钟|小时|天|周|月|年)\s*前", text)
    if relative:
        amount = int(relative.group(1))
        unit = relative.group(2)
        factor = {"分钟": 60, "小时": 3600, "天": 86400, "周": 7 * 86400, "月": 30 * 86400, "年": 365 * 86400}[unit]
        return reference_epoch - amount * factor, False
    absolute = re.search(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})", text)
    if absolute:
        try:
            published = date(int(absolute.group(1)), int(absolute.group(2)), int(absolute.group(3)))
            # 日期展示没有时分，保存当天中午，仅用于稳定的 45 天边界判断。
            return datetime.combine(published, datetime.min.time()).timestamp(), True
        except ValueError:
            return None, False
    return None, False


def subscription_update_age_days(
    value: str,
    today: date | None = None,
    updated_epoch: float | None = None,
    updated_at_date_only: bool = False,
) -> int | None:
    """Return age using the saved fetch-time conversion when available."""
    if updated_epoch is None:
        return None
    if updated_at_date_only:
        return max(0, ((today or datetime.now().date()) - datetime.fromtimestamp(updated_epoch).date()).days)
    return max(0, int((time.time() - updated_epoch) // 86400))


def subscription_poster_is_recent(
    value: str,
    updated_epoch: float | None = None,
    updated_at_date_only: bool = False,
    max_days: int = SUBSCRIPTION_MAX_POSTER_AGE_DAYS,
) -> bool:
    """Only confirmed stale updates are hidden; legacy relative values need a saved timestamp."""
    if updated_epoch is None:
        updated_epoch, updated_at_date_only = subscription_update_timestamp(value, time.time())
        # A relative value without its original fetch time must not be treated
        # as freshly updated on every application start.
        if updated_epoch is None or (not updated_at_date_only and re.search(r"前|刚", value or "")):
            return False
    if updated_at_date_only:
        age = subscription_update_age_days(
            value,
            updated_epoch=updated_epoch,
            updated_at_date_only=True,
        )
        return age is not None and age <= max_days
    # Relative timestamps retain the fetch-time epoch.  Compare seconds here
    # so 45 days plus one second is stale instead of being rounded down to 45.
    return (time.time() - float(updated_epoch)) <= max_days * 86400


def parse_recent_updates(html: str, captured_at: float | None = None) -> list[SubscriptionItem]:
    if not html or any(marker in html.lower() for marker in ("用户登录", "登录账号", "password")):
        raise SubscriptionLoginRequired("请先在订阅页面登录 dyjie.net")

    parser = _TableParser()
    parser.feed(html)
    captured_at = time.time() if captured_at is None else float(captured_at)
    items: list[SubscriptionItem] = []
    seen_titles: set[str] = set()
    for table in parser.tables:
        if not table:
            continue
        header = [cell[0] for cell in table[0]]
        if not any("名称" in cell for cell in header) or not any("更新时间" in cell for cell in header):
            continue
        name_index = next(i for i, cell in enumerate(header) if "名称" in cell)
        update_index = next(i for i, cell in enumerate(header) if "更新时间" in cell)
        link_index = next(
            (i for i, cell in enumerate(header) if "链接" in cell or "查看" in cell),
            None,
        )
        for row in table[1:]:
            if len(row) <= max(name_index, update_index):
                continue
            title = row[name_index][0].strip()
            updated_at = row[update_index][0].strip()
            if not title or title == "暂无" or not updated_at:
                continue
            if title in seen_titles:
                continue
            seen_titles.add(title)
            href = ""
            if link_index is not None and link_index < len(row):
                href = row[link_index][1]
            if not href:
                href = next((cell_href for _, cell_href in row if cell_href), "")
            updated_epoch, updated_at_date_only = subscription_update_timestamp(updated_at, captured_at)
            items.append(
                SubscriptionItem(
                    title,
                    updated_at,
                    urljoin(DEFAULT_SUBSCRIPTION_URL, href) if href else "",
                    "",
                    updated_epoch,
                    updated_at_date_only,
                )
            )
    if not items:
        raise SubscriptionPageError("订阅页中没有找到最近更新的影视")
    return items
