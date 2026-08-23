"""多来源图片登记、优先级选择与本地缓存。"""

from __future__ import annotations

import hashlib
import os
import urllib.request
from pathlib import Path


class ImageProviderManager:
    PRIORITY = {
        "tmdb": 100,
        "fanart": 90,
        "douban": 80,
        "imdb": 70,
        "local": 10,
    }

    def __init__(self, store, cache_dir: str | Path):
        self.store = store
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "images").mkdir(parents=True, exist_ok=True)

    def register(self, item_id: int, image_type: str, source: str, url: str = "",
                 local_path: str = "", priority: int | None = None, status: str = "pending") -> int:
        return self.store.upsert_image(item_id, image_type, source, url, local_path,
                                       priority if priority is not None else self.PRIORITY.get(source, 0), status)

    def best_local(self, item_id: int, image_type: str) -> str:
        row = self.store.get_best_image(item_id, image_type, downloaded_only=True)
        if row and row["local_path"] and os.path.exists(row["local_path"]):
            return row["local_path"]
        return ""

    def resolve(self, item: object, image_type: str) -> str:
        item_id = int(item["id"])
        path = self.best_local(item_id, image_type)
        if path:
            return path
        field = "poster" if image_type == "poster" else "backdrop"
        value = str(item[field] or "") if field in item.keys() else ""
        if value and os.path.exists(value):
            self.register(item_id, image_type, "tmdb" if image_type == "backdrop" else "douban",
                          local_path=value, status="downloaded")
            return value
        base = Path(str(item["path"] or "")) if "path" in item.keys() else Path()
        candidates = [base / ("poster.jpg" if image_type == "poster" else "backdrop.jpg"),
                      base / ("poster.png" if image_type == "poster" else "backdrop.png")]
        for candidate in candidates:
            if candidate.is_file():
                self.register(item_id, image_type, "local", local_path=str(candidate), status="downloaded")
                return str(candidate)
        return ""

    def download(self, item_id: int, image_type: str, source: str, url: str) -> str:
        """下载单张图片；失败只返回空字符串，不阻塞媒体展示。"""
        if not url:
            return ""
        suffix = ".jpg"
        target = self.cache_dir / "images" / f"{item_id}_{image_type}_{hashlib.sha1(url.encode()).hexdigest()[:12]}{suffix}"
        try:
            if not target.exists():
                urllib.request.urlretrieve(url, target)
            self.register(item_id, image_type, source, url, str(target), self.PRIORITY.get(source, 0), "downloaded")
            return str(target)
        except Exception:
            self.register(item_id, image_type, source, url, "", self.PRIORITY.get(source, 0), "failed")
            return ""
