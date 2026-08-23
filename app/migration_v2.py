"""Additive MoviePoster V2 media-model migration.

This module deliberately does not remove or rewrite legacy ``files`` playback
columns.  It can be run repeatedly and is safe to call during Store startup.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


EPISODE_COLUMNS = {
    "item_id": "INTEGER NOT NULL DEFAULT 0",
    "season": "INTEGER NOT NULL DEFAULT 0",
    "episode": "INTEGER NOT NULL DEFAULT 0",
    "episode_title": "TEXT",
    "overview": "TEXT",
    "air_date": "TEXT",
    "tmdb_episode_id": "TEXT",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if column not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def migrate_v2(conn: sqlite3.Connection) -> dict[str, int]:
    """Apply the V2 data-layer migration and return before/after counts."""
    conn.execute("PRAGMA foreign_keys=ON")
    _add_column(conn, "people", "tmdb_person_id", "TEXT")
    before = {
        "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "paths": conn.execute("SELECT COUNT(DISTINCT path) FROM files").fetchone()[0],
    }
    conn.execute("BEGIN")
    try:
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
        for name, definition in EPISODE_COLUMNS.items():
            _add_column(conn, "episodes", name, definition)

        conn.execute(
            """CREATE TABLE IF NOT EXISTS playback(
                id INTEGER PRIMARY KEY,
                file_id INTEGER NOT NULL UNIQUE,
                progress REAL DEFAULT 0,
                duration REAL DEFAULT 0,
                watched INTEGER DEFAULT 0,
                playback_state TEXT DEFAULT 'never',
                last_played_at TEXT,
                play_count INTEGER DEFAULT 0,
                updated_at TEXT,
                FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
            )"""
        )
        _add_column(conn, "files", "episode_id", "INTEGER")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_item ON episodes(item_id, season, episode)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_episodes_tmdb ON episodes(tmdb_episode_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_files_episode ON files(episode_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_playback_file ON playback(file_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_playback_recent ON playback(last_played_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_playback_state ON playback(playback_state, progress)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_people_tmdb ON people(tmdb_person_id)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS images(
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
            )"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_images_best ON images(item_id, type, status, priority)")

        # Link existing files to episode rows where metadata already exists.
        conn.execute(
            """UPDATE files
               SET episode_id=(
                 SELECT e.id FROM episodes e
                 WHERE e.item_id=files.item_id
                   AND e.season=files.season
                   AND e.episode=files.episode
                 LIMIT 1
               )
               WHERE episode IS NOT NULL"""
        )

        # Backfill the normalized playback table without touching legacy fields.
        conn.execute(
            """INSERT OR IGNORE INTO playback(
                 file_id, progress, duration, watched, playback_state,
                 last_played_at, play_count, updated_at
               )
               SELECT id, COALESCE(progress, 0), COALESCE(duration, 0),
                      COALESCE(watched, 0), COALESCE(playback_state, 'never'),
                      last_played_at, COALESCE(play_count, 0), updated_at
               FROM files"""
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    after = {
        "items": conn.execute("SELECT COUNT(*) FROM items").fetchone()[0],
        "files": conn.execute("SELECT COUNT(*) FROM files").fetchone()[0],
        "paths": conn.execute("SELECT COUNT(DISTINCT path) FROM files").fetchone()[0],
        "episodes": conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0],
        "playback": conn.execute("SELECT COUNT(*) FROM playback").fetchone()[0],
        "linked_files": conn.execute("SELECT COUNT(*) FROM files WHERE episode_id IS NOT NULL").fetchone()[0],
    }
    return {f"before_{k}": v for k, v in before.items()} | {f"after_{k}": v for k, v in after.items()}


def migrate_path(db_path: str | Path) -> dict[str, int]:
    conn = sqlite3.connect(str(db_path))
    try:
        return migrate_v2(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MoviePoster V2 database migration")
    parser.add_argument("db", type=Path, help="path to library.db")
    args = parser.parse_args()
    print(migrate_path(args.db))
