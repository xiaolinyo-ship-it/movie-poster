"""豆瓣元数据抓取：搜索、详情（评分/简介）、海报缓存。"""

from __future__ import annotations

import json
import hashlib
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SUGGEST_URL = "https://movie.douban.com/j/subject_suggest?q={q}"
DETAIL_URL = "https://m.douban.com/rexxar/api/v2/subject/{sid}?ck="
SO360_URL = "https://www.so.com/s?q={q}"
MD_SEARCH_URL = "https://m.douban.com/search/?query={q}"
REXXAR_SEARCH_URL = "https://m.douban.com/rexxar/api/v2/search?q={q}&type=movie&start=0&count=8"

CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def clean_title(name: str) -> tuple[str, str | None]:
    """清洗目录名为可搜索标题，返回 (title, year)。"""
    t = (name or "").strip()
    if not t:
        return t, None
    year = None
    m = re.search(r"(19|20)\d{2}", t)
    if m:
        year = m.group(0)
    # 去掉字母排序前缀（A暗影蜘蛛侠 / H 黑豹2 / 1C冲突）
    t = re.sub(r"^[\d]*[A-Za-z]+\s*", "", t)
    # 去掉 [] 【】 里的杂质
    t = re.sub(r"[【\[][^】\]]*[】\]]", "", t)
    # 去掉 （国）（粤）等配音标记
    t = re.sub(r"（[^）]{1,4}）", "", t)
    # 取第一个连续中文段（含数字），如 重启人生.日语官中.Brush... -> 重启人生
    cjk = re.search(r"[\u4e00-\u9fff0-9]{2,}", t)
    if cjk:
        t = cjk.group(0)
    t = t.strip(" .-_")
    return t, year


def _title_ok(query: str, candidate: str) -> bool:
    if not candidate:
        return False
    q = re.sub(r"\s+", "", query.lower())
    c = re.sub(r"\s+", "", candidate.lower())
    if not q or not c:
        return False
    if q in c or c in q:
        return True
    # 中文双字前缀一致即可（阿凡达2 vs 阿凡达：水之道）
    cjk = re.findall(r"[\u4e00-\u9fff]", q)
    if len(cjk) >= 2 and "".join(cjk[:2]) in c:
        return True
    # 纯数字标题（1899）
    if q.isdigit() and q in c:
        return True
    return False


