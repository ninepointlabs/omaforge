"""HTTP with an on-disk cache, conditional requests, rate-limit handling and offline mode."""

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from omaforge import __version__, paths
from omaforge.core.fsutil import atomic_write_bytes

USER_AGENT = f"omaforge/{__version__} (+https://github.com/ninepointlabs/omaforge)"


class HttpError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class OfflineError(HttpError):
    pass


class RateLimitError(HttpError):
    def __init__(self, message: str, reset_at: float | None = None):
        super().__init__(message, 429)
        self.reset_at = reset_at


@dataclass
class Response:
    status: int
    body: bytes
    headers: dict[str, str]
    from_cache: bool = False
    stale: bool = False

    def json(self):
        return json.loads(self.body)


class Http:
    def __init__(self, cache_dir: Path | None = None, offline: bool = False, timeout: float = 30):
        self.cache_dir = cache_dir or paths.cache_dir() / "http"
        self.offline = offline
        self.timeout = timeout
        self._blocked_until: dict[str, float] = {}

    def _cache_paths(self, url: str, headers: dict) -> tuple[Path, Path]:
        # Tokens change what an API returns (private repos, limits), so key on them too.
        key = hashlib.sha256((url + json.dumps(headers, sort_keys=True)).encode()).hexdigest()
        return self.cache_dir / f"{key}.body", self.cache_dir / f"{key}.meta"

    def _read_cache(self, url, headers):
        body_p, meta_p = self._cache_paths(url, headers)
        try:
            return body_p.read_bytes(), json.loads(meta_p.read_text())
        except (OSError, ValueError):
            return None, None

    def _write_cache(self, url, headers, body: bytes, resp_headers: dict) -> None:
        body_p, meta_p = self._cache_paths(url, headers)
        meta = {
            "url": url,
            "fetched": time.time(),
            "etag": resp_headers.get("etag"),
            "last_modified": resp_headers.get("last-modified"),
            "headers": {k: v for k, v in resp_headers.items() if k in ("content-type", "link")},
        }
        atomic_write_bytes(body_p, body)
        atomic_write_bytes(meta_p, json.dumps(meta).encode())

    def get(self, url: str, headers: dict | None = None, ttl: float = 3600, cache: bool = True) -> Response:
        headers = dict(headers or {})
        cached_body, meta = self._read_cache(url, headers) if cache else (None, None)
        if cached_body is not None and (self.offline or time.time() - meta["fetched"] < ttl):
            return Response(200, cached_body, meta.get("headers", {}), from_cache=True)
        if self.offline:
            raise OfflineError(f"offline and nothing cached for {url}")

        host = urllib.request.urlparse(url).netloc
        blocked = self._blocked_until.get(host, 0)
        if blocked > time.time():
            if cached_body is not None:
                return Response(200, cached_body, meta.get("headers", {}), from_cache=True, stale=True)
            raise RateLimitError(f"{host} rate limit; retry after {time.ctime(blocked)}", blocked)

        req_headers = {"User-Agent": USER_AGENT, **headers}
        if cached_body is not None:
            if meta.get("etag"):
                req_headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                req_headers["If-Modified-Since"] = meta["last_modified"]

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=req_headers), timeout=self.timeout) as r:
                    body = r.read()
                    resp_headers = {k.lower(): v for k, v in r.headers.items()}
                if cache:
                    self._write_cache(url, headers, body, resp_headers)
                return Response(r.status, body, resp_headers)
            except urllib.error.HTTPError as e:
                resp_headers = {k.lower(): v for k, v in (e.headers or {}).items()}
                if e.code == 304 and cached_body is not None:
                    self._write_cache(url, headers, cached_body, {**meta.get("headers", {}), **resp_headers,
                                                                  "etag": meta.get("etag"), "last-modified": meta.get("last_modified")})
                    return Response(200, cached_body, meta.get("headers", {}), from_cache=True)
                if e.code == 429 or (e.code == 403 and resp_headers.get("x-ratelimit-remaining") == "0"):
                    reset = resp_headers.get("x-ratelimit-reset") or ""
                    retry_after = resp_headers.get("retry-after") or ""
                    until = float(reset) if reset.isdigit() else time.time() + (float(retry_after) if retry_after.isdigit() else 60)
                    self._blocked_until[host] = until
                    if cached_body is not None:
                        return Response(200, cached_body, meta.get("headers", {}), from_cache=True, stale=True)
                    raise RateLimitError(f"{host} rate limit reached; resets {time.ctime(until)}", until) from e
                if e.code >= 500 and attempt < 2:
                    last_error = e
                    time.sleep(1 + attempt)
                    continue
                raise HttpError(f"{url}: HTTP {e.code}", e.code) from e
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last_error = e
                if attempt < 1:
                    time.sleep(1)
                    continue
                break
        if cached_body is not None:
            return Response(200, cached_body, meta.get("headers", {}), from_cache=True, stale=True)
        raise OfflineError(f"cannot reach {host}: {last_error}")

    def post_json(self, url: str, payload, headers: dict | None = None, ttl: float = 0):
        """POST JSON. Cached by body when ttl > 0 (for idempotent lookups like fingerprints)."""
        body = json.dumps(payload, sort_keys=True).encode()
        cache_key = {**(headers or {}), "_body": hashlib.sha256(body).hexdigest()}
        cached, meta = self._read_cache(url, cache_key) if ttl else (None, None)
        if cached is not None and (self.offline or time.time() - meta["fetched"] < ttl):
            return json.loads(cached)
        if self.offline:
            raise OfflineError(f"offline and nothing cached for {url}")
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "User-Agent": USER_AGENT, "Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429:
                raise RateLimitError(f"{url}: rate limit reached") from e
            raise HttpError(f"{url}: HTTP {e.code}", e.code) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if cached is not None:
                return json.loads(cached)
            raise OfflineError(f"cannot reach {url}: {e}") from e
        if ttl:
            self._write_cache(url, cache_key, data, {})
        return json.loads(data)

    def get_json(self, url: str, headers: dict | None = None, ttl: float = 3600):
        return self.get(url, headers, ttl).json()

    def download(self, url: str, dest: Path, headers: dict | None = None, max_bytes: int = 512 * 1024 * 1024) -> Path:
        """Stream a file to `dest` (not cached). Raises OfflineError when offline."""
        if self.offline:
            raise OfflineError("offline: cannot download")
        dest.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
        tmp = dest.with_name(dest.name + ".part")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r, open(tmp, "wb") as fh:
                total = 0
                while chunk := r.read(1 << 16):
                    total += len(chunk)
                    if total > max_bytes:
                        raise HttpError(f"{url}: download larger than {max_bytes} bytes")
                    fh.write(chunk)
            tmp.replace(dest)
        except urllib.error.HTTPError as e:
            tmp.unlink(missing_ok=True)
            raise HttpError(f"{url}: HTTP {e.code}", e.code) from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            tmp.unlink(missing_ok=True)
            raise OfflineError(f"download failed: {e}") from e
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return dest
