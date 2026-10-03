"""Windows 全局热键：独立消息窗口 + RegisterHotKey。

设计要点：
* 不复用主窗口的 HWND。Qt 在 setWindowFlags / 重建窗口时会更换句柄，
  挂在窗口上的热键会跟着失效（这就是"改了快捷键后唤不出来"的根因）。
* 这里在后台线程创建一个 message-only 窗口（HWND_MESSAGE），
  热键注册在它上面，WM_HOTKEY 由该线程的消息循环接收，
  再通过 Qt 信号（跨线程自动入队）安全地通知主线程。
"""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import threading
import uuid
from ctypes import wintypes as wt

from PyQt6.QtCore import QObject, pyqtSignal

IS_WINDOWS = sys.platform == "win32"

WM_HOTKEY = 0x0312
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

PRIMARY_ID = 1
ALT_ID = 2

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _user32.RegisterHotKey.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    _user32.RegisterHotKey.restype = wt.BOOL
    _user32.UnregisterHotKey.argtypes = [wt.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wt.BOOL
    _user32.VkKeyScanW.argtypes = [wt.WCHAR]
    _user32.VkKeyScanW.restype = ctypes.c_short
    _user32.GetForegroundWindow.restype = wt.HWND
    _user32.DefWindowProcW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    _user32.DefWindowProcW.restype = wt.LPARAM
    # 必须显式声明 64 位下的参数类型，否则 hInstance / hwnd 会被当成 32 位 int 而溢出
    _user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
    _user32.RegisterClassExW.restype = wt.ATOM
    _user32.CreateWindowExW.argtypes = [
        wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wt.HWND, wt.HMENU, wt.HINSTANCE, wt.LPARAM,
    ]
    _user32.CreateWindowExW.restype = wt.HWND
    _user32.PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
    _user32.TranslateMessage.argtypes = [ctypes.POINTER(wt.MSG)]
    _user32.DispatchMessageW.argtypes = [ctypes.POINTER(wt.MSG)]
    _user32.PostQuitMessage.argtypes = [ctypes.c_int]
    _user32.GetMessageW.argtypes = [ctypes.POINTER(wt.MSG), wt.HWND, ctypes.c_uint, ctypes.c_uint]
    _kernel32.GetModuleHandleW.restype = wt.HMODULE


NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "return": 0x0D,
    "esc": 0x1B,
    "escape": 0x1B,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "del": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "up": 0x26,
    "down": 0x28,
    "left": 0x25,
    "right": 0x27,
    "printscreen": 0x2C,
    "pause": 0x13,
    "numlock": 0x90,
}
for _i in range(1, 25):
    NAMED_KEYS[f"f{_i}"] = 0x6F + _i


def parse_combo(combo: str) -> tuple[int, int]:
    """把 "Ctrl+Alt+N" 解析成 (modifiers, virtual_key)。失败返回 (0, 0)。"""
    if not combo:
        return 0, 0
    mods = 0
    vk = 0
    for raw in combo.split("+"):
        part = raw.strip()
        if not part:
            continue
        low = part.lower()
        if low in ("ctrl", "control"):
            mods |= MOD_CONTROL
        elif low in ("alt", "menu"):
            mods |= MOD_ALT
        elif low == "shift":
            mods |= MOD_SHIFT
        elif low in ("win", "meta", "super", "windows"):
            mods |= MOD_WIN
        elif low in NAMED_KEYS:
            vk = NAMED_KEYS[low]
        elif len(part) == 1:
            if part.isalpha():
                # 字母键不区分大小写：Ctrl+Alt+N 不需要同时按 Shift
                vk = _vk_from_char(part.lower())
            else:
                vk = _vk_from_char(part)
                if vk and _vk_shift_state(part) & 1:
                    mods |= MOD_SHIFT
        else:
            return 0, 0
    if not vk:
        return 0, 0
    return mods, vk


def _vk_from_char(ch: str) -> int:
    if not IS_WINDOWS:
        return ord(ch.upper())
    res = _user32.VkKeyScanW(ch)
    if res == -1:
        return 0
    return res & 0xFF


def _vk_shift_state(ch: str) -> int:
    if not IS_WINDOWS:
        return 0
    res = _user32.VkKeyScanW(ch)
    if res == -1:
        return 0
    return (res >> 8) & 0xFF


def foreground_hwnd() -> int:
    """当前前台窗口句柄（非 Windows 返回 0）。"""
    if not IS_WINDOWS:
        return 0
    try:
        return int(_user32.GetForegroundWindow() or 0)
    except Exception:
        return 0


def combo_is_valid(combo: str) -> bool:
    mods, vk = parse_combo(combo)
    if not vk:
        return False
    return bool(mods & (MOD_CONTROL | MOD_ALT | MOD_WIN))


