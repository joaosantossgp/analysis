from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from desktop.bridge import CVMBridge


NEWS_METHODS = {
    "get_news_articles",
    "get_news_overview",
    "get_news_company_scope",
    "get_news_retention_status",
    "get_news_article_classification",
    "get_news_article_content",
    "get_news_sources",
    "get_news_collection_runs",
    "get_news_refresh_status",
    "refresh_news_sources",
    "set_news_source_enabled",
    "set_news_source_priority",
    "add_custom_news_source",
    "update_news_article_state",
    "apply_news_classification_correction",
    "set_news_company_scope_override",
    "save_news_retention_policy",
    "cleanup_news_extracted_content",
}


class NewsDevBridgeServer:
    def __init__(self) -> None:
        self.bridge = CVMBridge()

    def call(self, method: str, params: dict[str, Any]) -> Any:
        if method not in NEWS_METHODS:
            return {"status": "error", "error": f"Method {method} is not allowed by the News dev bridge"}
        fn = getattr(self.bridge, method, None)
        if not callable(fn):
            return {"status": "error", "error": f"Method {method} is not implemented"}
        return fn(params)


def _handler(runtime: NewsDevBridgeServer, allowed_origin: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "CVMNewsDevBridge/1.0"

        def _cors_origin(self) -> str:
            origin = self.headers.get("Origin") or ""
            parsed = urlsplit(origin)
            if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"}:
                return origin
            return allowed_origin

        def _send_json(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", self._cors_origin())
            self.send_header("Access-Control-Allow-Headers", "content-type")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self._send_json(200, {"ok": True})

        def do_GET(self) -> None:
            if urlsplit(self.path).path != "/health":
                self._send_json(404, {"status": "error", "error": "not found"})
                return
            self._send_json(200, {"status": "ok", "service": "news-dev-bridge"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path != "/bridge":
                self._send_json(404, {"status": "error", "error": "not found"})
                return
            try:
                length = int(self.headers.get("content-length") or "0")
                raw = self.rfile.read(length)
                request = json.loads(raw.decode("utf-8") or "{}")
                method = str(request.get("method") or "")
                params = request.get("params") if isinstance(request.get("params"), dict) else {}
                self._send_json(200, runtime.call(method, params))
            except Exception as exc:
                self._send_json(500, {"status": "error", "error": str(exc)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Local development HTTP bridge for CVMAnalytics News.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allowed-origin", default="http://127.0.0.1:5173")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("News dev bridge only binds to localhost")

    runtime = NewsDevBridgeServer()
    server = ThreadingHTTPServer((args.host, args.port), _handler(runtime, args.allowed_origin))
    print(f"[news-dev-bridge] listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
