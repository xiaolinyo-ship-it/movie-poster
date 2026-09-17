"""后台线程：扫描、豆瓣抓取、整理。"""

from __future__ import annotations

import os
import hashlib
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThread, Signal
from PySide6.QtGui import QImage

from . import scanner
from .douban import DoubanClient
from .tmdb import TmdbClient
from .organize import apply_plan, build_plan, undo_last
from .subscriptions import _season_number, subscription_poster_is_recent


class SubscriptionHighResSignals(QObject):
    done = Signal(object)


class SubscriptionHighResWorker(QRunnable):
    """Resolve subscription posters and independent high-resolution backgrounds."""

    IMDB_SUGGEST_URL = "https://v2.sg.media-imdb.com/suggestion/x/{query}.json"

    def __init__(self, items: list[dict[str, str]], cache_dir: str | Path, tmdb_api_key: str = ""):
        super().__init__()
        self.items = [dict(item) for item in items]
        self.cache_dir = Path(cache_dir)
        self.tmdb = TmdbClient(self.cache_dir, tmdb_api_key)
        self.signals = SubscriptionHighResSignals()

    @staticmethod
    def _normalized(value: str) -> str:
        value = unicodedata.normalize("NFKC", value or "").casefold()
        return "".join(ch for ch in value if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")

    @staticmethod
    def _large_douban_url(url: str) -> str:
        # Douban exposes small/medium/large ratio-poster paths for the same
        # image; use the large path when it exists.
        value = url or ""
        value = re.sub(r"/(?:s|m)_ratio_poster/", "/l_ratio_poster/", value)
        value = value.replace("/photo/m/public/", "/photo/l/public/")
        return value

    @staticmethod
    def _without_season(value: str) -> str:
        value = unicodedata.normalize("NFKC", value or "")
        value = re.sub(r"\s*第\s*[\d一二三四五六七八九十百]+\s*季\s*", " ", value, flags=re.I)
        value = re.sub(r"\s*(?:S|Season)\s*\d{1,2}\b", " ", value, flags=re.I)
        return " ".join(value.split()).strip()

    @staticmethod
    def _image_size(path: str | Path) -> tuple[int, int]:
        if not path or not Path(path).is_file():
            return (0, 0)
        image = QImage(str(path))
        return (image.width(), image.height())

    @staticmethod
    def _imdb_original_image_url(url: str) -> str:
        """Remove IMDb's resize suffix so the CDN can return the source image."""
        return re.sub(r"\._V1_[^/]*\.(jpe?g|png|webp)$", r".\1", url or "", flags=re.I)

    def _download_background(self, url: str, name: str) -> str:
        if not url or not name:
            return ""
        dest_dir = self.cache_dir / "backgrounds"
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]", "_", name) or "subscription"
        dest = dest_dir / f"{safe}.jpg"
        if dest.exists() and dest.stat().st_size > 10000:
            width, height = self._image_size(dest)
            if max(width, height) >= 1600:
                return str(dest)
        tmp = dest.with_suffix(".part")
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "Chrome/126.0.0.0 Safari/537.36",
                    "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read()
            if len(data) < 10000:
                return ""
            tmp.write_bytes(data)
            width, height = self._image_size(tmp)
            if max(width, height) < 1600:
                tmp.unlink(missing_ok=True)
                return ""
            tmp.replace(dest)
            return str(dest)
        except Exception:
            tmp.unlink(missing_ok=True)
            return ""

    def _resolve_tmdb_background(self, title: str) -> str:
        if not self.tmdb.enabled:
            return ""
        query = self._without_season(title)
        if not query:
            return ""
        for kind in ("tv", "movie"):
            try:
                meta = self.tmdb.fetch_item_meta(query, kind)
                backdrop_url = str(meta.get("backdrop_url") or "")
                tmdb_id = str(meta.get("tmdb_id") or "")
                if not backdrop_url or not tmdb_id:
                    continue
                # TMDB's original variant is preferable to the normal 1280px
                # rendition when the provider has a larger source available.
                backdrop_url = backdrop_url.replace("/w1280/", "/original/")
                path = self.tmdb.download_backdrop(backdrop_url, f"subscription_{tmdb_id}")
                width, height = self._image_size(path)
                if path and max(width, height) >= 1600:
                    return str(path)
            except Exception:
                continue
        return ""

    def _imdb_suggest(self, query: str) -> list[dict]:
        key = hashlib.md5(query.encode("utf-8")).hexdigest()
        cache = self.cache_dir / f"imdb_suggest_{key}.json"
        if cache.exists():
            try:
                data = json.loads(cache.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return data
            except Exception:
                pass
        try:
            url = self.IMDB_SUGGEST_URL.format(query=urllib.parse.quote(query))
            request = urllib.request.Request(url, headers={"User-Agent": "MoviePoster/2.0"})
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8", "ignore"))
            results = data.get("d") if isinstance(data, dict) else []
            if isinstance(results, list):
                cache.write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
                return results
        except Exception:
            pass
        return []

    def _resolve_imdb_background(self, item: dict[str, str], detail: dict) -> str:
        queries = []
        for value in (
            detail.get("original_title"),
            detail.get("sub_title"),
            detail.get("title"),
            item.get("title"),
        ):
            query = self._without_season(str(value or ""))
            if query and query.casefold() not in {x.casefold() for x in queries}:
                queries.append(query)
        for query in queries:
            results = self._imdb_suggest(query)
            normalized_query = self._normalized(query)
            ranked = []
            for result in results:
                image = result.get("i") or {}
                image_url = str(image.get("imageUrl") or "").strip()
                if not image_url:
                    continue
                title = self._normalized(str(result.get("l") or ""))
                score = 1 if normalized_query and (
                    normalized_query in title or title in normalized_query
                ) else 0
                ranked.append((score, int(image.get("width") or 0), result))
            ranked.sort(key=lambda value: (value[0], value[1]), reverse=True)
            for _, _, result in ranked:
                image = result.get("i") or {}
                image_url = self._imdb_original_image_url(str(image.get("imageUrl") or ""))
                path = self._download_background(image_url, f"subscription_imdb_{result.get('id', '')}")
                if path:
                    return path
        return ""

    def _resolve_background(self, item: dict[str, str], detail: dict) -> str:
        existing = str(item.get("background") or "").strip()
        if existing:
            width, height = self._image_size(existing)
            if max(width, height) >= 1600:
                return existing
        background = self._resolve_tmdb_background(str(item.get("title") or ""))
        if background:
            return background
        return self._resolve_imdb_background(item, detail)

    def _resolve_one(self, client: DoubanClient, item: dict[str, str]) -> tuple[str, str]:
        title = str(item.get("title") or "").strip()
        if not title:
            return "", ""
        existing = str(item.get("hd_poster") or "").strip()
        highres = ""
        if existing:
            width, height = self._image_size(existing)
            if max(width, height) >= 900:
                highres = existing
        existing_background = str(item.get("background") or "").strip()
        if existing_background:
            width, height = self._image_size(existing_background)
            if max(width, height) < 1600:
                existing_background = ""
        if highres and existing_background:
            return highres, existing_background

        season = _season_number(title)
        candidates = client.suggest(title)
        if not candidates:
            return highres, self._resolve_background(item, {})
        requested = self._normalized(title)
        exact = next(
            (candidate for candidate in candidates
             if self._normalized(str(candidate.get("title") or "")) == requested),
            None,
        )
        # Never silently bind a season-bearing subscription to a different or
        # generic season.  Exact results are preferred; if none exists, skip.
        if exact is None and season is not None:
            return highres, self._resolve_background(item, {})
        candidate = exact or candidates[0]
        sid = str(candidate.get("id") or "").strip()
        if not sid:
            return highres, self._resolve_background(item, {})
        detail = client.detail(sid) or {}
        detail_title = str(detail.get("title") or candidate.get("title") or "").strip()
        if season is not None and _season_number(detail_title) != season:
            return highres, self._resolve_background(item, detail)
        if season is not None and self._normalized(detail_title) != requested:
            return highres, self._resolve_background(item, detail)
        picture = detail.get("pic") or {}
        poster_url = self._large_douban_url(str(picture.get("large") or picture.get("normal") or ""))
        if not highres and poster_url:
            path = client.download_poster(poster_url, f"subscription_hd_{sid}")
            if path:
                width, height = self._image_size(path)
                if max(width, height) >= 900:
                    highres = str(path)
        background = self._resolve_background(item, detail)
        return highres, background

    def run(self):
        try:
            client = DoubanClient(self.cache_dir, delay=0.35)
            result = []
            for item in self.items:
                updated = dict(item)
                highres, background = self._resolve_one(client, updated) if subscription_poster_is_recent(
                    str(updated.get("updated_at") or ""),
                    updated.get("updated_at_epoch"),
                    bool(updated.get("updated_at_date_only", False)),
                ) else ("", str(updated.get("background") or "").strip())
                if highres:
                    updated["hd_poster"] = highres
                if background:
                    updated["background"] = background
                result.append(updated)
            self.signals.done.emit(result)
        except Exception:
            # High-resolution artwork is additive; a provider failure must not
            # hide or reorder the already-synced subscription list.
            self.signals.done.emit(self.items)


class ScanWorker(QThread):
    progress = Signal(str)
    # Keep nested scan results on the worker; do not marshal the full object
    # graph through a queued Qt signal on Windows.
    finished_scan = Signal()
    cancelled = Signal()
    error = Signal(str)

    def __init__(self, tv_root: str, movie_root: str):
        super().__init__()
        self.tv_root = tv_root
        self.movie_root = movie_root
        self.tv_items = []
        self.movie_items = []
        self.tv_errors: list[str] = []
        self.movie_errors: list[str] = []

    def run(self):
        try:
            self.progress.emit("正在扫描电视剧目录…")
            self.tv_items = scanner.scan_tv(self.tv_root, self.tv_errors, self.isInterruptionRequested)
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return
            self.progress.emit(f"电视剧 {len(self.tv_items)} 部，扫描电影目录…")
            self.movie_items = scanner.scan_movies(self.movie_root, self.movie_errors, self.isInterruptionRequested)
            if self.isInterruptionRequested():
                self.cancelled.emit()
                return
            issue_count = len(self.tv_errors) + len(self.movie_errors)
            suffix = f"，发现 {issue_count} 个读取问题，已保留旧记录" if issue_count else ""
            self.progress.emit(f"扫描完成：电视剧 {len(self.tv_items)} 部，电影 {len(self.movie_items)} 部{suffix}")
            self.finished_scan.emit()
        except Exception as e:
            self.error.emit(str(e))


class RecentFilesWorker(QThread):
    """Read media-directory timestamps without blocking the Qt/UI thread.

    ``root`` is the media item's directory and is the primary ordering key,
    matching Windows Explorer's ``修改日期`` (last modified date).  ``files``
    are only a fallback for an unavailable directory.  The worker receives
    plain paths only; it never touches the shared Store connection.
    """

    # ``dict`` is not a reliable queued-signal type in all PySide6 builds;
    # object keeps the payload in Python space across the worker boundary.
    finished_times = Signal(int, object)
    error = Signal(int, str)

    def __init__(self, generation: int, items: dict[int, object]):
        super().__init__()
        self.generation = generation
        self.items = items

    def run(self):
        try:
            result: dict[int, tuple[int, float]] = {}
            for item_id, value in self.items.items():
                latest = 0.0
                root = ""
                fallback_files: list[str] = []
                if isinstance(value, dict):
                    root = str(value.get("root") or "")
                    fallback_files = [str(p) for p in (value.get("files") or []) if p]
                else:
                    # Keep compatibility with callers that provide a plain
                    # path list.
                    fallback_files = [str(p) for p in (value or []) if p]

                if root:
                    try:
                        latest = os.path.getmtime(root)
                    except (OSError, ValueError):
                        try:
                            latest = os.path.getctime(root)
                        except (OSError, ValueError):
                            latest = 0.0

                # If the item directory is unavailable, use the newest media
                # file as a best-effort fallback.  This keeps NAS disconnects
                # non-fatal while preserving the intended directory ordering.
                if not latest:
                    for path in fallback_files:
                        if self.isInterruptionRequested():
                            return
                        try:
                            latest = max(latest, os.path.getmtime(path))
                        except (OSError, ValueError):
                            try:
                                latest = max(latest, os.path.getctime(path))
                            except (OSError, ValueError):
                                continue
                result[item_id] = (1 if latest else 0, latest)
            self.finished_times.emit(self.generation, result)
        except Exception as exc:
            self.error.emit(self.generation, str(exc))


class DoubanTask(QRunnable):
    """单个条目的豆瓣元数据抓取，通过信号回主线程。"""

    def __init__(self, client: DoubanClient, item_id: int, title: str, kind: str,
                 sid: str | None, signals: "DoubanSignals"):
        super().__init__()
        self.client = client
        self.item_id = item_id
        self.title = title
        self.kind = kind
        self.sid = sid
        self.signals = signals

    def run(self):
        meta = self.client.fetch_item_meta(self.title, self.kind, self.sid)
        if not meta:
            self.signals.failed.emit(self.item_id)
            return
        poster_path = None
        if meta.get("poster") and meta.get("douban_id"):
            poster_path = self.client.download_poster(meta["poster"], meta["douban_id"])
        self.signals.done.emit(self.item_id, meta, str(poster_path) if poster_path else None)


class DoubanSignals(QObject):
    done = Signal(int, dict, str)
    failed = Signal(int)


class TmdbTask(QRunnable):
    """Optional TMDB supplement; never overwrites Douban score/title/summary."""

    def __init__(self, client: TmdbClient, item_id: int, title: str, kind: str,
                 signals: "TmdbSignals"):
        super().__init__()
        self.client = client
        self.item_id = item_id
        self.title = title
        self.kind = kind
        self.signals = signals

    def run(self):
        try:
            meta = self.client.fetch_item_meta(self.title, self.kind)
            if not meta:
                self.signals.failed.emit(self.item_id)
                return
            backdrop = self.client.download_backdrop(meta.get("backdrop_url", ""), meta.get("tmdb_id", ""))
            self.signals.done.emit(self.item_id, meta, str(backdrop) if backdrop else "")
        except Exception:
            self.signals.failed.emit(self.item_id)


class TmdbSignals(QObject):
    done = Signal(int, dict, str)
    failed = Signal(int)


class TmdbLinkTask(QRunnable):
    """Resolve only a TMDB movie/TV ID; never returns replacement media metadata."""

    def __init__(self, client: TmdbClient, item_id: int, kind: str, queries: list[str], year: str | None,
                 signals: "TmdbLinkSignals"):
        super().__init__()
        self.client, self.item_id, self.kind, self.queries, self.year = client, item_id, kind, queries, year
        self.signals = signals

    def run(self):
        try:
            tmdb_id = self.client.find_media_id(self.kind, *self.queries, year=self.year)
            if tmdb_id:
                self.signals.done.emit(self.item_id, tmdb_id)
            else:
                self.signals.failed.emit(self.item_id)
        except Exception:
            self.signals.failed.emit(self.item_id)


class TmdbLinkSignals(QObject):
    done = Signal(int, str)
    failed = Signal(int)


class TmdbEpisodeTask(QRunnable):
    """Fetch one TV episode's title and air metadata without blocking the UI."""

    def __init__(self, client: TmdbClient, item_id: int, tmdb_id: str, season: int, episode: int,
                 signals: "TmdbEpisodeSignals"):
        super().__init__()
        self.client = client
        self.item_id = item_id
        self.tmdb_id = tmdb_id
        self.season = season
        self.episode = episode
        self.signals = signals

    def run(self):
        try:
            data = self.client.fetch_tv_episode(self.tmdb_id, self.season, self.episode)
            if data:
                self.signals.done.emit(self.item_id, self.season, self.episode, data)
            else:
                self.signals.failed.emit(self.item_id, self.season, self.episode)
        except Exception:
            self.signals.failed.emit(self.item_id, self.season, self.episode)


class TmdbEpisodeSignals(QObject):
    done = Signal(int, int, int, dict)
    failed = Signal(int, int, int)


class TmdbRelationTask(QRunnable):
    """Synchronize only people and genre relations for one TMDB item."""

    def __init__(self, client: TmdbClient, item_id: int, tmdb_id: str, kind: str,
                 signals: "TmdbRelationSignals"):
        super().__init__()
        self.client, self.item_id, self.tmdb_id, self.kind = client, item_id, tmdb_id, kind
        self.signals = signals

    def run(self):
        try:
            data = self.client.fetch_item_relations(self.tmdb_id, self.kind)
            if data:
                self.signals.done.emit(self.item_id, data)
            else:
                self.signals.failed.emit(self.item_id)
        except Exception:
            self.signals.failed.emit(self.item_id)


class TmdbRelationSignals(QObject):
    done = Signal(int, dict)
    failed = Signal(int)


class OrganizePlanWorker(QThread):
    finished_plan = Signal(object)  # OrganizePlan
    error = Signal(str)

    def __init__(self, tv_root: str, movie_root: str, trash_root: str):
        super().__init__()
        self.tv_root = tv_root
        self.movie_root = movie_root
        self.trash_root = trash_root

    def run(self):
        try:
            self.finished_plan.emit(build_plan(self.tv_root, self.movie_root, self.trash_root))
        except Exception as e:
            self.error.emit(str(e))


class OrganizeApplyWorker(QThread):
    log_line = Signal(str)
    finished_apply = Signal()

    def __init__(self, plan, undo_path: str):
        super().__init__()
        self.plan = plan
        self.undo_path = undo_path

    def run(self):
        for line in apply_plan(self.plan, self.undo_path):
            self.log_line.emit(line)
        self.finished_apply.emit()


class UndoWorker(QThread):
    log_line = Signal(str)
    finished_undo = Signal()

    def __init__(self, undo_path: str):
        super().__init__()
        self.undo_path = undo_path

    def run(self):
        for line in undo_last(self.undo_path):
            self.log_line.emit(line)
        self.finished_undo.emit()


class ManualSearchWorker(QThread):
    """手动搜索豆瓣条目（详情页补全）。"""

    result = Signal(list)  # [{id, title, year, rating}]
    finished_search = Signal()

    def __init__(self, client, query: str):
        super().__init__()
        self.client = client
        self.query = query

    def run(self):
        out = []
        seen = set()
        for cand in self.client.suggest(self.query):
            sid = str(cand.get("id") or "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append({
                    "id": sid,
                    "title": cand.get("title") or "",
                    "year": cand.get("year") or "",
                    "rating": None,
                })
        for item in self.client._search_rexxar(self.query):
            sid = item.get("id")
            if sid and sid not in seen:
                seen.add(sid)
                d = self.client._detail_direct(sid)
                out.append({
                    "id": sid,
                    "title": (d or {}).get("title") or item.get("title") or "",
                    "year": (d or {}).get("year") or "",
                    "rating": (d.get("rating") or {}).get("value") if d else None,
                })
        self.result.emit(out[:10])
        self.finished_search.emit()


class ApplySubjectWorker(QThread):
    """按选定豆瓣 id 抓取详情与海报。"""

    done = Signal(int, dict, str)  # item_id, meta, poster_path
    failed = Signal(int)

    def __init__(self, client, item_id: int, title: str, kind: str, sid: str):
        super().__init__()
        self.client = client
        self.item_id = item_id
        self.title = title
        self.kind = kind
        self.sid = sid

    def run(self):
        meta = self.client.fetch_item_meta(self.title, self.kind, self.sid)
        if not meta or not meta.get("douban_id"):
            self.failed.emit(self.item_id)
            return
        poster_path = None
        if meta.get("poster"):
            poster_path = self.client.download_poster(meta["poster"], meta["douban_id"])
        self.done.emit(self.item_id, meta, str(poster_path) if poster_path else None)
