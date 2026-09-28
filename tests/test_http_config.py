import json
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from omaforge import config
from omaforge.core.http import Http, OfflineError, RateLimitError


class Handler(BaseHTTPRequestHandler):
    hits: dict = {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        Handler.hits[self.path] = Handler.hits.get(self.path, 0) + 1
        if self.path == "/etag":
            if self.headers.get("If-None-Match") == '"v1"':
                self.send_response(304)
                self.end_headers()
                return
            self._json({"n": Handler.hits[self.path]}, etag='"v1"')
        elif self.path == "/limited":
            self.send_response(429)
            self.send_header("Retry-After", "30")
            self.end_headers()
        elif self.path == "/zip":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"PK" + b"x" * 100)
        else:
            self._json({"path": self.path})

    def _json(self, obj, etag=None):
        body = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        if etag:
            self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def test_cache_and_ttl(server, tmp_path):
    http = Http(cache_dir=tmp_path)
    assert http.get_json(f"{server}/a") == {"path": "/a"}
    hits = Handler.hits["/a"]
    assert http.get_json(f"{server}/a", ttl=60) == {"path": "/a"}
    assert Handler.hits["/a"] == hits


def test_etag_revalidation(server, tmp_path):
    http = Http(cache_dir=tmp_path)
    first = http.get_json(f"{server}/etag", ttl=0)
    r = http.get(f"{server}/etag", ttl=0)
    assert r.from_cache and r.json() == first


def test_offline_uses_cache_or_fails(server, tmp_path):
    Http(cache_dir=tmp_path).get_json(f"{server}/b")
    offline = Http(cache_dir=tmp_path, offline=True)
    assert offline.get_json(f"{server}/b", ttl=0) == {"path": "/b"}
    with pytest.raises(OfflineError):
        offline.get_json(f"{server}/never")


def test_unreachable_falls_back_to_stale_cache(tmp_path, monkeypatch):
    http = Http(cache_dir=tmp_path, timeout=1)
    url = "http://127.0.0.1:9/unreachable"
    http._write_cache(url, {}, b'{"cached": true}', {})
    monkeypatch.setattr("omaforge.core.http.time.sleep", lambda s: None)
    r = http.get(url, ttl=0)
    assert r.stale and r.json() == {"cached": True}


def test_rate_limit(server, tmp_path):
    http = Http(cache_dir=tmp_path)
    with pytest.raises(RateLimitError):
        http.get_json(f"{server}/limited")
    hits = Handler.hits["/limited"]
    with pytest.raises(RateLimitError):  # host is now blocked; no new request
        http.get_json(f"{server}/other")
    assert Handler.hits["/limited"] == hits and "/other" not in Handler.hits


def test_download(server, tmp_path):
    dest = Http(cache_dir=tmp_path).download(f"{server}/zip", tmp_path / "f.zip")
    assert dest.read_bytes().startswith(b"PK")
    assert not list(tmp_path.glob("*.part"))


def test_config_roundtrip_and_permissions(tmp_path):
    cfg = config.load()
    cfg["providers"]["github"]["token"] = 'to"ken'
    cfg["roots"]["paths"] = ["/a b/c"]
    config.save(cfg)
    assert config.config_path().stat().st_mode & 0o777 == 0o600
    assert config.load()["providers"]["github"]["token"] == 'to"ken'
    assert tomllib.loads(config.dumps(cfg))["roots"]["paths"] == ["/a b/c"]


def test_env_overrides_secrets(monkeypatch):
    monkeypatch.setenv("OMAFORGE_CURSEFORGE_API_KEY", "envkey")
    assert config.load()["providers"]["curseforge"]["api_key"] == "envkey"
