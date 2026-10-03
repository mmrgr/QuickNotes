"""验证设置对话框能正常构建，分享按钮可见可点。"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402
from app.storage import Store  # noqa: E402
from app.hotkey import HotkeyManager  # noqa: E402
from app.settings_dialog import SettingsDialog  # noqa: E402

app = QApplication([])

tmp = Path(__file__).parent.parent / "_tmp_ui_check.json"
store = Store(tmp)
store.notes = []
store.save()

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


try:
    dlg = SettingsDialog(store, HotkeyManager(), None)
    dlg.show()
    app.processEvents()
    ok("设置对话框创建成功", dlg is not None)
    ok("对话框可见", dlg.isVisible())

    btns = dlg.findChildren(QPushButton)
    texts = [b.text() for b in btns]
    ok("存在「导出分享包…」按钮", any("导出分享包" in t for t in texts), f"buttons={texts}")
    ok("存在「导入分享包…」按钮", any("导入分享包" in t for t in texts), f"buttons={texts}")
    ok("导出按钮已连接回调", dlg.btn_export.receivers(dlg.btn_export.clicked) > 0)
    ok("导入按钮已连接回调", dlg.btn_import.receivers(dlg.btn_import.clicked) > 0)
    ok("导出按钮 enabled", dlg.btn_export.isEnabled())
    ok("导入按钮 enabled", dlg.btn_import.isEnabled())
    ok("导出按钮在窗口内可见", dlg.btn_export.isVisible())

    dlg.close()
except Exception as e:  # noqa: BLE001
    ok("设置对话框构建未抛异常", False, f"{type(e).__name__}: {e}")

if tmp.exists():
    tmp.unlink()

print("\n===== 设置界面分享入口验证 =====")
passed = 0
for name, flag, extra in results:
    print(("PASS" if flag else "FAIL") + "  " + name + (f"   ({extra})" if extra else ""))
    if flag:
        passed += 1
print(f"\n通过 {passed}/{len(results)}")
sys.exit(0 if passed == len(results) else 1)
