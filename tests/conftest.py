import json
import os
import pathlib
import time

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"
EXAMPLE_BOARD = REPO / "examples" / "tool-library" / "1-Tool-library.html"
DAY = 86400


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A temp ARTBOARDS_HOME, never the real data dir."""
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("ARTBOARDS_HOME", str(root))
    return root


def make_group(root, key, meta=None, files=None, age_days=0.0, raw_meta=None):
    """A group folder. files maps a name to its text; every file gets an mtime age_days old.
    raw_meta writes meta.json as given (for malformed cases)."""
    folder = root / key
    folder.mkdir(parents=True)
    if raw_meta is not None:
        (folder / "meta.json").write_text(raw_meta)
    elif meta is not None:
        (folder / "meta.json").write_text(json.dumps(meta))
    stamp = time.time() - age_days * DAY
    for name, text in (files or {}).items():
        path = folder / name
        path.write_text(text)
        os.utime(path, (stamp, stamp))
    return folder


def age(path, days):
    stamp = time.time() - days * DAY
    os.utime(path, (stamp, stamp), follow_symlinks=False)


def require(path):
    """Skip when a file the other half of the build writes is not there yet."""
    if not path.exists():
        pytest.skip(f"{path.relative_to(REPO)} is not written yet")
    return path