class DoubanClient:
    def __init__(self, cache_dir: Path, delay: float = 0.4):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "posters").mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self._last = 0.0
        self._cookie = None
        self._fail_streak = 0
        self._channel_streak = {"so360": 0, "m_douban": 0, "rexxar": 0}
        self._channel_cooldown: dict[str, float] = {}
        self._warm_cookie()

    def _channel_ok(self, name: str) -> bool:
        return time.time() >= self._channel_cooldown.get(name, 0)

    def _channel_result(self, name: str, ok: bool) -> None:
        if ok:
            self._channel_streak[name] = 0
        else:
            self._channel_streak[name] = self._channel_streak.get(name, 0) + 1
            if self._channel_streak[name] >= 3:
                self._channel_cooldown[name] = time.time() + 300
                self._channel_streak[name] = 0

    def _warm_cookie(self) -> None:
        """访问豆瓣首页拿 bid cookie，图片下载需要。"""
        try:
            req = urllib.request.Request(
                "https://movie.douban.com/",
                headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                resp.read()
                raw = resp.headers.get("Set-Cookie") or ""
                for part in raw.split(";"):
                    part = part.strip()
                    if part.startswith("bid="):
                        self._cookie = f"bid={part[4:]}"
        except Exception:
            self._cookie = None

    def _throttle(self) -> None:
        wait = self.delay - (time.time() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()

    def _get_json(self, url: str, referer: str | None = None, retries: int = 3) -> dict | list | None:
        headers = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
        if referer:
            headers["Referer"] = referer
        if self._fail_streak >= 5:
            # 触发限流冷却，暂停 10 秒
            time.sleep(10)
            self._fail_streak = 0
        for attempt in range(retries + 1):
            self._throttle()
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8", "ignore"))
                if isinstance(data, list) and not data:
                    raise ValueError("empty result")
                self._fail_streak = 0
                return data
            except Exception:
                self._fail_streak += 1
                if attempt < retries:
                    time.sleep(3 + attempt * 3)
        return None

    def suggest(self, query: str) -> list[dict]:
        key = hashlib.md5(query.encode("utf-8")).hexdigest()
        cache = self.cache_dir / f"suggest_{key}.json"
        if cache.exists():
            try:
                age = time.time() - cache.stat().st_mtime
                data = json.loads(cache.read_text(encoding="utf-8"))
                # 空结果缓存 5 分钟，正常结果永久缓存
                if data or age < 300:
                    return data
            except Exception:
                pass
        data = self._get_json(SUGGEST_URL.format(q=urllib.parse.quote(query)), retries=1)
        if data:
            cache.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        elif not cache.exists():
            # 缓存空结果 5 分钟，避免同一批次重复请求同一个标题
            cache.write_text("[]", encoding="utf-8")
            try:
                os.utime(cache, (time.time() + 300, time.time() + 300))
            except OSError:
                pass
        return data if isinstance(data, list) else []

    def _resolve_cache(self, query: str):
        """返回 sid / "NEGATIVE"（30 分钟内不重试）/ None（无缓存）。"""
        key = hashlib.md5(query.encode("utf-8")).hexdigest()
        p = self.cache_dir / f"resolve_{key}.json"
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("sid"):
                    return str(data["sid"])
                # 负缓存：30 分钟内不重复搜索
                if time.time() - p.stat().st_mtime < 1800:
                    return "NEGATIVE"
            except Exception:
                pass
        return None

    def _save_resolve(self, query: str, sid: str | None) -> None:
        key = hashlib.md5(query.encode("utf-8")).hexdigest()
        p = self.cache_dir / f"resolve_{key}.json"
        try:
            p.write_text(json.dumps({"sid": sid}), encoding="utf-8")
        except OSError:
            pass

    def _search_so360(self, query: str) -> list[str]:
        """360 搜索反查豆瓣 subject id。"""
        self._throttle()
        url = SO360_URL.format(q=urllib.parse.quote(f"豆瓣 {query}"))
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"})
            data = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
            subs = re.findall(r"movie\.douban\.com/subject/(\d+)", data)
            subs = list(dict.fromkeys(subs))
            self._channel_result("so360", bool(subs))
            return subs
        except Exception:
            self._channel_result("so360", False)
            return []

    def _search_m_douban(self, query: str) -> list[str]:
        self._throttle()
        url = MD_SEARCH_URL.format(q=urllib.parse.quote(query))
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Referer": "https://m.douban.com/"},
            )
            data = urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore")
            subs = re.findall(r"movie\.douban\.com/subject/(\d+)", data)
            subs = list(dict.fromkeys(subs))
            self._channel_result("m_douban", bool(subs))
            return subs
        except Exception:
            self._channel_result("m_douban", False)
            return []

    def _search_rexxar(self, query: str) -> list[dict]:
        self._throttle()
        url = REXXAR_SEARCH_URL.format(q=urllib.parse.quote(query))
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": UA, "Referer": "https://m.douban.com/"},
            )
            data = json.loads(urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "ignore"))
            items = (data.get("subjects") or {}).get("items") or []
            out = []
            for it in items:
                t = it.get("target") or {}
                if t.get("id"):
                    out.append({"id": str(t["id"]), "title": t.get("title") or ""})
            self._channel_result("rexxar", bool(out))
            return out
        except Exception:
            self._channel_result("rexxar", False)
            return []

    def _detail_direct(self, sid: str) -> dict | None:
        """候选校验用详情获取，失败重试一次。"""
        cached = self._detail_cache(sid)
        if cached:
            return cached
        for attempt in range(2):
            self._throttle()
            try:
                req = urllib.request.Request(
                    DETAIL_URL.format(sid=sid),
                    headers={"User-Agent": UA, "Referer": "https://m.douban.com/"},
                )
                d = json.loads(urllib.request.urlopen(req, timeout=10).read().decode("utf-8", "ignore"))
                if isinstance(d, dict) and d.get("id") is not None:
                    (self.cache_dir / f"douban_{sid}.json").write_text(
                        json.dumps(d, ensure_ascii=False), encoding="utf-8"
                    )
                    return d
            except Exception:
                if attempt == 0:
                    time.sleep(2)
        return None

    def _validated_sid(self, query: str, candidates: list[str], limit: int = 3) -> str | None:
        """用详情接口核对候选 id 的标题，返回第一个匹配。"""
        for sid in candidates[:limit]:
            d = self._detail_direct(sid)
            if not d:
                continue
            t = (d.get("title") or "").strip()
            if _title_ok(query, t):
                return sid
        return None

    def resolve_subject(self, raw_title: str, kind: str) -> str | None:
        """多通道解析豆瓣 subject id，带本地缓存。"""
        query, year = clean_title(raw_title)
        if not query:
            return None
        cached = self._resolve_cache(query)
        if cached:
            if cached == "NEGATIVE":
                return None
            return cached
        # 通道 1：官方 suggest（限流时跳过，恢复后优先）
        if self._fail_streak < 3:
            best = self.pick_best(query, kind)
            if best and best.get("id"):
                sid = str(best["id"])
                self._save_resolve(query, sid)
                return sid
        # 通道 2：360
        if self._channel_ok("so360"):
            search_query = f"{query} {year}" if year else query
            cands = self._search_so360(search_query)
            if cands:
                sid = self._validated_sid(query, cands)
                if sid:
                    self._save_resolve(query, sid)
                    return sid
        # 通道 3：豆瓣移动搜索页
        if self._channel_ok("m_douban"):
            cands = self._search_m_douban(query)
            if cands:
                sid = self._validated_sid(query, cands)
                if sid:
                    self._save_resolve(query, sid)
                    return sid
        # 通道 4：rexxar 搜索
        if self._channel_ok("rexxar"):
            for item in self._search_rexxar(query):
                if _title_ok(query, item.get("title") or ""):
                    self._save_resolve(query, item["id"])
                    return item["id"]
        self._save_resolve(query, None)
        return None
        if isinstance(data, list):
            return data
        return []

    def _detail_cache(self, sid: str) -> dict | None:
        p = self.cache_dir / f"douban_{sid}.json"
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    def detail(self, sid: str) -> dict | None:
        cached = self._detail_cache(sid)
        if cached:
            return cached
        data = self._get_json(DETAIL_URL.format(sid=sid), referer="https://m.douban.com/", retries=1)
        if not isinstance(data, dict) or data.get("id") is None:
            return None
        (self.cache_dir / f"douban_{sid}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
        return data

    @staticmethod
    def _rating_fields(d: dict) -> tuple:
        rating = d.get("rating") or {}
        value = rating.get("value")
        if value is None:
            value = rating.get("average")
        votes = rating.get("count")
        if votes is None:
            votes = rating.get("ratings_count")
        return value, votes

    def pick_best(self, query: str, kind: str) -> dict | None:
        """从 suggest 结果里挑最合适的条目。"""
        results = self.suggest(query)
        if not results:
            return None
        # 过滤：电视剧优先 subtype=tv/含季，电影优先 subtype=movie
        if kind == "tv":
            tv = [r for r in results if r.get("subtype") == "tv"]
            pool = tv or results
        else:
            mv = [r for r in results if r.get("subtype") in ("movie", "")]
            pool = mv or results
        return pool[0]

    def fetch_item_meta(self, title: str, kind: str, sid: str | None = None) -> dict:
        """返回 {douban_id, douban_title, rating, votes, year, summary, poster, url}。"""
        best = None
        if not sid:
            sid = self.resolve_subject(title, kind)
            if not sid:
                return {}
        query, _ = clean_title(title)
        best = {"title": query}
        poster = (best or {}).get("img") or ""
        url = (best or {}).get("url") or ""
        rating = votes = year = summary = None
        douban_title = ""
        if sid:
            d = self.detail(sid)
            if d:
                poster = (d.get("pic") or {}).get("large") or (d.get("pic") or {}).get("normal") or poster
                rating, votes = self._rating_fields(d)
                year = d.get("year")
                summary = d.get("intro")
                douban_title = (d.get("title") or "").strip() or ((best or {}).get("title") or "")
                url = f"https://movie.douban.com/subject/{sid}/"
        else:
            douban_title = (best or {}).get("title") or ""
        return {
            "douban_id": sid,
            "douban_title": douban_title or query,
            "rating": rating,
            "votes": votes,
            "year": year,
            "summary": summary,
            "poster": poster,
            "url": url,
        }

    def download_poster(self, url: str, sid: str) -> Path | None:
        if not url:
            return None
        safe = re.sub(r"[^\w.-]", "_", sid) or "poster"
        dest = self.cache_dir / "posters" / f"{safe}.jpg"
        if dest.exists() and dest.stat().st_size > 5000:
            return dest
        self._throttle()
        headers = {
            "User-Agent": UA,
            "Referer": "https://movie.douban.com/",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        for attempt in range(3):
            try:
                resp = urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=25)
                data = resp.read()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                if "html" in ctype or len(data) < 5000:
                    # 反爬挑战：解析脚本中的 cookie 常量后重试
                    cookie = solve_image_challenge(data.decode("utf-8", "ignore"))
                    if cookie:
                        headers["Cookie"] = "; ".join(
                            p for p in [self._cookie, cookie] if p
                        )
                        continue
                    return None
                with open(dest, "wb") as f:
                    f.write(data)
                if dest.stat().st_size > 5000:
                    return dest
                dest.unlink(missing_ok=True)
            except Exception:
                pass
        return None


def solve_image_challenge(script: str) -> str | None:
    """解析豆瓣图片反爬 JS，返回需要设置的 cookie。"""
    nums = [int(x) for x in re.findall(r"(?:\w+):(\d{6,})", script)]
    m2 = re.search(r"\]\(t,(\d+)\)", script)
    if len(nums) != 3 or not m2:
        return None
    total = sum(nums)
    ssid = m2.group(1)
    return f"__tst_status={total}#; EO_Bot_Ssid={ssid}"
