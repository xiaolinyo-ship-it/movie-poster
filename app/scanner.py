"""NAS 媒体库扫描与结构识别。"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


VIDEO_EXTS = {".mp4", ".mkv", ".avi", ".ts", ".wmv", ".flv", ".mov", ".m4v", ".webm", ".rmvb"}
SUB_EXTS = {".srt", ".ass", ".ssa", ".sub", ".idx"}

EP_RE = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")
SEASON_DIR_RE = re.compile(r"(?:[Ss]eason\s*|S)?0?(\d{1,2})(?:\s*季)?$", re.IGNORECASE)
CN_SEASON_RE = re.compile(r"第\s*([\d一二三四五六七八九十百]+)\s*季")
CN_EP_RE = re.compile(r"第\s*([\d一二三四五六七八九十百]+)\s*[集话]")
LONE_EP_RE = re.compile(r"(?:^|[^\d])[Ee](\d{1,3})(?:[^\d]|$)")


def _number_token(value: str) -> int | None:
    value = (value or "").strip()
    if value.isdigit():
        return int(value)
    digits = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
              "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
              "百": 100}
    if not value or any(ch not in digits for ch in value):
        return None
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        return (digits.get(left, 1) if left else 1) * 10 + (digits.get(right, 0) if right else 0)
    return digits.get(value)


def is_video(name: str) -> bool:
    return Path(name).suffix.lower() in VIDEO_EXTS


def is_sub(name: str) -> bool:
    return Path(name).suffix.lower() in SUB_EXTS


@dataclass
class MediaFile:
    path: str
    name: str
    season: int = 0
    episode: int | None = None


@dataclass
class MediaItem:
    kind: str  # "tv" | "movie"
    title: str
    path: str
    files: list[MediaFile] = field(default_factory=list)
    scan_complete: bool = True

    @property
    def season_count(self) -> int:
        if self.kind != "tv":
            return 0
        return len({f.season for f in self.files if f.season > 0})

    @property
    def episode_count(self) -> int:
        return len([f for f in self.files if f.episode is not None])

    @property
    def total_size_gb(self) -> float:
        total = 0.0
        for f in self.files:
            try:
                total += os.path.getsize(f.path)
            except OSError:
                pass
        return total / (1024 ** 3)


def _parse_episode(name: str, parent_dir: str | None = None) -> tuple[int, int | None]:
    """返回 (season, episode)。season=0 表示未能识别。"""
    m = EP_RE.search(name)
    if m:
        return int(m.group(1)), int(m.group(2))
    if parent_dir:
        cm = CN_SEASON_RE.search(parent_dir)
        if cm:
            season = _number_token(cm.group(1)) or 0
        else:
            sm = SEASON_DIR_RE.search(parent_dir)
            season = int(sm.group(1)) if sm else 0
        em = CN_EP_RE.search(name)
        if em:
            episode = _number_token(em.group(1))
            return season, episode
        le = LONE_EP_RE.search(name)
        if le and season:
            return season, int(le.group(1))
        if season:
            # Keep a reliable season even when this filename has no
            # recognizable episode number; unknown is not season zero.
            return season, None
    return 0, None


def _scan_files(
    root: str,
    errors: list[str] | None = None,
    should_cancel=None,
) -> tuple[list[MediaFile], bool]:
    out: list[MediaFile] = []
    local_errors: list[str] = []

    def onerror(exc: OSError):
        local_errors.append(f"{getattr(exc, 'filename', root) or root}: {exc}")

    for dirpath, dirnames, filenames in os.walk(root, onerror=onerror):
        if should_cancel and should_cancel():
            return out, False
        # 跳过回收站
        dirnames[:] = [d for d in dirnames if d != "#recycle" and d.lower() != "sample"]
        for fn in filenames:
            if not is_video(fn):
                continue
            if "sample" in fn.lower():
                continue
            parent = os.path.basename(dirpath)
            season, episode = _parse_episode(fn, parent)
            out.append(MediaFile(path=os.path.join(dirpath, fn), name=fn, season=season, episode=episode))
    out.sort(key=lambda f: (f.season, f.episode or 0, f.name))
    if errors is not None:
        errors.extend(local_errors)
    return out, not local_errors


def scan_tv(root: str, errors: list[str] | None = None, should_cancel=None) -> list[MediaItem]:
    items: list[MediaItem] = []
    if not root or not os.path.isdir(root):
        if errors is not None:
            errors.append(f"电视剧根目录不可访问：{root or '(空)'}")
        return items
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        if errors is not None:
            errors.append(f"电视剧根目录不可读取：{root}: {exc}")
        return items
    for name in names:
        if should_cancel and should_cancel():
            return items
        d = os.path.join(root, name)
        if not os.path.isdir(d) or name == "#recycle":
            continue
        files, complete = _scan_files(d, errors, should_cancel)
        if files:
            items.append(MediaItem(kind="tv", title=name, path=d, files=files, scan_complete=complete))
    items.sort(key=lambda i: i.title.lower())
    return items


def _resolve_movie_branches(top_dir: str, cur_dir: str, depth: int) -> list[tuple[str, str]]:
    """返回 [(显示名, 实际播放目录)]，处理分类目录/发布组嵌套。"""
    try:
        entries = sorted(os.listdir(cur_dir))
    except OSError:
        return []
    files = [e for e in entries if os.path.isfile(os.path.join(cur_dir, e)) and is_video(e)]
    subdirs = [e for e in entries if os.path.isdir(os.path.join(cur_dir, e)) and e != "#recycle"]
    if files:
        # 直接有视频：当前目录即电影目录
        title = os.path.basename(top_dir) if depth == 1 and len(subdirs) == 0 else os.path.basename(cur_dir)
        if depth == 1:
            title = os.path.basename(top_dir)
        return [(title, cur_dir)]
    if len(subdirs) == 1:
        # 发布组嵌套：穿透到子目录；内层是发布组名则用外层电影名，否则用内层名
        sub = subdirs[0]
        title = os.path.basename(top_dir) if looks_like_release_group(sub) else sub
        return [(title, os.path.join(cur_dir, sub))]
    if len(subdirs) > 1:
        # 分类目录（如 3D）：每个子目录是一部电影
        out = []
        for sd in subdirs:
            out.extend(_resolve_movie_branches(os.path.join(cur_dir, sd), os.path.join(cur_dir, sd), depth + 1))
        return out
    return []


def scan_movies(root: str, errors: list[str] | None = None, should_cancel=None) -> list[MediaItem]:
    items: list[MediaItem] = []
    if not root or not os.path.isdir(root):
        if errors is not None:
            errors.append(f"电影根目录不可访问：{root or '(空)'}")
        return items
    try:
        names = sorted(os.listdir(root))
    except OSError as exc:
        if errors is not None:
            errors.append(f"电影根目录不可读取：{root}: {exc}")
        return items
    for name in names:
        if should_cancel and should_cancel():
            return items
        d = os.path.join(root, name)
        if not os.path.isdir(d) or name == "#recycle":
            continue
        for title, play_dir in _resolve_movie_branches(d, d, 1):
            files, complete = _scan_files(play_dir, errors, should_cancel)
            if files:
                items.append(MediaItem(kind="movie", title=title, path=play_dir, files=files, scan_complete=complete))
    items.sort(key=lambda i: i.title.lower())
    return items


def normalize_path(p: str) -> str:
    return os.path.normpath(p).lower()


def has_media(path: str) -> bool:
    try:
        return any(is_video(f) for _, _, fs in os.walk(path) for f in fs)
    except OSError:
        return False


def looks_like_release_group(name: str) -> bool:
    """发布组目录特征：含【】/[]/www，或含年份+大量英文数字。"""
    if any(ch in name for ch in "【】[]"):
        return True
    if "www." in name.lower():
        return True
    if re.search(r"(19|20)\d{2}", name):
        return True
    return False
