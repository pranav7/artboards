import json
import http.client
import threading

import pytest
from conftest import make_group

from artboards import paths, server


@pytest.fixture
def running(home):
    """The server on a free port in a thread, with no tidy thread."""
    httpd = server.make_server(port=0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd.server_address[1]
    httpd.shutdown()
    httpd.server_close()


def get(port, path, method="GET"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path)  # sent as is: http.client does not normalise ".."
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    return resp.status, resp.getheader("Content-Type"), body


def test_pages(home, running):
    make_group(home, "g--live--1", {"title": "Live board", "artboards": [{"file": "1-a.html", "state": "open"}]},
               files={"1-a.html": "<p>hi</p>"})
    make_group(home, "g--done--2", {"title": "Done board", "active": False}, files={"1-a.html": "x"})
    status, ctype, body = get(running, "/")
    assert status == 200 and ctype == "text/html; charset=utf-8"
    assert b"Live board" in body and b"Done board" not in body and b"1 closed group" in body
    status, _, body = get(running, "/history")
    assert status == 200 and b"Done board" in body
    assert get(running, "/", method="HEAD")[0] == 200


def test_group_file_and_symlinked_group(home, running, tmp_path):
    make_group(home, "g", files={"1-a.html": "<p>hi</p>", "shot.png": "png"})
    elsewhere = tmp_path / "docs"
    elsewhere.mkdir()
    (elsewhere / "b.html").write_text("linked")
    (home / "linked").symlink_to(elsewhere)
    assert get(running, "/g/1-a.html") == (200, "text/html; charset=utf-8", b"<p>hi</p>")
    assert get(running, "/g/shot.png")[1] == "image/png"
    assert get(running, "/linked/b.html")[2] == b"linked"
    assert get(running, "/g/1%2Da.html")[0] == 200


def test_kit_route(running):
    if not (paths.KIT_DIR / "lofi.js").exists():
        pytest.skip("kit/lofi.js is not written yet")
    status, ctype, body = get(running, "/_kit/lofi.js")
    assert status == 200 and ctype == "text/javascript; charset=utf-8"
    assert body == (paths.KIT_DIR / "lofi.js").read_bytes()


def test_kit_route_serves_kit_files(running, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    (kit / "lofi.css").write_text("body{}")
    monkeypatch.setattr(paths, "KIT_DIR", kit)
    assert get(running, "/_kit/lofi.css") == (200, "text/css; charset=utf-8", b"body{}")
    assert get(running, "/_kit/nope.js")[0] == 404


def test_not_found(home, running):
    make_group(home, "g", files={"a.html": "x"})
    (home / ".server.log").write_text("secret")
    for path in ("/nope", "/g", "/g/", "/g/missing.html", "/nope/a.html", "/.server.log", "/_kit/"):
        assert get(running, path)[0] == 404, path


def test_traversal_is_refused(home, running, tmp_path):
    make_group(home, "g", files={"a.html": "x"})
    (tmp_path / "secret.txt").write_text("secret")
    (home / "g" / "out.txt").symlink_to(tmp_path / "secret.txt")
    for path in ("/g/../../secret.txt", "/g/%2e%2e/%2e%2e/secret.txt", "/_kit/../pyproject.toml",
                 "/_kit/%2e%2e/pyproject.toml", "/g/out.txt", "/g/..%5c..%5csecret.txt"):
        status, _, body = get(running, path)
        assert status in (403, 404), path
        assert b"secret" not in body and b"[project]" not in body


def test_tidy_loop_survives_a_failure(monkeypatch, capsys):
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("tidy blew up")

    def stop(_):
        if len(calls) >= 2:
            raise SystemExit
    monkeypatch.setattr(server.tidy, "run", boom)
    monkeypatch.setattr(server.time, "sleep", stop)
    with pytest.raises(SystemExit):
        server.tidy_loop(1)
    assert len(calls) == 2
    assert "tidy blew up" in capsys.readouterr().err


def post(port, path, origin):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request("POST", path, headers={"Origin": origin} if origin else {})
    resp = conn.getresponse()
    resp.read()
    conn.close()
    return resp.status


def test_archive_and_reopen_buttons(home, running):
    folder = make_group(home, "g--live--1", {"title": "Live board", "artboards": [{"file": "1-a.html", "state": "open"}]},
                        files={"1-a.html": "x"})
    origin = f"http://localhost:{running}"
    assert post(running, "/_api/archive/g--live--1", origin) == 200
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["active"] is False and meta["closed"]["reason"] == "by-hand"
    assert b"Live board" not in get(running, "/")[2]
    assert b'data-action="reopen" data-key="g--live--1"' in get(running, "/history")[2]

    assert post(running, "/_api/reopen/g--live--1", f"http://127.0.0.1:{running}") == 200
    meta = json.loads((folder / "meta.json").read_text())
    assert meta["active"] is True and meta["keep"] is True and "closed" not in meta
    assert b'data-action="archive" data-key="g--live--1"' in get(running, "/")[2]


def test_buttons_refuse_other_origins_and_bad_paths(home, running):
    folder = make_group(home, "g--live--1", {"title": "Live board"}, files={"1-a.html": "x"})
    before = (folder / "meta.json").read_text()
    assert post(running, "/_api/archive/g--live--1", None) == 403
    assert post(running, "/_api/archive/g--live--1", "https://example.com") == 403
    assert post(running, "/_api/archive/g--live--1", "http://localhost:1") == 403
    assert post(running, "/_api/archive/nope", f"http://localhost:{running}") == 404
    assert post(running, "/_api/delete/g--live--1", f"http://localhost:{running}") == 404
    assert post(running, "/_api/archive/..", f"http://localhost:{running}") == 404
    assert (folder / "meta.json").read_text() == before
