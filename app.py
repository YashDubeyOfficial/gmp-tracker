#!/usr/bin/env python3
"""Run with python3 app.py; use --refresh to update the standalone HTML snapshot."""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import urlparse

from scraper import scrape

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "data" / "ipos.json"
LOCK = threading.Lock()
STATE = {"snapshot": None, "refreshing": False, "progress": None, "lastError": None, "lastAttempt": None}
last_started = 0.0


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as file:
        file.write(text)
        temp = Path(file.name)
    temp.replace(path)


def page(snapshot=None, standalone=False):
    html = (ROOT / "public/index.html").read_text()
    payload = json.dumps(snapshot, ensure_ascii=False).replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = html.replace("__SNAPSHOT__", payload)
    if standalone:
        html = html.replace('<link rel="stylesheet" href="/styles.css">', '<style>' + (ROOT / "public/styles.css").read_text() + '</style>')
        html = html.replace('<script src="/app.js" defer></script>', '<script>' + (ROOT / "public/app.js").read_text() + '</script>')
    return html


def load_cache():
    if CACHE.exists():
        try:
            data = json.loads(CACHE.read_text())
            if not isinstance(data.get("rows"), list) or not data.get("fetchedAt"):
                raise ValueError("Invalid cached snapshot")
            STATE["snapshot"] = data
        except (ValueError, OSError) as exc:
            STATE["lastError"] = f"Saved snapshot could not be read: {exc}"


def progress(done, total):
    with LOCK:
        STATE["progress"] = {"done": done, "total": total}


def refresh():
    try:
        snapshot = scrape(progress=progress)
        atomic_write(CACHE, json.dumps(snapshot, ensure_ascii=False, indent=2))
        atomic_write(ROOT / "dashboard.html", page(snapshot, standalone=True))
        with LOCK:
            STATE["snapshot"] = snapshot
            STATE["lastError"] = None
        print(f"Updated {len(snapshot['rows'])} IPOs; {len(snapshot['warnings'])} detail warnings. Saved dashboard.html", flush=True)
        return True
    except Exception as exc:
        with LOCK:
            STATE["lastError"] = f"Refresh failed: {exc}. Last successful data is retained."
        print(STATE["lastError"], flush=True)
        return False
    finally:
        with LOCK:
            STATE["refreshing"] = False


def start_refresh():
    global last_started
    with LOCK:
        if STATE["refreshing"]:
            return "running"
        if time.monotonic() - last_started < 60:
            return "cooldown"
        last_started = time.monotonic()
        STATE.update(refreshing=True, progress=None, lastAttempt=datetime.now(timezone.utc).isoformat())
    threading.Thread(target=refresh, daemon=True).start()
    return "started"


class Handler(BaseHTTPRequestHandler):
    def send(self, status, data, mime):
        body = data.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", mime + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        route = urlparse(self.path).path
        if route == "/api/ipos":
            # Pick up morning CLI refreshes even if this server stayed open overnight.
            if CACHE.exists():
                try:
                    cached = json.loads(CACHE.read_text())
                    with LOCK:
                        if cached.get("fetchedAt", "") > (STATE["snapshot"] or {}).get("fetchedAt", ""):
                            STATE["snapshot"] = cached
                except (OSError, ValueError):
                    pass
            with LOCK:
                response = json.dumps(STATE)
            self.send(200, response, "application/json")
        elif route == "/":
            self.send(200, page(STATE["snapshot"]), "text/html")
        elif route in ("/app.js", "/styles.css"):
            self.send(200, (ROOT / "public" / route[1:]).read_text(), "text/javascript" if route.endswith("js") else "text/css")
        elif route == "/dashboard.html" and (ROOT / "dashboard.html").exists():
            self.send(200, (ROOT / "dashboard.html").read_text(), "text/html")
        else:
            self.send(404, "Not found", "text/plain")

    def do_POST(self):
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host')}":
            self.send(403, '{"error":"Cross-origin refresh is not allowed"}', "application/json")
            return
        if self.path != "/api/refresh":
            self.send(404, "Not found", "text/plain")
            return
        outcome = start_refresh()
        self.send(429 if outcome == "cooldown" else 202, json.dumps({"status": outcome}), "application/json")

    def log_message(self, fmt, *args):
        if args and "api/ipos" not in str(args[0]):
            super().log_message(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="Scrape once, save JSON + standalone dashboard.html, and exit")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-refresh", action="store_true", help="Serve saved data without refreshing on launch")
    args = parser.parse_args()
    load_cache()
    if args.refresh:
        raise SystemExit(0 if refresh() else 1)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    if not args.no_refresh:
        start_refresh()
    print(f"GmpTraqer: http://127.0.0.1:{args.port}  (Ctrl+C to stop)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
