"""数据目录、设置项、开机自启等与运行环境相关的内容。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

APP_NAME = "QuickNotes"
APP_TITLE = "快捷便签"

DEFAULT_SETTINGS: dict = {
    "hotkey": "Ctrl+Alt+N",
    "hotkey_alt": "",        # 备用召唤快捷键，留空表示不启用
    "per_page": 10,
    "always_on_top": True,
    "opacity": 100,          # 百分比 40~100
    "theme": "light",        # light / dark
    "font_size": 13,
    "width": 440,
    "height": 680,
    "pos": None,             # [x, y] 或 None
    "confirm_delete": True,
    "hide_on_outside_click": True,
    "autostart": False,
    "show_pinned_first": True,
}


def app_data_dir() -> Path:
    """数据存放目录：%LOCALAPPDATA%\\QuickNotes"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def data_file() -> Path:
    return app_data_dir() / "data.json"


def app_root() -> Path:
    """程序所在目录（main.py 所在目录）。"""
    return Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    hotkey: str = DEFAULT_SETTINGS["hotkey"]
    hotkey_alt: str = DEFAULT_SETTINGS["hotkey_alt"]
    per_page: int = DEFAULT_SETTINGS["per_page"]
    always_on_top: bool = DEFAULT_SETTINGS["always_on_top"]
    opacity: int = DEFAULT_SETTINGS["opacity"]
    theme: str = DEFAULT_SETTINGS["theme"]
    font_size: int = DEFAULT_SETTINGS["font_size"]
    width: int = DEFAULT_SETTINGS["width"]
    height: int = DEFAULT_SETTINGS["height"]
    pos: list | None = None
    confirm_delete: bool = DEFAULT_SETTINGS["confirm_delete"]
    hide_on_outside_click: bool = DEFAULT_SETTINGS["hide_on_outside_click"]
    autostart: bool = DEFAULT_SETTINGS["autostart"]
    show_pinned_first: bool = DEFAULT_SETTINGS["show_pinned_first"]

    @classmethod
    def from_dict(cls, data: dict | None) -> "Settings":
        s = cls()
        if isinstance(data, dict):
            for key, value in data.items():
                if hasattr(s, key) and value is not None:
                    setattr(s, key, value)
        s.per_page = max(1, min(100, int(s.per_page)))
        s.font_size = max(10, min(24, int(s.font_size)))
        s.opacity = max(40, min(100, int(s.opacity)))
        s.width = max(320, min(1200, int(s.width)))
        s.height = max(300, min(1600, int(s.height)))
        if s.theme not in ("light", "dark"):
            s.theme = "light"
        return s

    def to_dict(self) -> dict:
        return asdict(self)


# --------------------------------------------------------------------------
# 开机自启（Windows 注册表 Run 项）
# --------------------------------------------------------------------------
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _launch_command() -> str:
    """开机自启时执行的命令。"""
    exe = sys.executable
    if getattr(sys, "frozen", False):
        return f'"{exe}" --startup'
    # 开发/源码模式：优先使用 pythonw.exe（无控制台窗口）
    pyw = Path(exe).with_name("pythonw.exe")
    if pyw.exists():
        exe = str(pyw)
    main_py = app_root() / "main.py"
    return f'"{exe}" "{main_py}"'


def is_autostart_enabled() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_WRITE) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except OSError:
                    pass
        return True
    except OSError:
        return False
