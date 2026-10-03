"""基础功能自测：storage / hotkey 解析 / 主窗口分页与渲染。"""

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.hotkey import combo_is_valid, parse_combo  # noqa: E402
from app.storage import Store  # noqa: E402


def test_hotkey_parse():
    assert combo_is_valid("Ctrl+Alt+N")
    assert combo_is_valid("Ctrl+Shift+F1")
    assert not combo_is_valid("N")            # 缺少修饰键
    assert not combo_is_valid("Ctrl+")        # 缺少主键
    mods, vk = parse_combo("Ctrl+Alt+N")
    assert mods == 0x0002 | 0x0001 and vk == 0x4E, (mods, vk)   # 不带 Shift
    _, vk_f1 = parse_combo("Ctrl+Shift+F1")
    assert vk_f1 == 0x70
    print("hotkey parse OK")


def test_store(tmp: Path):
    store = Store(tmp / "data.json")
    for i in range(25):
        store.add(f"便签 {i}")
    assert len(store.notes) == 25
    assert store.notes[0].text == "便签 24"        # 新建的在最前

    store.settings.per_page = 10
    notes = store.visible_notes()
    assert len(notes) == 25
    assert len(notes[0:10]) == 10

    # 搜索
    assert len(store.visible_notes("便签 1")) == 11   # 1,10..19
    assert len(store.visible_notes("不存在的关键词")) == 0

    # 置顶优先
    first = store.notes[-1]
    store.toggle_pin(first.id)
    assert store.visible_notes()[0].id == first.id

    # 上移 / 下移
    ids_before = [n.id for n in store.visible_notes()]
    target = ids_before[3]
    store.move(target, -1)
    ids_after = [n.id for n in store.visible_notes()]
    assert ids_after.index(target) == 2, ids_after[:5]

    # 删除
    store.delete(target)
    assert len(store.notes) == 24

    # 保存 / 重新加载
    store.save()
    reloaded = Store(tmp / "data.json")
    assert len(reloaded.notes) == 24
    assert reloaded.notes[0].text == store.notes[0].text

    # 导出 / 导入（分享包）
    backup = tmp / "backup.json"
    assert store.export_to(backup, title="测试便签集", author="小张")
    other = Store(tmp / "other.json")
    added, skipped = other.import_from(backup)
    assert added == 24 and skipped == 0, (added, skipped)
    assert other.import_from(backup) == (0, 24)   # 重复内容应被跳过

    meta, notes = Store.read_share(backup)
    assert meta["title"] == "测试便签集" and meta["author"] == "小张", meta
    assert len(notes) == 24
    print("store OK")


def test_hotkey_manager():
    """用 PostMessage 伪造 WM_HOTKEY，验证「消息窗口 -> Qt 信号」整条链路。"""
    import ctypes
    import time

    from PyQt6.QtWidgets import QApplication

    from app.hotkey import HotkeyManager

    app = QApplication.instance() or QApplication(sys.argv)
    manager = HotkeyManager()
    assert manager.hwnd, "消息窗口创建失败"
    print("hotkey message window hwnd =", manager.hwnd)

    hits = []
    manager.activated.connect(lambda: hits.append(1))

    ok = manager.register_all(["Ctrl+Alt+N"])
    assert ok and manager.ok, manager.status
    print("hotkey status:", manager.status)

    u = ctypes.windll.user32
    u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_void_p]
    u.PostMessageW(manager.hwnd, 0x0312, 1, 0)
    for _ in range(60):
        app.processEvents()
        if hits:
            break
        time.sleep(0.02)
    assert hits, "WM_HOTKEY 没有触发 activated 信号"

    # 改成另一组快捷键后仍然可用（这是之前失效的场景）
    hits.clear()
    assert manager.register_all(["Ctrl+Alt+Q"])
    u.PostMessageW(manager.hwnd, 0x0312, 1, 0)
    for _ in range(60):
        app.processEvents()
        if hits:
            break
        time.sleep(0.02)
    assert hits, "切换快捷键后热键失效"

    # 旧组合必须被真正释放：另一个独立的热键管理器应该能抢到 Ctrl+Alt+N
    from app.hotkey import HotkeyManager as _HM

    other = _HM()
    released = other.register_all(["Ctrl+Alt+N"])
    other.shutdown()
    assert released, f"旧快捷键没有被释放，仍被占用（{other.status}）"
    print("hotkey manager OK")


def test_window(tmp: Path):
    from PyQt6.QtWidgets import QApplication

    from app.hotkey import HotkeyManager
    from app.window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    store = Store(tmp / "data2.json")
    store.settings.per_page = 10
    for i in range(23):
        store.add(f"内容 {i}")

    win = MainWindow(store, HotkeyManager())
    win.show()
    app.processEvents()

    assert win._total_pages == 3, win._total_pages
    assert len(win._cards) == 10, len(win._cards)

    win.go_page(3)
    app.processEvents()
    assert win._page == 3
    assert len(win._cards) == 3, len(win._cards)

    win.prev_page()
    app.processEvents()
    assert win._page == 2 and len(win._cards) == 10

    # 新建便签会跳回第一页并聚焦
    win.new_note()
    app.processEvents()
    assert win._page == 1 and len(store.notes) == 24

    # 分页越界保护
    win.go_page(99)
    assert win._page == win._total_pages
    win.go_page(-5)
    assert win._page == 1
    print("window paging OK")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        test_hotkey_parse()
        test_store(tmp)
        test_hotkey_manager()
        test_window(tmp)
    print("ALL TESTS PASSED")
