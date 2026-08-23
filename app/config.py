"""配置读写。"""

from __future__ import annotations

import json
from pathlib import Path


DEFAULT_CONFIG = {
    "tv_root": r"\\example-nas\tv",
    "movie_root": r"\\example-nas\video",
    "potplayer": r"C:\Program Files\DAUM\PotPlayer\PotPlayerMini64.exe",
    "douban_enabled": True,
    "tmdb_api_key": "",
    "request_delay": 0.8,
    "theme": "dark",
}


class Config:
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
        self.data_dir = self.base_dir / "data"
        self.cache_dir = self.data_dir / "cache"
        self.poster_dir = self.cache_dir / "posters"
        self.trash_dir = self.data_dir / "trash"
        self.db_path = self.data_dir / "library.db"
        self.config_path = self.base_dir / "config.json"
        self.undo_path = self.data_dir / "undo.log"
        for d in (self.data_dir, self.cache_dir, self.poster_dir, self.trash_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.values = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        if self.config_path.exists():
            try:
                data = json.loads(self.config_path.read_text(encoding="utf-8"))
                self.values.update(data)
            except Exception:
                pass

    def save(self) -> None:
        self.config_path.write_text(
            json.dumps(self.values, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get(self, key: str, default=None):
        return self.values.get(key, default)

    def set(self, key: str, value) -> None:
        self.values[key] = value
        self.save()
