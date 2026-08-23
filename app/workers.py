"""后台线程：扫描、豆瓣抓取、整理。"""

from __future__ import annotations

import time

from PySide6.QtCore import QObject, QRunnable, QThread, Signal

from . import scanner
from .douban import DoubanClient
from .tmdb import TmdbClient
from .organize import apply_plan, build_plan, undo_last


class ScanWorker(QThread):
    progress = Signal(str)
    finished_scan = Signal(list, list)  # tv items, movie items
    error = Signal(str)

    def __init__(self, tv_root: str, movie_root: str):
        super().__init__()
        self.tv_root = tv_root
        self.movie_root = movie_root

    def run(self):
        try:
            self.progress.emit("正在扫描电视剧目录…")
            tv = scanner.scan_tv(self.tv_root)
            self.progress.emit(f"电视剧 {len(tv)} 部，扫描电影目录…")
            movies = scanner.scan_movies(self.movie_root)
            self.progress.emit(f"扫描完成：电视剧 {len(tv)} 部，电影 {len(movies)} 部")
            self.finished_scan.emit(tv, movies)
        except Exception as e:
            self.error.emit(str(e))


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
