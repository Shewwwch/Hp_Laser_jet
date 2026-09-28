"""Dependency-free HTTP API and local dashboard."""
import json
import os
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from engine import curated_search, live_search

ROOT = Path(__file__).parent
DB = Path(os.environ.get("SIGNAL_DB", str(ROOT / "data" / "cache.sqlite3")))
DATABASE_URL = os.environ.get("DATABASE_URL")
LOCK = threading.Lock()


def database():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS searches (mode TEXT, query TEXT, created REAL, result TEXT, PRIMARY KEY(mode,query))")
    return con


def cache_get(mode, query):
    if DATABASE_URL:
        import psycopg
        with psycopg.connect(DATABASE_URL) as con:
            con.execute("CREATE TABLE IF NOT EXISTS searches (mode TEXT NOT NULL, query TEXT NOT NULL, created DOUBLE PRECISION NOT NULL, result JSONB NOT NULL, PRIMARY KEY(mode,query))")
            row = con.execute("SELECT created,result FROM searches WHERE mode=%s AND query=%s", (mode, query)).fetchone()
        return (row[0], json.dumps(row[1], ensure_ascii=False) if isinstance(row[1], dict) else row[1]) if row else None
    with database() as con:
        return con.execute("SELECT created,result FROM searches WHERE mode=? AND query=?", (mode, query)).fetchone()


def cache_put(mode, query, result):
    payload = json.dumps(result, ensure_ascii=False)
    if DATABASE_URL:
        import psycopg
        with psycopg.connect(DATABASE_URL) as con:
            con.execute("INSERT INTO searches VALUES (%s,%s,%s,%s::jsonb) ON CONFLICT (mode,query) DO UPDATE SET created=EXCLUDED.created,result=EXCLUDED.result", (mode, query, time.time(), payload))
        return
    with database() as con:
        con.execute("INSERT OR REPLACE INTO searches VALUES (?,?,?,?)", (mode, query, time.time(), payload))


def search(query, mode, refresh=False):
    if mode not in ("demo", "live"):
        raise ValueError("Режим должен быть demo или live")
    query = query.strip()
    if not 2 <= len(query) <= 150:
        raise ValueError("Введите направление от 2 до 150 символов")
    with LOCK:
        row = cache_get(mode, query)
    ttl = 86400 if mode == "live" else 2592000
    if row and not refresh and time.time() - row[0] < ttl:
        result = json.loads(row[1])
        result["cached"] = True
        return result
    result = curated_search(query) if mode == "demo" else live_search(query)
    result["cached"] = False
    result["updated_at"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    with LOCK:
        cache_put(mode, query, result)
    return result


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, data, content_type="application/json; charset=utf-8"):
        payload = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        path = urlsplit(self.path)
        if path.path in ("/", "/index.html"):
            return self._send(200, (ROOT / "static" / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path.path == "/static/style.css":
            return self._send(200, (ROOT / "static" / "style.css").read_bytes(), "text/css; charset=utf-8")
        if path.path == "/static/app.js":
            return self._send(200, (ROOT / "static" / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        if path.path == "/api/health":
            return self._send(200, {"status": "ok", "service": "SignalRadar"})
        if path.path == "/api/search":
            args = parse_qs(path.query)
            query = args.get("q", [""])[0]
            mode = args.get("mode", ["demo"])[0]
            try:
                return self._send(200, search(query, mode, args.get("refresh", [""])[0] == "1"))
            except ValueError as exc:
                return self._send(400, {"error": str(exc)})
            except Exception as exc:
                self.log_error("Search failed: %s", exc)
                return self._send(502, {"error": "Не удалось получить публикации OpenAlex. Проверьте интернет и повторите запрос. Демо доступно отдельно."})
        return self._send(404, {"error": "Страница не найдена"})


if __name__ == "__main__":
    host = os.environ.get("SIGNAL_HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print(f"SignalRadar: http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
