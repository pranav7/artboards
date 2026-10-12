"""Where things live: the data dir, the port, the repo root and the kit."""
import os
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
KIT_DIR = REPO_ROOT / "kit"
SKILL_DIR = REPO_ROOT / "skills" / "artboard"
DEFAULT_PORT = 8899


def data_dir():
    """$ARTBOARDS_HOME, default ~/.local/share/artboards. Read on every call so tests can
    point it somewhere else."""
    home = os.environ.get("ARTBOARDS_HOME")
    return pathlib.Path(home).expanduser() if home else pathlib.Path.home() / ".local" / "share" / "artboards"


def port():
    return int(os.environ.get("ARTBOARDS_PORT") or DEFAULT_PORT)
