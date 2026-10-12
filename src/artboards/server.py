"""The artboards HTTP server.

Routes: "/" the review queue, "/history" closed groups, "/_kit/<file>" the lo-fi kit, and
"/<group>/<file>" files from the data dir (group folders may be symlinks). Anything else is a
404, and a path that leaves the data dir or the kit dir is refused.

POST "/_api/archive/<key>" and "/_api/reopen/<key>" are the buttons on the two index pages.
They accept only requests whose Origin is this server, so another site cannot press them.
"""
import http.server
import mimetypes
import os
import pathlib
import sys
import threading
import time
import traceback
from urllib.parse import unquote, urlsplit

from . import index, paths, tidy
from . import meta as m

TIDY_EVERY = 3600
ACTIONS = {"archive": m.close_by_hand, "reopen": m.reopen}
mimetypes.add_type("text/javascript", ".js")


def inside(path, base):
    """The resolved path when it stays inside base, else None."""
    try:
        resolved = path.resolve()
        resolved.relative_to(base.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    return resolved


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "artboards"

    def do_GET(self):
        self.respond(body=True)

    def do_HEAD(self):
        self.respond(body=False)

    def do_POST(self):
        parts = [p for p in unquote(urlsplit(self.path).path).split("/") if p]
        if len(parts) != 3 or parts[0] != "_api" or parts[1] not in ACTIONS:
            return self.send_error(404)
        port = self.server.server_address[1]
        if self.headers.get("Origin") not in (f"http://localhost:{port}", f"http://127.0.0.1:{port}"):
            return self.send_error(403, "Request from another origin refused")
        key = parts[2]
        folder = paths.data_dir() / key
        if key.startswith(".") or "\\" in key or not os.path.isdir(folder):
            return self.send_error(404)
        meta, ok = m.load_meta(folder)
        if not ok:
            return self.send_error(409, "meta.json cannot be read")
        ACTIONS[parts[1]](meta)
        m.write_meta(folder, meta)
        self.send_bytes(b'{"ok": true}\n', "application/json; charset=utf-8", body=True)

    def respond(self, body):
        path = unquote(urlsplit(self.path).path)
        parts = [p for p in path.split("/") if p]
        if path in ("/", "/index.html"):
            return self.send_page(index.render_main(index.read_groups()), body)
        if parts == ["history"]:
            return self.send_page(index.render_history(index.read_groups()), body)
        if any(p in (".", "..") or "\\" in p for p in parts):
            return self.send_error(403, "Path refused")
        if len(parts) >= 2 and parts[0] == "_kit":
            return self.send_file(paths.KIT_DIR, paths.KIT_DIR.joinpath(*parts[1:]), body)
        if len(parts) >= 2 and not parts[0].startswith("."):
            group = paths.data_dir() / parts[0]
            return self.send_file(group, group.joinpath(*parts[1:]), body)
        return self.send_error(404)

    def send_page(self, text, body):
        self.send_bytes(text.encode("utf-8"), "text/html; charset=utf-8", body)

    def send_file(self, base, path, body):
        if not base.is_dir():
            return self.send_error(404)
        resolved = inside(path, base)
        if resolved is None:
            return self.send_error(403, "Path refused")
        if not resolved.is_file():
            return self.send_error(404)
        try:
            data = resolved.read_bytes()
        except OSError:
            return self.send_error(404)
        ctype = mimetypes.guess_type(resolved.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        self.send_bytes(data, ctype, body)

    def send_bytes(self, data, ctype, body):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(data)

    def log_message(self, fmt, *args):
        pass  # the access log is noise; errors still print


class Server(http.server.ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def tidy_loop(every):
    """Run tidy now and then every `every` seconds. A failure prints and never stops the server."""
    while True:
        try:
            lines, _ = tidy.run()
            for line in lines:
                print(f"tidy: {line}", flush=True)
        except Exception:
            print("artboards: tidy failed", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)
        time.sleep(every)


def make_server(port=None, host="127.0.0.1"):
    return Server((host, paths.port() if port is None else port), Handler)


def serve(port=None, tidy_every=TIDY_EVERY):
    """Run in the foreground. tidy_every=None turns the tidy thread off."""
    httpd = make_server(port)
    if tidy_every:
        threading.Thread(target=tidy_loop, args=(tidy_every,), daemon=True, name="tidy").start()
    print(f"artboards on http://localhost:{httpd.server_address[1]}/ serving {paths.data_dir()}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
