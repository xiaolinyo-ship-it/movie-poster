"""媒体库整理引擎：归类、清理、空目录删除，全部可撤销。"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field

from .scanner import EP_RE, SUB_EXTS, is_video


JUNK_EXTS = {
    ".torrent", ".txt", ".png", ".jpg", ".jpeg", ".gif", ".qkdownloading",
    ".zip", ".rar", ".7z", ".nfo", ".url", ".html", ".htm", ".db", ".dat",
    ".lnk", ".exe", ".part", ".crdownload",
}


@dataclass
class MoveOp:
    source: str
    target: str
    kind: str  # tv_flatten | movie_flatten | movie_to_tv | sample_trash | junk_trash | empty_dir_del
    label: str


@dataclass
class OrganizePlan:
    ops: list[MoveOp] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.ops)


def _is_season_dir(name: str) -> bool:
    return bool(re.match(r"^(?:season\s*\d+|s\d{1,2}|第\s*\d+\s*季)$", name, re.IGNORECASE))


def _is_release_group_dir(name: str) -> bool:
    if any(ch in name for ch in "【】[]"):
        return True
    if "www." in name.lower():
        return True
    if re.search(r"(19|20)\d{2}", name):
        return True
    return False


def _find_season_dir(item_path: str, season: int) -> str | None:
    try:
        for name in os.listdir(item_path):
            d = os.path.join(item_path, name)
            if os.path.isdir(d):
                low = name.lower()
                if f"season {season}" in low or low in (f"s{season:02d}", f"s{season}"):
                    return d
    except OSError:
        pass
    return None


def _walk_skip(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "#recycle" and d.lower() != "sample"]
        yield dirpath, dirnames, filenames


# ---------- 电视剧 ----------

def _flatten_dir(cur_dir: str, item_path: str, ops: list[MoveOp]) -> None:
    """递归提升发布组/集数目录内的视频与字幕到剧目录。"""
    try:
        entries = os.listdir(cur_dir)
    except OSError:
        return
    videos = [e for e in entries if os.path.isfile(os.path.join(cur_dir, e)) and is_video(e)]
    for v in videos:
        season = None
        m = EP_RE.search(v)
        if m:
            season = int(m.group(1))
        target_dir = _find_season_dir(item_path, season) if season else None
        target_dir = target_dir or item_path
        src = os.path.join(cur_dir, v)
        dst = os.path.join(target_dir, v)
        if src != dst:
            ops.append(MoveOp(src, dst, "tv_flatten", f"提升单集: {os.path.basename(cur_dir)}/{v}"))
        base = os.path.splitext(v)[0]
        for e in entries:
            if os.path.splitext(e)[1].lower() in SUB_EXTS and os.path.splitext(e)[0].startswith(base):
                ops.append(MoveOp(os.path.join(cur_dir, e), os.path.join(target_dir, e), "tv_flatten", f"跟随字幕: {e}"))
    for sub in entries:
        p = os.path.join(cur_dir, sub)
        if os.path.isdir(p) and sub != "#recycle" and sub.lower() != "sample":
            _flatten_dir(p, item_path, ops)


def plan_tv(item_path: str) -> list[MoveOp]:
    ops: list[MoveOp] = []
    try:
        subdirs = [d for d in os.listdir(item_path) if os.path.isdir(os.path.join(item_path, d))]
    except OSError:
        return ops
    for sd in subdirs:
        if sd.lower() == "sample" or _is_season_dir(sd):
            continue
        sdir = os.path.join(item_path, sd)
        if _is_release_group_dir(sd) or sd.strip().isdigit() or re.search(r"第\s*\d+\s*[集话]", sd):
            _flatten_dir(sdir, item_path, ops)
    return ops


def plan_junk(item_path: str, trash_root: str) -> list[MoveOp]:
    """下载残留（torrent/广告图/临时文件）移入本地回收站。"""
    ops: list[MoveOp] = []
    for dirpath, _, filenames in _walk_skip(item_path):
        for f in filenames:
            ext = os.path.splitext(f)[1].lower()
            if ext in JUNK_EXTS:
                src = os.path.join(dirpath, f)
                rel = os.path.relpath(src, os.path.dirname(item_path))
                dst = os.path.join(trash_root, "junk", rel)
                ops.append(MoveOp(src, dst, "junk_trash", f"下载残留: {f}"))
    return ops


def plan_empty_dirs(root: str) -> list[MoveOp]:
    """空目录删除（最深层优先）。"""
    ops: list[MoveOp] = []
    empty: list[str] = []
    for dirpath, dirnames, filenames in _walk_skip(root):
        dirnames[:] = [d for d in dirnames if d != "#recycle"]
        if not dirnames and not filenames:
            empty.append(dirpath)
    # 按深度降序，先删最深的
    empty.sort(key=lambda p: p.count(os.sep), reverse=True)
    for d in empty:
        if os.path.normpath(d) != os.path.normpath(root):
            ops.append(MoveOp(d, "", "empty_dir_del", f"删除空目录: {os.path.basename(d) or d}"))
    return ops


# ---------- 电影 ----------

def plan_movie(item_path: str) -> list[MoveOp]:
    """电影目录内发布组嵌套 -> 提升；Sample -> 回收。"""
    ops: list[MoveOp] = []
    try:
        entries = os.listdir(item_path)
    except OSError:
        return ops
    subdirs = [d for d in entries if os.path.isdir(os.path.join(item_path, d))]
    direct_videos = [e for e in entries if os.path.isfile(os.path.join(item_path, e)) and is_video(e)]
    if not direct_videos and len(subdirs) == 1 and _is_release_group_dir(subdirs[0]):
        inner = os.path.join(item_path, subdirs[0])
        try:
            inner_entries = os.listdir(inner)
        except OSError:
            return ops
        inner_videos = [e for e in inner_entries if os.path.isfile(os.path.join(inner, e)) and is_video(e)]
        if inner_videos:
            for v in inner_videos:
                src = os.path.join(inner, v)
                dst = os.path.join(item_path, v)
                ops.append(MoveOp(src, dst, "movie_flatten", f"提升电影文件: {subdirs[0]}/{v}"))
                for e in inner_entries:
                    if os.path.splitext(e)[1].lower() in SUB_EXTS and os.path.splitext(e)[0].startswith(os.path.splitext(v)[0]):
                        ops.append(MoveOp(os.path.join(inner, e), os.path.join(item_path, e), "movie_flatten", f"跟随字幕: {e}"))
    return ops


def plan_samples(root: str, trash_root: str) -> list[MoveOp]:
    """Sample 样片目录移入本地回收站。"""
    ops: list[MoveOp] = []
    seen: set[str] = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "#recycle"]
        for sd in list(dirnames):
            if sd.lower() == "sample":
                src = os.path.join(dirpath, sd)
                rel = os.path.relpath(src, os.path.dirname(root))
                dst = os.path.join(trash_root, "sample", rel)
                ops.append(MoveOp(src, dst, "sample_trash", f"样片回收: {rel}"))
                dirnames.remove(sd)  # 不深入
        for f in filenames:
            if "sample" in f.lower() and is_video(f):
                src = os.path.join(dirpath, f)
                rel = os.path.relpath(src, os.path.dirname(root))
                dst = os.path.join(trash_root, "sample", rel)
                if src not in seen:
                    ops.append(MoveOp(src, dst, "sample_trash", f"样片回收: {f}"))
                    seen.add(src)
    return ops


def plan_movie_to_tv(movie_root: str, tv_root: str) -> list[MoveOp]:
    """电影目录里误放的剧集（多数文件带 SxxEyy）整体归位到电视剧目录。"""
    ops: list[MoveOp] = []
    if not os.path.isdir(movie_root) or not os.path.isdir(tv_root):
        return ops
    try:
        names = sorted(os.listdir(movie_root))
    except OSError:
        return ops
    for name in names:
        d = os.path.join(movie_root, name)
        if not os.path.isdir(d) or name == "#recycle":
            continue
        total = 0
        eps = 0
        for dirpath, dirnames, filenames in os.walk(d):
            dirnames[:] = [x for x in dirnames if x != "#recycle"]
            for f in filenames:
                if is_video(f):
                    total += 1
                    if EP_RE.search(f):
                        eps += 1
        if total >= 1 and eps >= max(1, int(total * 0.5)):
            dst = os.path.join(tv_root, name)
            if not os.path.exists(dst):
                ops.append(MoveOp(d, dst, "movie_to_tv", f"剧集归位: {name}"))
    return ops


def build_plan(tv_root: str, movie_root: str, trash_root: str) -> OrganizePlan:
    plan = OrganizePlan()
    for root in (tv_root, movie_root):
        if not root or not os.path.isdir(root):
            continue
        plan.ops.extend(plan_samples(root, trash_root))
        plan.ops.extend(plan_junk(root, trash_root))
        plan.ops.extend(plan_empty_dirs(root))
    if tv_root and os.path.isdir(tv_root):
        for name in sorted(os.listdir(tv_root)):
            d = os.path.join(tv_root, name)
            if os.path.isdir(d) and name != "#recycle":
                plan.ops.extend(plan_tv(d))
    if movie_root and os.path.isdir(movie_root):
        plan.ops.extend(plan_movie_to_tv(movie_root, tv_root))
        for name in sorted(os.listdir(movie_root)):
            d = os.path.join(movie_root, name)
            if os.path.isdir(d) and name != "#recycle":
                plan.ops.extend(plan_movie(d))
    return plan


# ---------- 执行 ----------

def _is_busy(path: str) -> bool:
    try:
        with open(path, "rb"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def _move(src: str, dst: str, log: list[str]) -> tuple[int, int]:
    """返回 (moved, skipped)。"""
    if not os.path.exists(src):
        return 0, 0
    if os.path.exists(dst):
        log.append(f"SKIP 目标已存在: {dst}")
        return 0, 1
    if os.path.isdir(src):
        if _is_busy_dir(src):
            log.append(f"SKIP 目录被占用: {src}")
            return 0, 1
    elif _is_busy(src):
        log.append(f"SKIP 文件被占用: {src}")
        return 0, 1
    was_dir = os.path.isdir(src)
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        if not was_dir:
            parent = os.path.dirname(src)
            if parent and os.path.isdir(parent):
                try:
                    if not os.listdir(parent):
                        os.rmdir(parent)
                except OSError:
                    pass
        return 1, 0
    except Exception as e:
        log.append(f"FAIL {src}: {e}")
        return 0, 1


def _is_busy_dir(path: str) -> bool:
    try:
        os.rename(path, path)
        return False
    except OSError:
        return True


def apply_plan(plan: OrganizePlan, undo_path: str, dry_run: bool = False) -> list[str]:
    """执行整理，写撤销日志。顺序：移动/回收 -> 删空目录。"""
    log: list[str] = []
    undo_lines: list[str] = []
    moved = skipped = 0
    del_ops: list[MoveOp] = []
    for op in plan.ops:
        if op.kind == "empty_dir_del":
            del_ops.append(op)
            continue
        if dry_run:
            log.append(f"PLAN {op.label}")
            continue
        m, s = _move(op.source, op.target, log)
        moved += m
        skipped += s
        if m:
            undo_lines.append(f"mv\t{op.source}\t{op.target}")
    # 空目录删除
    for op in sorted(del_ops, key=lambda o: o.source.count(os.sep), reverse=True):
        if dry_run:
            log.append(f"PLAN {op.label}")
            continue
        try:
            if os.path.isdir(op.source) and not os.listdir(op.source):
                os.rmdir(op.source)
                undo_lines.append(f"del\t{op.source}\t")
                moved += 1
            else:
                skipped += 1
        except OSError as e:
            log.append(f"FAIL {op.label}: {e}")
            skipped += 1
    if undo_lines:
        with open(undo_path, "a", encoding="utf-8") as f:
            f.write("-- batch --\n" + "\n".join(undo_lines) + "\n")
    log.append(f"完成：整理 {moved}，跳过 {skipped}")
    return log


def undo_last(undo_path: str) -> list[str]:
    if not os.path.exists(undo_path):
        return ["没有撤销记录"]
    lines = [l for l in open(undo_path, encoding="utf-8").read().splitlines() if l]
    if not lines:
        return ["没有撤销记录"]
    try:
        mark = max(i for i, l in enumerate(lines) if l == "-- batch --")
    except ValueError:
        return ["撤销日志格式异常"]
    batch = lines[mark + 1 :]
    rest = lines[:mark]
    log: list[str] = []
    undone = 0
    failed = []
    for line in batch:
        parts = line.split("\t")
        if len(parts) == 3:
            op, source, target = parts
        elif len(parts) == 2:  # 兼容旧格式
            op, source, target = "mv", parts[0], parts[1]
        else:
            continue
        try:
            if op == "del":
                if not os.path.exists(source):
                    os.makedirs(source, exist_ok=True)
                    undone += 1
                else:
                    failed.append(line)
            else:
                if os.path.exists(target):
                    os.makedirs(os.path.dirname(source), exist_ok=True)
                    shutil.move(target, source)
                    undone += 1
                else:
                    failed.append(line)
        except Exception as e:
            failed.append(line)
            log.append(f"FAIL 撤销 {target or source}: {e}")
    with open(undo_path, "w", encoding="utf-8") as f:
        content = "\n".join(rest + failed)
        if content:
            f.write(content + "\n")
    log.append(f"撤销完成：{undone} 项")
    return log
