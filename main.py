"""快捷便签 QuickNotes —— 入口。"""

from __future__ import annotations

import os
import sys
import ctypes

from PyQt6.QtWidgets import QApplication

if getattr(sys, "frozen", False):
    sys.path.insert(0, sys._MEIPASS)  # noqa: SLF001
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.hotkey import HotkeyManager  # noqa: E402
from app.log import log  # noqa: E402
from app.storage import Store  # noqa: E402
from app.window import MainWindow  # noqa: E402

INSTANCE_KEY = "QuickNotes_SingleInstance_v1"
APP_WINDOW_TITLE = "快捷便签"


class SingleInstance:
    """使用系统命名互斥体避免引入 QtNetwork（单文件可少约 1MB）。"""

    ERROR_ALREADY_EXISTS = 183

    def __init__(self, key: str):
        self._handle = None
        self.already_running = False
        if sys.platform != "win32":
            return
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        self._close_handle = kernel32.CloseHandle
        self._close_handle.argtypes = [ctypes.c_void_p]
        self._close_handle.restype = ctypes.c_bool
        ctypes.set_last_error(0)
        self._handle = kernel32.CreateMutexW(None, False, key)
        self.already_running = ctypes.get_last_error() == self.ERROR_ALREADY_EXISTS

    def activate_existing(self) -> None:
        if sys.platform != "win32":
            return
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
        user32.FindWindowW.restype = ctypes.c_void_p
        user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
        hwnd = user32.FindWindowW(None, APP_WINDOW_TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)

    def close(self) -> None:
        if self._handle:
            self._close_handle(self._handle)
            self._handle = None


def main() -> int:
    start_hidden = "--startup" in sys.argv or "--hidden" in sys.argv

    instance = SingleInstance(INSTANCE_KEY)
    if instance.already_running:
        instance.activate_existing()
        instance.close()
        return 0

    app = QApplication(sys.argv)
    app.setApplicationName("QuickNotes")
    app.setApplicationDisplayName("快捷便签")
    app.setQuitOnLastWindowClosed(False)
    app.setStyle("Fusion")

    store = Store()
    log(f"启动：python={sys.version.split()[0]} frozen={bool(getattr(sys, 'frozen', False))}")
    if store.fresh:
        store.add(
            "欢迎使用「快捷便签」\n"
            "· 默认按 Ctrl + Alt + N 召唤窗口（设置里可改）\n"
            "· 鼠标滚轮上下浏览，滚到当前页尽头自动翻页\n"
            "· 每页 10 条，底部数字可点击翻页\n"
            "· 点击卡片直接编辑；★ 置顶，↑↓ 调整顺序，⧉ 复制，✕ 删除\n"
            "· 数据保存在本地，托盘图标可退出程序"
        )
        store.save()
    hotkey = HotkeyManager()
    window = MainWindow(store, hotkey)

    app.aboutToQuit.connect(hotkey.shutdown)
    app.aboutToQuit.connect(store.save)
    app.aboutToQuit.connect(instance.close)

    if not start_hidden:
        window.show_window()

    if os.environ.get("QUICKNOTES_SELFTEST"):
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(2000, app.quit)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