# 与绝大多数软件冲突的常见组合（即使用了 RegisterHotKey 也会被前台程序先吃掉）
RISKY_COMBOS = {
    "ctrl+f": "查找",
    "ctrl+c": "复制",
    "ctrl+v": "粘贴",
    "ctrl+x": "剪切",
    "ctrl+a": "全选",
    "ctrl+z": "撤销",
    "ctrl+y": "重做",
    "ctrl+s": "保存",
    "ctrl+p": "打印",
    "ctrl+o": "打开",
    "ctrl+n": "新建",
    "ctrl+w": "关闭",
    "ctrl+t": "新建标签页",
    "ctrl+tab": "切换标签页",
    "ctrl+q": "退出",
    "alt+f4": "关闭窗口",
    "ctrl+shift+esc": "任务管理器",
}


def combo_hint(combo: str) -> str:
    """给用户看的提示：某些组合会被系统/常见软件抢走。"""
    low = (combo or "").lower().replace(" ", "")
    tips = []
    if "win" in low:
        tips.append("Win 组合键大多被 Windows 保留（如 Win+N 通知中心），建议改用 Ctrl+Alt 组合")
    if "ctrl+alt+del" in low:
        tips.append("Ctrl+Alt+Del 是系统保留键，无法使用")
    if "f12" in low:
        tips.append("F12 常被浏览器开发者工具占用")
    if low in RISKY_COMBOS:
        tips.append(f"这个组合几乎被所有软件用于「{RISKY_COMBOS[low]}」，前台程序会先截获，建议改成 Ctrl+Alt+X 这类三键组合")
    elif low.startswith("ctrl+") and "alt" not in low and "win" not in low:
        tips.append("只用 Ctrl 的两键组合容易与软件自身快捷键冲突，建议加上 Alt（如 Ctrl+Alt+N）")
    return "；".join(tips)


def force_foreground(hwnd: int) -> bool:
    """尽力把窗口提到前台（Qt 的 activateWindow 在桌面/其它全屏程序前经常失败）。"""
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        _user32.SetForegroundWindow.restype = wt.BOOL
        return bool(_user32.SetForegroundWindow(wt.HWND(int(hwnd))))
    except Exception:
        return False


