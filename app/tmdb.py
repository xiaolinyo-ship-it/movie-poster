"""Optional TMDB metadata supplement.

TMDB is deliberately additive: callers decide which fields may fill gaps, while
the existing Douban title, score and summary remain authoritative.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


class TmdbClient:
    API = "https://api.themoviedb.org/3"
    IMAGE = "https://image.tmdb.org/t/p/w1280"

    def __init__(self, cache_dir: str | Path, api_key: str = ""):
        self.cache_dir = Path(cache_dir)
        self.api_key = (api_key or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def find_media_id(self, kind: str, *queries: str, year: str | None = None) -> str | None:
        """Find only a TMDB movie/TV ID, with optional year narrowing."""
        if not self.enabled:
            return None
        seen = set()
        for raw in queries:
            query = re.sub(r"[._-]+", " ", str(raw or "")).strip()
            if not query or query.casefold() in seen:
                continue
            seen.add(query.casefold())
            params = {"query": query, "include_adult": "false"}
            if year and str(year).isdigit():
                params["first_air_date_year" if kind == "tv" else "year"] = str(year)
            endpoint = "/search/tv" if kind == "tv" else "/search/movie"
            results = self._get(endpoint, params).get("results", [])
            if results:
                value = results[0].get("id")
                return str(value) if value else None
        return None

    def find_tv_id(self, *queries: str, year: str | None = None) -> str | None:
        return self.find_media_id("tv", *queries, year=year)

    def _get(self, path: str, params: dict) -> dict:
        query = {"api_key": self.api_key, "language": "zh-CN", **params}
        url = f"{self.API}{path}?{urllib.parse.urlencode(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "MoviePoster/2.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def fetch_item_meta(self, title: str, kind: str) -> dict:
        if not self.enabled:
            return {}
        query = re.sub(r"[._-]+", " ", title).strip()
        endpoint = "/search/tv" if kind == "tv" else "/search/movie"
        results = self._get(endpoint, {"query": query, "include_adult": "false"}).get("results", [])
        if not results:
            return {}
        result = results[0]
        tmdb_id = result.get("id")
        detail_endpoint = f"/tv/{tmdb_id}" if kind == "tv" else f"/movie/{tmdb_id}"
        detail = self._get(detail_endpoint, {"append_to_response": "credits"})
        credits = detail.get("credits") or {}
        directors = [p.get("name") for p in credits.get("crew", []) if p.get("job") == "Director"]
        actors = [
            {"name": p.get("name"), "character": p.get("character")}
            for p in credits.get("cast", [])[:20] if p.get("name")
        ]
        genres = [g.get("name") for g in detail.get("genres", []) if g.get("name")]
        countries = [
            x.get("name") for x in (detail.get("production_countries") or []) if x.get("name")
        ]
        release = detail.get("first_air_date") if kind == "tv" else detail.get("release_date")
        return {
            "tmdb_id": str(tmdb_id) if tmdb_id else None,
            "original_title": detail.get("original_name") or detail.get("original_title") or "",
            "backdrop_url": f"{self.IMAGE}{detail['backdrop_path']}" if detail.get("backdrop_path") else "",
            "genres": genres,
            "countries": countries,
            "directors": directors,
            "actors": actors,
            "runtime_minutes": detail.get("runtime") or ((detail.get("episode_run_time") or [None])[0]),
            "year": (release or "")[:4] or None,
        }

    def fetch_tv_episode(self, tmdb_id: str, season: int, episode: int) -> dict:
        """Fetch one TV episode's display metadata from TMDB."""
        if not self.enabled or not tmdb_id:
            return {}
        data = self._get(
            f"/tv/{urllib.parse.quote(str(tmdb_id))}/season/{int(season)}/episode/{int(episode)}",
            {},
        )
        return {
            "episode_title": data.get("name") or "",
            "overview": data.get("overview") or "",
            "air_date": data.get("air_date") or "",
            "tmdb_episode_id": str(data.get("id")) if data.get("id") else "",
        }

    def fetch_item_relations(self, tmdb_id: str, kind: str) -> dict:
        """Fetch only people and genre relations for an existing TMDB item."""
        if not self.enabled or not tmdb_id:
            return {}
        endpoint = f"/{'tv' if kind == 'tv' else 'movie'}/{urllib.parse.quote(str(tmdb_id))}"
        detail = self._get(endpoint, {"append_to_response": "credits"})
        credits = detail.get("credits") or {}
        directors = [
            {"name": p.get("name"), "tmdb_person_id": str(p.get("id"))}
            for p in credits.get("crew", [])
            if p.get("job") == "Director" and p.get("name")
        ]
        actors = [
            {"name": p.get("name"), "tmdb_person_id": str(p.get("id"))}
            for p in credits.get("cast", [])[:30]
            if p.get("name")
        ]
        genres = [g.get("name") for g in detail.get("genres", []) if g.get("name")]
        return {"directors": directors, "actors": actors, "genres": genres}

    def download_backdrop(self, url: str, tmdb_id: str) -> Path | None:
        if not url or not tmdb_id:
            return None
        dest_dir = self.cache_dir / "backdrops"
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^\w.-]", "_", str(tmdb_id)) or "backdrop"
        dest = dest_dir / f"{safe}.jpg"
        if dest.exists() and dest.stat().st_size > 5000:
            return dest
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MoviePoster/2.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) < 5000:
                return None
            dest.write_bytes(data)
            return dest
        except Exception:
            return None
