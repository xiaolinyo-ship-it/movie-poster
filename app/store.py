"""SQLite 持久化：媒体条目、文件、播放进度。"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from .migration_v2 import migrate_v2


SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  douban_id TEXT,
  douban_title TEXT,
  rating REAL,
  votes INTEGER,
  year TEXT,
  summary TEXT,
  poster TEXT,
  original_title TEXT,
  backdrop TEXT,
  first_seen_at TEXT,
  metadata_status TEXT DEFAULT 'pending',
  runtime_minutes INTEGER,
  tmdb_id TEXT,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS files(
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  path TEXT NOT NULL UNIQUE,
  filename TEXT NOT NULL,
  season INTEGER DEFAULT 0,
  episode INTEGER,
  duration REAL DEFAULT 0,
  progress REAL DEFAULT 0,
  watched INTEGER DEFAULT 0,
  last_played_at TEXT,
  play_count INTEGER DEFAULT 0,
  playback_state TEXT DEFAULT 'never',
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_item ON files(item_id);
CREATE INDEX IF NOT EXISTS idx_items_kind ON items(kind);
CREATE TABLE IF NOT EXISTS episodes(
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  season INTEGER NOT NULL,
  episode INTEGER NOT NULL,
  episode_title TEXT,
  overview TEXT,
  air_date TEXT,
  tmdb_episode_id TEXT,
  UNIQUE(item_id, season, episode),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_episodes_item ON episodes(item_id, season, episode);
CREATE TABLE IF NOT EXISTS favorites(
  item_id INTEGER PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS genres(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS item_genres(
  item_id INTEGER NOT NULL,
  genre_id INTEGER NOT NULL,
  PRIMARY KEY(item_id, genre_id),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY(genre_id) REFERENCES genres(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS people(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL UNIQUE,
  tmdb_person_id TEXT
);
CREATE TABLE IF NOT EXISTS item_people(
  item_id INTEGER NOT NULL,
  person_id INTEGER NOT NULL,
  role TEXT NOT NULL,
  character TEXT,
  PRIMARY KEY(item_id, person_id, role),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS countries(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS item_countries(
  item_id INTEGER NOT NULL,
  country_id INTEGER NOT NULL,
  PRIMARY KEY(item_id, country_id),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
  FOREIGN KEY(country_id) REFERENCES countries(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS images(
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  type TEXT NOT NULL,
  source TEXT NOT NULL,
  url TEXT,
  local_path TEXT,
  priority INTEGER DEFAULT 0,
  status TEXT DEFAULT 'pending',
  created_at TEXT NOT NULL,
  UNIQUE(item_id, type, source, url),
  FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_images_best ON images(item_id, type, status, priority);
"""


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column_if_missing(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_schema(conn: sqlite3.Connection) -> None:
    """Apply the additive V2 P1 migration without removing or rewriting old data."""
    # SCHEMA creates these columns for new installations; these checks handle old DBs.
    _add_column_if_missing(conn, "items", "original_title", "TEXT")
    _add_column_if_missing(conn, "items", "backdrop", "TEXT")
    _add_column_if_missing(conn, "items", "first_seen_at", "TEXT")
    _add_column_if_missing(conn, "items", "metadata_status", "TEXT DEFAULT 'pending'")
    _add_column_if_missing(conn, "items", "runtime_minutes", "INTEGER")
    _add_column_if_missing(conn, "items", "tmdb_id", "TEXT")
    _add_column_if_missing(conn, "files", "last_played_at", "TEXT")
    _add_column_if_missing(conn, "files", "play_count", "INTEGER DEFAULT 0")
    _add_column_if_missing(conn, "files", "playback_state", "TEXT DEFAULT 'never'")
    conn.execute(
        """CREATE TABLE IF NOT EXISTS favorites(
            item_id INTEGER PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )"""
    )
    conn.execute(
        """CREATE TABLE IF NOT EXISTS episodes(
            id INTEGER PRIMARY KEY,
            item_id INTEGER NOT NULL,
            season INTEGER NOT NULL,
            episode INTEGER NOT NULL,
            episode_title TEXT,
            overview TEXT,
            air_date TEXT,
            tmdb_episode_id TEXT,
            UNIQUE(item_id, season, episode),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_item ON episodes(item_id, season, episode)")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS genres(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS item_genres(
            item_id INTEGER NOT NULL, genre_id INTEGER NOT NULL,
            PRIMARY KEY(item_id, genre_id),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY(genre_id) REFERENCES genres(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS people(
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            normalized_name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS item_people(
            item_id INTEGER NOT NULL, person_id INTEGER NOT NULL,
            role TEXT NOT NULL, character TEXT,
            PRIMARY KEY(item_id, person_id, role),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY(person_id) REFERENCES people(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS countries(id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS item_countries(
            item_id INTEGER NOT NULL, country_id INTEGER NOT NULL,
            PRIMARY KEY(item_id, country_id),
            FOREIGN KEY(item_id) REFERENCES items(id) ON DELETE CASCADE,
            FOREIGN KEY(country_id) REFERENCES countries(id) ON DELETE CASCADE
        );
        """
    )
    # Existing entries predate first_seen_at. The old updated_at is the only safe
    # historical timestamp available, so use it as a non-destructive approximation.
    conn.execute(
        "UPDATE items SET first_seen_at=updated_at WHERE first_seen_at IS NULL AND updated_at IS NOT NULL"
    )
    conn.execute("UPDATE files SET play_count=0 WHERE play_count IS NULL")
    conn.execute("UPDATE files SET playback_state='never' WHERE playback_state IS NULL")
    conn.commit()


class Store:
    def __init__(self, db_path: str):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        migrate_schema(self.conn)
        migrate_v2(self.conn)

    def close(self):
        self.conn.close()

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec="seconds")

    # ---- items ----
    def upsert_item(self, kind: str, title: str, path: str) -> int:
        now = self._now()
        row = self.conn.execute("SELECT id FROM items WHERE path=?", (path,)).fetchone()
        if row:
            self.conn.execute(
                "UPDATE items SET kind=?, title=?, updated_at=? WHERE id=?",
                (kind, title, now, row["id"]),
            )
            self.conn.commit()
            return row["id"]
        cur = self.conn.execute(
            "INSERT INTO items(kind,title,path,first_seen_at,metadata_status,updated_at) VALUES(?,?,?,?,?,?)",
            (kind, title, path, now, "pending", now),
        )
        self.conn.commit()
        return cur.lastrowid

    def get_item_by_path(self, path: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM items WHERE path=?", (path,)).fetchone()

    def get_item(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()

    # ---- images ----
    def upsert_image(self, item_id: int, image_type: str, source: str, url: str = "",
                     local_path: str = "", priority: int = 0, status: str = "pending") -> int:
        now = self._now()
        row = self.conn.execute(
            "SELECT id FROM images WHERE item_id=? AND type=? AND source=? AND COALESCE(url,'')=?",
            (item_id, image_type, source, url or ""),
        ).fetchone()
        if row:
            self.conn.execute(
                "UPDATE images SET local_path=?, priority=?, status=? WHERE id=?",
                (local_path or None, int(priority), status, row[0]),
            )
            image_id = row[0]
        else:
            cur = self.conn.execute(
                "INSERT INTO images(item_id,type,source,url,local_path,priority,status,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (item_id, image_type, source, url or None, local_path or None, int(priority), status, now),
            )
            image_id = cur.lastrowid
        self.conn.commit()
        return int(image_id)

    def list_images(self, item_id: int, image_type: str | None = None) -> list[sqlite3.Row]:
        if image_type:
            return self.conn.execute(
                "SELECT * FROM images WHERE item_id=? AND type=? ORDER BY priority DESC, id DESC",
                (item_id, image_type),
            ).fetchall()
        return self.conn.execute("SELECT * FROM images WHERE item_id=? ORDER BY type, priority DESC", (item_id,)).fetchall()

    def get_best_image(self, item_id: int, image_type: str, downloaded_only: bool = True) -> sqlite3.Row | None:
        sql = "SELECT * FROM images WHERE item_id=? AND type=?"
        params: list[object] = [item_id, image_type]
        if downloaded_only:
            sql += " AND status='downloaded' AND local_path IS NOT NULL"
        sql += " ORDER BY priority DESC, id DESC LIMIT 1"
        return self.conn.execute(sql, params).fetchone()

    def list_items(self, kind: str | None = None) -> list[sqlite3.Row]:
        if kind:
            return self.conn.execute("SELECT * FROM items WHERE kind=? ORDER BY title", (kind,)).fetchall()
        return self.conn.execute("SELECT * FROM items ORDER BY kind, title").fetchall()

    def search_all(self, keyword: str) -> list[sqlite3.Row]:
        """Search media and related people/genres with relevance weights."""
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        pattern = f"%{keyword}%"
        return self.conn.execute(
            """SELECT i.*,
                      COUNT(DISTINCT CASE WHEN f.episode IS NOT NULL THEN f.id END) AS episode_count,
                      CASE
                        WHEN i.title = ? THEN 100
                        WHEN i.title LIKE ? COLLATE NOCASE THEN 90
                        WHEN i.douban_title LIKE ? COLLATE NOCASE THEN 85
                        WHEN i.original_title LIKE ? COLLATE NOCASE THEN 80
                        WHEN EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                                     WHERE ip.item_id=i.id AND ip.role='actor' AND p.name LIKE ? COLLATE NOCASE) THEN 60
                        WHEN EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                                     WHERE ip.item_id=i.id AND ip.role='director' AND p.name LIKE ? COLLATE NOCASE) THEN 50
                        WHEN EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                                     WHERE ip.item_id=i.id AND ip.role NOT IN ('actor','director') AND p.name LIKE ? COLLATE NOCASE) THEN 40
                        WHEN EXISTS (SELECT 1 FROM item_genres ig JOIN genres g ON g.id=ig.genre_id
                                     WHERE ig.item_id=i.id AND g.name LIKE ? COLLATE NOCASE) THEN 40
                        WHEN EXISTS (SELECT 1 FROM files fx WHERE fx.item_id=i.id AND fx.filename LIKE ? COLLATE NOCASE) THEN 10
                        WHEN EXISTS (SELECT 1 FROM files fx WHERE fx.item_id=i.id AND fx.path LIKE ? COLLATE NOCASE) THEN 5
                        ELSE 0 END AS score,
                      CASE
                        WHEN i.title = ? THEN '标题:' || i.title
                        WHEN i.title LIKE ? COLLATE NOCASE THEN '标题:' || i.title
                        WHEN i.douban_title LIKE ? COLLATE NOCASE THEN '豆瓣标题:' || i.douban_title
                        WHEN i.original_title LIKE ? COLLATE NOCASE THEN '原名:' || i.original_title
                        WHEN EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                                     WHERE ip.item_id=i.id AND ip.role='actor' AND p.name LIKE ? COLLATE NOCASE)
                          THEN '演员:' || (SELECT p.name FROM item_people ip JOIN people p ON p.id=ip.person_id
                                           WHERE ip.item_id=i.id AND ip.role='actor' AND p.name LIKE ? COLLATE NOCASE LIMIT 1)
                        WHEN EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                                     WHERE ip.item_id=i.id AND ip.role='director' AND p.name LIKE ? COLLATE NOCASE)
                          THEN '导演:' || (SELECT p.name FROM item_people ip JOIN people p ON p.id=ip.person_id
                                           WHERE ip.item_id=i.id AND ip.role='director' AND p.name LIKE ? COLLATE NOCASE LIMIT 1)
                        WHEN EXISTS (SELECT 1 FROM item_genres ig JOIN genres g ON g.id=ig.genre_id
                                     WHERE ig.item_id=i.id AND g.name LIKE ? COLLATE NOCASE)
                          THEN '类型:' || (SELECT g.name FROM item_genres ig JOIN genres g ON g.id=ig.genre_id
                                           WHERE ig.item_id=i.id AND g.name LIKE ? COLLATE NOCASE LIMIT 1)
                        WHEN EXISTS (SELECT 1 FROM files fx WHERE fx.item_id=i.id AND fx.filename LIKE ? COLLATE NOCASE) THEN '文件名'
                        WHEN EXISTS (SELECT 1 FROM files fx WHERE fx.item_id=i.id AND fx.path LIKE ? COLLATE NOCASE) THEN '路径'
                        ELSE '关联媒体' END AS matched_by
               FROM items i
               LEFT JOIN files f ON f.item_id=i.id
               WHERE i.title LIKE ? COLLATE NOCASE
                  OR i.douban_title LIKE ? COLLATE NOCASE
                  OR i.original_title LIKE ? COLLATE NOCASE
                  OR EXISTS (SELECT 1 FROM item_people ip JOIN people p ON p.id=ip.person_id
                             WHERE ip.item_id=i.id AND p.name LIKE ? COLLATE NOCASE)
                  OR EXISTS (SELECT 1 FROM item_genres ig JOIN genres g ON g.id=ig.genre_id
                             WHERE ig.item_id=i.id AND g.name LIKE ? COLLATE NOCASE)
                  OR EXISTS (SELECT 1 FROM files fx WHERE fx.item_id=i.id AND (fx.filename LIKE ? COLLATE NOCASE OR fx.path LIKE ? COLLATE NOCASE))
               GROUP BY i.id
               ORDER BY score DESC, CASE WHEN i.kind='tv' THEN 0 ELSE 1 END, i.title""",
            [keyword] + [pattern] * 9 + [keyword] + [pattern] * 11 + [pattern] * 7,
        ).fetchall()

    def search_suggestions(self, keyword: str, limit: int = 8) -> list[str]:
        """Return distinct title-like suggestions for the search completer."""
        keyword = (keyword or "").strip()
        if not keyword:
            return []
        pattern = f"%{keyword}%"
        rows = self.conn.execute(
            """SELECT value, MAX(score) AS rank FROM (
                 SELECT title AS value,
                   CASE WHEN title=? THEN 100 WHEN title LIKE ? COLLATE NOCASE THEN 90 ELSE 0 END AS score
                 FROM items WHERE title LIKE ? COLLATE NOCASE
                 UNION ALL
                 SELECT douban_title AS value,
                   CASE WHEN douban_title=? THEN 80 WHEN douban_title LIKE ? COLLATE NOCASE THEN 80 ELSE 0 END
                 FROM items WHERE douban_title IS NOT NULL AND douban_title LIKE ? COLLATE NOCASE
                 UNION ALL
                 SELECT original_title AS value,
                   CASE WHEN original_title=? THEN 70 WHEN original_title LIKE ? COLLATE NOCASE THEN 70 ELSE 0 END
                 FROM items WHERE original_title IS NOT NULL AND original_title LIKE ? COLLATE NOCASE
               ) WHERE value IS NOT NULL AND value!=''
               GROUP BY value ORDER BY rank DESC, value LIMIT ?""",
            (keyword, pattern, pattern, keyword, pattern, pattern, keyword, pattern, pattern, int(limit)),
        ).fetchall()
        return [str(row["value"]) for row in rows]

    def update_meta(self, item_id: int, **fields) -> None:
        if not fields:
            return
        fields["updated_at"] = self._now()
        keys = ", ".join(f"{k}=?" for k in fields)
        self.conn.execute(f"UPDATE items SET {keys} WHERE id=?", (*fields.values(), item_id))
        self.conn.commit()

    def replace_item_metadata(
        self,
        item_id: int,
        genres: list[str] | None = None,
        countries: list[str] | None = None,
        directors: list[str] | None = None,
        actors: list[dict | str] | None = None,
    ) -> None:
        """Replace normalized multi-value metadata for one item."""
        def clean(value: str) -> str:
            return " ".join(str(value).strip().split())

        if genres is not None:
            self.conn.execute("DELETE FROM item_genres WHERE item_id=?", (item_id,))
            for name in dict.fromkeys(clean(x) for x in genres if clean(x)):
                self.conn.execute("INSERT OR IGNORE INTO genres(name) VALUES(?)", (name,))
                gid = self.conn.execute("SELECT id FROM genres WHERE name=?", (name,)).fetchone()[0]
                self.conn.execute("INSERT OR IGNORE INTO item_genres(item_id,genre_id) VALUES(?,?)", (item_id, gid))
        if countries is not None:
            self.conn.execute("DELETE FROM item_countries WHERE item_id=?", (item_id,))
            for name in dict.fromkeys(clean(x) for x in countries if clean(x)):
                self.conn.execute("INSERT OR IGNORE INTO countries(name) VALUES(?)", (name,))
                cid = self.conn.execute("SELECT id FROM countries WHERE name=?", (name,)).fetchone()[0]
                self.conn.execute("INSERT OR IGNORE INTO item_countries(item_id,country_id) VALUES(?,?)", (item_id, cid))
        if directors is not None or actors is not None:
            self.conn.execute("DELETE FROM item_people WHERE item_id=?", (item_id,))
            for name in directors or []:
                value = clean(name)
                if value:
                    self.conn.execute("INSERT OR IGNORE INTO people(name,normalized_name) VALUES(?,?)", (value, value.casefold()))
                    pid = self.conn.execute("SELECT id FROM people WHERE normalized_name=?", (value.casefold(),)).fetchone()[0]
                    self.conn.execute("INSERT OR IGNORE INTO item_people(item_id,person_id,role) VALUES(?,?,?)", (item_id, pid, "director"))
            for actor in actors or []:
                if isinstance(actor, dict):
                    value = clean(actor.get("name", ""))
                    character = clean(actor.get("character", "")) or None
                else:
                    value, character = clean(actor), None
                if value:
                    self.conn.execute("INSERT OR IGNORE INTO people(name,normalized_name) VALUES(?,?)", (value, value.casefold()))
                    pid = self.conn.execute("SELECT id FROM people WHERE normalized_name=?", (value.casefold(),)).fetchone()[0]
                    self.conn.execute("INSERT OR IGNORE INTO item_people(item_id,person_id,role,character) VALUES(?,?,?,?)", (item_id, pid, "actor", character))
        self.conn.commit()

    def replace_item_relations(self, item_id: int, genres: list[str], directors: list[dict], actors: list[dict]) -> None:
        """Persist TMDB people/genre relations without touching item metadata."""
        def clean(value) -> str:
            return " ".join(str(value or "").strip().split())

        self.conn.execute("DELETE FROM item_genres WHERE item_id=?", (item_id,))
        for name in dict.fromkeys(clean(x) for x in genres if clean(x)):
            self.conn.execute("INSERT OR IGNORE INTO genres(name) VALUES(?)", (name,))
            gid = self.conn.execute("SELECT id FROM genres WHERE name=?", (name,)).fetchone()[0]
            self.conn.execute("INSERT OR IGNORE INTO item_genres(item_id,genre_id) VALUES(?,?)", (item_id, gid))

        self.conn.execute("DELETE FROM item_people WHERE item_id=?", (item_id,))
        for role, values in (("director", directors), ("actor", actors)):
            for person in values or []:
                person = person if isinstance(person, dict) else {"name": person}
                name = clean(person.get("name"))
                if not name:
                    continue
                normalized = name.casefold()
                tmdb_id = str(person.get("tmdb_person_id") or "") or None
                existing = self.conn.execute(
                    "SELECT id FROM people WHERE normalized_name=?", (normalized,)
                ).fetchone()
                if existing:
                    pid = existing[0]
                    if tmdb_id:
                        self.conn.execute("UPDATE people SET tmdb_person_id=? WHERE id=?", (tmdb_id, pid))
                else:
                    cur = self.conn.execute(
                        "INSERT INTO people(name,normalized_name,tmdb_person_id) VALUES(?,?,?)",
                        (name, normalized, tmdb_id),
                    )
                    pid = cur.lastrowid
                self.conn.execute(
                    "INSERT OR IGNORE INTO item_people(item_id,person_id,role) VALUES(?,?,?)",
                    (item_id, pid, role),
                )
        self.conn.commit()

    def get_item_metadata(self, item_id: int) -> dict:
        genres = [r[0] for r in self.conn.execute("SELECT g.name FROM genres g JOIN item_genres x ON x.genre_id=g.id WHERE x.item_id=? ORDER BY g.name", (item_id,))]
        countries = [r[0] for r in self.conn.execute("SELECT c.name FROM countries c JOIN item_countries x ON x.country_id=c.id WHERE x.item_id=? ORDER BY c.name", (item_id,))]
        people = self.conn.execute("SELECT p.name, x.role, x.character FROM people p JOIN item_people x ON x.person_id=p.id WHERE x.item_id=? ORDER BY CASE x.role WHEN 'director' THEN 0 ELSE 1 END, p.name", (item_id,)).fetchall()
        return {
            "genres": genres,
            "countries": countries,
            "directors": [r[0] for r in people if r[1] == "director"],
            "actors": [{"name": r[0], "character": r[2]} for r in people if r[1] == "actor"],
        }

    # ---- files ----
    def replace_files(self, item_id: int, paths: list[str], filenames: list[str],
                      seasons: list[int], episodes: list[int | None]) -> None:
        now = self._now()
        existing = {r["path"] for r in self.conn.execute("SELECT path FROM files WHERE item_id=?", (item_id,))}
        keep = set()
        for p, fn, s, e in zip(paths, filenames, seasons, episodes):
            keep.add(p)
            row = self.conn.execute("SELECT id FROM files WHERE path=?", (p,)).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE files SET filename=?, season=?, episode=?, updated_at=? WHERE id=?",
                    (fn, s, e, now, row["id"]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO files(item_id,path,filename,season,episode,updated_at) VALUES(?,?,?,?,?,?)",
                    (item_id, p, fn, s, e, now),
                )
        for p in existing - keep:
            self.conn.execute("DELETE FROM files WHERE path=?", (p,))
        self.conn.execute(
            """INSERT OR IGNORE INTO playback(file_id, progress, duration, watched, playback_state, play_count, updated_at)
               SELECT id, COALESCE(progress,0), COALESCE(duration,0), COALESCE(watched,0),
                      COALESCE(playback_state,'never'), COALESCE(play_count,0), updated_at
               FROM files WHERE item_id=?""", (item_id,)
        )
        self.conn.commit()

    def list_files(self, item_id: int) -> list[sqlite3.Row]:
        return self.conn.execute(
            """SELECT f.*, e.episode_title, e.overview, e.air_date,
                      COALESCE(p.progress, f.progress, 0) AS progress,
                      COALESCE(p.duration, f.duration, 0) AS duration,
                      COALESCE(p.watched, f.watched, 0) AS watched,
                      COALESCE(p.playback_state, f.playback_state, 'never') AS playback_state
               FROM files f
               LEFT JOIN episodes e ON e.id=f.episode_id
               LEFT JOIN playback p ON p.file_id=f.id
               WHERE f.item_id=? ORDER BY f.season, f.episode, f.filename""", (item_id,)
        ).fetchall()

    def upsert_episode(
        self, item_id: int, season: int, episode: int,
        episode_title: str = "", overview: str = "",
        air_date: str = "", tmdb_episode_id: str = "",
    ) -> None:
        self.conn.execute(
            """INSERT INTO episodes(item_id,season,episode,episode_title,overview,air_date,tmdb_episode_id)
               VALUES(?,?,?,?,?,?,?)
               ON CONFLICT(item_id,season,episode) DO UPDATE SET
                 episode_title=excluded.episode_title,
                 overview=excluded.overview,
                 air_date=excluded.air_date,
                 tmdb_episode_id=excluded.tmdb_episode_id""",
            (item_id, int(season), int(episode), episode_title or None,
             overview or None, air_date or None, tmdb_episode_id or None),
        )
        episode_row = self.conn.execute(
            "SELECT id FROM episodes WHERE item_id=? AND season=? AND episode=?",
            (item_id, int(season), int(episode)),
        ).fetchone()
        if episode_row:
            self.conn.execute(
                "UPDATE files SET episode_id=? WHERE item_id=? AND season=? AND episode=?",
                (episode_row["id"], item_id, int(season), int(episode)),
            )
        self.conn.commit()

    def get_episode_for_file(self, item_id: int, season: int, episode: int) -> sqlite3.Row | None:
        """Return the episode metadata joined to its media file coordinates."""
        return self.conn.execute(
            """SELECT f.item_id, f.path, f.filename, f.season, f.episode,
                      e.episode_title, e.overview, e.air_date, e.tmdb_episode_id
               FROM files f
               LEFT JOIN episodes e
                 ON e.item_id=f.item_id AND e.season=f.season AND e.episode=f.episode
               WHERE f.item_id=? AND f.season=? AND f.episode=?
               ORDER BY f.id LIMIT 1""",
            (item_id, int(season), int(episode)),
        ).fetchone()

    def get_file(self, path: str) -> sqlite3.Row | None:
        return self.conn.execute(
            """SELECT f.*, COALESCE(p.progress, f.progress, 0) AS progress,
                      COALESCE(p.duration, f.duration, 0) AS duration,
                      COALESCE(p.watched, f.watched, 0) AS watched,
                      COALESCE(p.playback_state, f.playback_state, 'never') AS playback_state
               FROM files f LEFT JOIN playback p ON p.file_id=f.id WHERE f.path=?""", (path,)
        ).fetchone()

    def set_progress(self, path: str, progress: float, duration: float = 0) -> None:
        self.conn.execute(
            "UPDATE files SET progress=?, duration=?, updated_at=? WHERE path=?",
            (progress, duration, self._now(), path),
        )
        self.conn.commit()

    def update_play_state(
        self,
        path: str,
        state: str,
        progress: float | None = None,
        duration: float | None = None,
    ) -> None:
        """Update file playback state without changing the external player flow."""
        allowed = {"never", "in_progress", "finished"}
        if state not in allowed:
            raise ValueError(f"invalid playback state: {state}")
        fields = ["playback_state=?", "updated_at=?"]
        values: list[object] = [state, self._now()]
        if progress is not None:
            fields.append("progress=?")
            values.append(float(progress))
        if duration is not None:
            fields.append("duration=?")
            values.append(float(duration))
        values.append(path)
        self.conn.execute(f"UPDATE files SET {', '.join(fields)} WHERE path=?", values)
        pb = self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if pb:
            pfields = ["playback_state=?", "updated_at=?"]
            pvalues: list[object] = [state, self._now()]
            if progress is not None:
                pfields.append("progress=?"); pvalues.append(float(progress))
            if duration is not None:
                pfields.append("duration=?"); pvalues.append(float(duration))
            pvalues.append(pb[0])
            self.conn.execute(f"UPDATE playback SET {', '.join(pfields)} WHERE file_id=?", pvalues)
        self.conn.commit()

    def update_last_played(self, path: str, increment_play_count: bool = True) -> None:
        """Record a playback start/interaction for future recent-played channels."""
        now = self._now()
        if increment_play_count:
            self.conn.execute(
                "UPDATE files SET last_played_at=?, play_count=COALESCE(play_count, 0)+1, "
                "updated_at=? WHERE path=?",
                (now, now, path),
            )
        else:
            self.conn.execute(
                "UPDATE files SET last_played_at=?, updated_at=? WHERE path=?",
                (now, now, path),
            )
        row = self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if row:
            if increment_play_count:
                self.conn.execute(
                    "UPDATE playback SET last_played_at=?, play_count=COALESCE(play_count,0)+1, updated_at=? WHERE file_id=?",
                    (now, now, row[0]),
                )
            else:
                self.conn.execute("UPDATE playback SET last_played_at=?, updated_at=? WHERE file_id=?", (now, now, row[0]))
        self.conn.commit()

    def set_watched(self, path: str, watched: bool) -> None:
        self.conn.execute(
            "UPDATE files SET watched=?, updated_at=? WHERE path=?",
            (1 if watched else 0, self._now(), path),
        )
        row = self.conn.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
        if row:
            self.conn.execute("UPDATE playback SET watched=?, updated_at=? WHERE file_id=?", (1 if watched else 0, self._now(), row[0]))
        self.conn.commit()

    def delete_file_record(self, path: str) -> None:
        """Delete one file index record; playback cascades via file_id."""
        self.conn.execute("DELETE FROM files WHERE path=?", (path,))
        self.conn.commit()

    # ---- favorites ----
    def add_favorite(self, item_id: int) -> None:
        now = self._now()
        self.conn.execute(
            "INSERT INTO favorites(item_id, created_at, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(item_id) DO UPDATE SET updated_at=excluded.updated_at",
            (item_id, now, now),
        )
        self.conn.commit()

    def remove_favorite(self, item_id: int) -> None:
        self.conn.execute("DELETE FROM favorites WHERE item_id=?", (item_id,))
        self.conn.commit()

    def is_favorite(self, item_id: int) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM favorites WHERE item_id=?", (item_id,)
        ).fetchone() is not None

    def item_progress(self, item_id: int) -> tuple[int, int]:
        rows = self.conn.execute("SELECT watched, progress, duration FROM files WHERE item_id=?", (item_id,)).fetchall()
        total = len(rows)
        done = sum(1 for r in rows if r["watched"] or (r["duration"] and r["progress"] >= r["duration"] * 0.95))
        return done, total

    def continuing_items(self) -> list[tuple[sqlite3.Row, float]]:
        """有播放进度但未看完的条目，按最近更新排序。"""
        rows = self.conn.execute(
            "SELECT DISTINCT f.item_id, MAX(f.updated_at) AS last FROM files f "
            "WHERE (f.progress > 0 AND (f.duration = 0 OR f.progress < f.duration * 0.95)) OR f.watched = 1 "
            "GROUP BY f.item_id ORDER BY last DESC"
        ).fetchall()
        out = []
        for r in rows:
            item = self.get_item(r["item_id"])
            if item:
                done, total = self.item_progress(item["id"])
                out.append((item, done / total if total else 0))
        return out