class _HotkeyThread(threading.Thread):
    """后台线程：创建隐藏窗口并跑消息循环。

    关键约束（实测）：RegisterHotKey / UnregisterHotKey 必须在**创建该窗口的线程**里调用，
    跨线程调用会返回错误 1408（无效窗口句柄）。所以注册请求通过消息队列交给本线程执行。
    """

    WM_REGISTER = 0x8001  # WM_APP + 1：请求（重新）注册热键

    def __init__(self, manager: "HotkeyManager"):
        super().__init__(daemon=True, name="QuickNotesHotkey")
        self.manager = manager
        # 类名必须唯一：同一进程内同名窗口类会复用第一次注册的窗口过程，
        # 导致多个实例互相串台（消息被派发到别人的 wndproc）。
        self.class_name = "QuickNotesHotkeyWindow_" + uuid.uuid4().hex[:8]
        self.ready = threading.Event()
        self.hwnd = 0
        self._wndproc = None  # 必须长期持有回调引用，否则会被 GC 掉
        self._requests: queue.Queue = queue.Queue()
        self._results: queue.Queue = queue.Queue()
        self._registered: dict[int, str] = {}

    # ------------------------------------------------------------ 对外（主线程）
    def request_register(self, combos: list[str]) -> tuple[bool, str]:
        """提交注册请求并等待结果（在消息线程内真正执行）。"""
        if not self.hwnd:
            return False, "热键窗口未创建"
        self._requests.put(list(combos))
        _user32.PostMessageW(self.hwnd, self.WM_REGISTER, 0, 0)
        try:
            return self._results.get(timeout=2.5)
        except queue.Empty:
            return False, "热键线程无响应"

    # -------------------------------------------------------------- 线程主体
    def run(self) -> None:
        if not IS_WINDOWS:
            self.ready.set()
            return

        WNDPROC = ctypes.WINFUNCTYPE(wt.LPARAM, wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM)

        def _proc(hwnd, msg, wparam, lparam):
            if msg == WM_HOTKEY:
                self.manager._on_hotkey_message(int(wparam))
                return 0
            if msg == self.WM_REGISTER:
                self._handle_register_request()
                return 0
            if msg == WM_DESTROY:
                _user32.PostQuitMessage(0)
                return 0
            return _user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = WNDPROC(_proc)

        class WNDCLASSEX(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_uint),
                ("style", ctypes.c_uint),
                ("lpfnWndProc", WNDPROC),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wt.HINSTANCE),
                ("hIcon", wt.HICON),
                ("hCursor", wt.HICON),
                ("hbrBackground", wt.HBRUSH),
                ("lpszMenuName", wt.LPCWSTR),
                ("lpszClassName", wt.LPCWSTR),
                ("hIconSm", wt.HICON),
            ]

        hinstance = _kernel32.GetModuleHandleW(None)
        wcex = WNDCLASSEX()
        wcex.cbSize = ctypes.sizeof(WNDCLASSEX)
        wcex.lpfnWndProc = self._wndproc
        wcex.hInstance = hinstance
        wcex.lpszClassName = self.class_name
        _user32.RegisterClassExW(ctypes.byref(wcex))

        hwnd = _user32.CreateWindowExW(
            0x00000080,  # WS_EX_TOOLWINDOW：不出现在任务栏/Alt-Tab
            self.class_name,
            "QuickNotesHotkey",
            0x80000000,  # WS_POPUP（不可见、不会被显示出来）
            0,
            0,
            0,
            0,
            None,
            None,
            hinstance,
            0,
        )
        self.hwnd = int(hwnd or 0)
        self.ready.set()
        self.manager._debug(f"hotkey window hwnd={self.hwnd} err={ctypes.get_last_error() if not self.hwnd else 0}")

        if not self.hwnd:
            return

        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            _user32.TranslateMessage(ctypes.byref(msg))
            _user32.DispatchMessageW(ctypes.byref(msg))

    # ---------------------------------------------------------- 线程内注册逻辑
    def _handle_register_request(self) -> None:
        try:
            combos = self._requests.get_nowait()
        except queue.Empty:
            return
        ok, text = self._register_in_thread(combos)
        self._results.put((ok, text))

    def _register_in_thread(self, combos: list[str]) -> tuple[bool, str]:
        for hotkey_id in list(self._registered):
            _user32.UnregisterHotKey(self.hwnd, hotkey_id)
        self._registered.clear()

        if not combos:
            return False, "未设置快捷键"

        results: list[str] = []
        any_ok = False
        for index, combo in enumerate(combos[:2]):
            hotkey_id = PRIMARY_ID if index == 0 else ALT_ID
            mods, vk = parse_combo(combo)
            if not vk:
                results.append(f"{combo}：无法识别")
                continue
            ok = bool(_user32.RegisterHotKey(self.hwnd, hotkey_id, mods | MOD_NOREPEAT, vk))
            err = ctypes.get_last_error() if not ok else 0
            self.manager._debug(f"register {combo!r} id={hotkey_id} -> {ok} err={err}")
            if ok:
                self._registered[hotkey_id] = combo
                any_ok = True
                results.append(f"{combo}：已生效")
            else:
                reason = "已被其它程序占用" if err == 1409 else f"注册失败（错误码 {err}）"
                results.append(f"{combo}：{reason}")

        if not any_ok:
            return False, "快捷键注册失败：" + "；".join(results)

        ok_text = "、".join(r.split("：")[0] for r in results if "已生效" in r) + " 已生效"
        failed = [r for r in results if "已生效" not in r]
        if failed:
            ok_text += "（" + "；".join(failed) + "）"
        return True, ok_text

    def stop(self) -> None:
        if self.hwnd:
            try:
                _user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        self.join(timeout=2)


class HotkeyManager(QObject):
    """注册/注销全局热键，命中时发出 activated 信号（线程安全）。"""

    activated = pyqtSignal()
    registrationFailed = pyqtSignal(str)
    statusChanged = pyqtSignal(str, bool)  # 状态文本, 是否生效

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._thread = _HotkeyThread(self)
        self._status = "未注册"
        self._ok = False
        self._thread.start()
        self._thread.ready.wait(5)

    # ------------------------------------------------------------------ 状态
    @property
    def hwnd(self) -> int:
        return self._thread.hwnd

    @property
    def status(self) -> str:
        return self._status

    @property
    def ok(self) -> bool:
        return self._ok

    @staticmethod
    def _debug(message: str) -> None:
        if os.environ.get("QUICKNOTES_DEBUG"):
            print("[hotkey] " + message, flush=True)

    # -------------------------------------------------------------- 注册注销
    def register_all(self, combos: list[str]) -> bool:
        """combos[0] 为主快捷键，combos[1] 为备用（可选）。"""
        ok, text = self._thread.request_register(combos)
        self._set_status(text, ok)
        if not ok:
            self.registrationFailed.emit(text)
        return ok

    def unregister_all(self) -> None:
        """解除当前已注册的所有热键。"""
        try:
            self._thread.request_register([])
        except Exception:
            pass

    def shutdown(self) -> None:
        self.unregister_all()
        self._thread.stop()

    def _set_status(self, text: str, ok: bool) -> None:
        self._status = text
        self._ok = ok
        self._debug(f"status: {text}")
        try:
            self.statusChanged.emit(text, ok)
        except RuntimeError:
            pass

    def _on_hotkey_message(self, hotkey_id: int) -> None:
        """在消息线程中被调用，跨线程 emit 会自动排队到主线程。"""
        self._debug(f"WM_HOTKEY id={hotkey_id}")
        try:
            self.activated.emit()
        except RuntimeError:
            pass
