"""Dev-only bridge from Docker API to the loopback Debussy Vite proxy."""

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx


TARGET = os.environ.get("DEBUSSY_DEV_PROXY_TARGET", "http://127.0.0.1:5176")
BIND = os.environ.get("DEBUSSY_DEV_BRIDGE_BIND", "10.113.114.88")
PORT = int(os.environ.get("DEBUSSY_DEV_BRIDGE_PORT", "8767"))
EXCHANGE_PATH = "/api/embed/v1/auth/exchange"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/healthz":
            self.send_error(404)
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def do_POST(self):
        if self.path != EXCHANGE_PATH:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length < 1 or length > 16 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length)
        try:
            with httpx.Client(timeout=8.0, trust_env=False) as client:
                upstream = client.post(
                    TARGET.rstrip("/") + EXCHANGE_PATH,
                    content=body,
                    headers={
                        "Authorization": self.headers.get("Authorization", ""),
                        "Content-Type": "application/json",
                    },
                )
        except httpx.HTTPError:
            self.send_error(502)
            return
        self.send_response(upstream.status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(upstream.content)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer((BIND, PORT), Handler).serve_forever()
