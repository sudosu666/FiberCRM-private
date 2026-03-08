from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import os


ROOT = Path(__file__).resolve().parent
APP_ROOT = ROOT / "app"
TEMPLATES = APP_ROOT / "templates"
STATIC = APP_ROOT / "static"

ROUTES = {
    "/": "login.html",
    "/login": "login.html",
    "/dispatcher": "dispatcher.html",
    "/designer": "designer.html",
    "/field": "field-ops.html",
    "/warehouse": "warehouse.html",
    "/connections-dispatch": "connections-dispatch.html",
}


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/static/"):
            self.serve_static(self.path.removeprefix("/static/"))
            return
        template_name = ROUTES.get(self.path.rstrip("/") or "/")
        if template_name:
            self.serve_template(template_name)
            return
        self.send_error(404, "Route not found in frontend preview")

    def serve_template(self, template_name: str) -> None:
        path = TEMPLATES / template_name
        if not path.exists():
            self.send_error(404, "Template not found")
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def serve_static(self, relative_path: str) -> None:
        path = STATIC / relative_path
        if not path.exists() or not path.is_file():
            self.send_error(404, "Static file not found")
            return
        self.path = "/" + os.path.relpath(path, APP_ROOT).replace(os.sep, "/")
        return super().do_GET()

    def translate_path(self, path: str) -> str:
        clean = path.lstrip("/")
        return str(APP_ROOT / clean)


def main() -> None:
    parser = argparse.ArgumentParser(description="Frontend preview server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    print(f"frontend preview on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
