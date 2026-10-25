"""The dashboard. Listens on 127.0.0.1 only, standard library only."""
import json
import pathlib
import shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config, state, store

WEB = pathlib.Path(__file__).parent / "web"


def serve(run: str) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body: bytes, ctype: str):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, (WEB / "index.html").read_bytes(), "text/html; charset=utf-8")
                if path == "/api/state":
                    return self._send(200, json.dumps(state.build(run)).encode(), "application/json")
                if path.startswith("/api/q/"):
                    return self._send(200, json.dumps(state.detail(run, path.rsplit("/", 1)[1])).encode(), "application/json")
            except KeyError:
                return self._send(404, b"{}", "application/json")
            self._send(404, b"not found", "text/plain")

    httpd = ThreadingHTTPServer(("127.0.0.1", config.PORT), Handler)
    print(f"Dashboard: http://127.0.0.1:{config.PORT}   (run '{run}', Ctrl+C to stop)")
    httpd.serve_forever()


def export(run: str, out: str, domain: str = "") -> None:
    """Writes a static copy of the finished night: index.html + data.json, ready for any host."""
    dest = pathlib.Path(out)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(WEB / "index.html", dest / "index.html")
    data = {"state": state.build(run), "details": {q["id"]: state.detail(run, q["id"]) for q in store.questions()}}
    (dest / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if domain:
        (dest / "CNAME").write_text(domain + "\n", encoding="utf-8")
    print(f"Static site written to {dest.resolve()} ({(dest / 'data.json').stat().st_size // 1024} KB of data)")
