"""简易运行日志，便于排查热键等问题。日志文件：%LOCALAPPDATA%\\QuickNotes\\quicknotes.log"""

from __future__ import annotations

import time
from pathlib import Path

from .config import app_data_dir

MAX_SIZE = 256 * 1024
KEEP_LINES = 200


def log_path() -> Path:
    return app_data_dir() / "quicknotes.log"


def log(message: str) -> None:
    path = log_path()
    try:
        line = time.strftime("%Y-%m-%d %H:%M:%S") + "  " + message + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        if path.stat().st_size > MAX_SIZE:
            _trim(path)
    except OSError:
        pass


def _trim(path: Path) -> None:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(lines[-KEEP_LINES:])
    except OSError:
        pass
