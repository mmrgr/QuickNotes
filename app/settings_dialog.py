"""设置窗口。"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import Settings, app_data_dir, data_file, is_autostart_enabled, set_autostart
from .hotkey import combo_hint, combo_is_valid
from .theme import dialog_stylesheet
from .widgets import confirm


class HotkeyCapture(QLineEdit):
    """点击后按下组合键即可录入，例如 Ctrl+Alt+N。"""

    MOD_ORDER = [
        (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
        (Qt.KeyboardModifier.AltModifier, "Alt"),
        (Qt.KeyboardModifier.ShiftModifier, "Shift"),
        (Qt.KeyboardModifier.MetaModifier, "Win"),
    ]

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处，然后按下组合键")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    @staticmethod
    def _key_name(key: int) -> str:
        special = {
            Qt.Key.Key_Space: "Space",
            Qt.Key.Key_Enter: "Enter",
            Qt.Key.Key_Return: "Enter",
            Qt.Key.Key_Escape: "Esc",
            Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Backspace: "Backspace",
            Qt.Key.Key_Delete: "Delete",
            Qt.Key.Key_Insert: "Insert",
            Qt.Key.Key_Home: "Home",
            Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "PageUp",
            Qt.Key.Key_PageDown: "PageDown",
            Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down",
            Qt.Key.Key_Left: "Left",
            Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Print: "PrintScreen",
        }
        if key in special:
            return special[key]
        base = int(Qt.Key.Key_F1)
        if base <= key <= base + 24:
            return f"F{int(key) - base + 1}"
        if 32 <= key < 127:
            return chr(key)
        return ""

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        if key in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Meta,
            Qt.Key.Key_unknown,
        ):
            parts = [name for m, name in self.MOD_ORDER if mods & m]
            self.setText("+".join(parts))
            return
        if key == Qt.Key.Key_Backspace and not (
            mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)
        ):
            self.clear()
            return
        parts = [name for m, name in self.MOD_ORDER if mods & m]
        name = self._key_name(key)
        if name:
            parts.append(name)
            self.setText("+".join(parts))
        event.accept()


class SettingsDialog(QDialog):
    def __init__(self, store, hotkey=None, parent: QWidget | None = None):
        super().__init__(parent)
        self.store = store
        self.hotkey = hotkey
        self.setWindowTitle("设置 — 快捷便签")
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setStyleSheet(dialog_stylesheet(store.settings))
        self._build()
        self._refresh_hotkey_status()
        if self.hotkey is not None:
            self.hotkey.statusChanged.connect(self._refresh_hotkey_status)

    def _refresh_hotkey_status(self, *_args) -> None:
        if not hasattr(self, "hotkey_status_label"):
            return
        if self.hotkey is None:
            self.hotkey_status_label.setText("状态：未知")
            return
        text = self.hotkey.status or "未注册"
        self.hotkey_status_label.setText(f"状态：{text}")
        color = "#d64545" if not self.hotkey.ok else ""
        self.hotkey_status_label.setStyleSheet(f"color: {color};" if color else "")

    def _build(self) -> None:
        s = self.store.settings
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(10)

        # ---------------- 召唤
        box_hotkey = QGroupBox("召唤", self)
        form = QFormLayout(box_hotkey)
        form.setContentsMargins(12, 14, 12, 10)
        form.setSpacing(8)
        self.hotkey_edit = HotkeyCapture(box_hotkey)
        self.hotkey_edit.setText(s.hotkey)
        form.addRow("召唤快捷键", self.hotkey_edit)

        self.hotkey_alt_edit = HotkeyCapture(box_hotkey)
        self.hotkey_alt_edit.setText(getattr(s, "hotkey_alt", "") or "")
        form.addRow("备用快捷键", self.hotkey_alt_edit)

        self.hotkey_status_label = QLabel("状态：—", box_hotkey)
        self.hotkey_status_label.setObjectName("hint")
        self.hotkey_status_label.setWordWrap(True)
        form.addRow("", self.hotkey_status_label)

        hint = QLabel(
            "点击输入框后直接按下组合键；建议包含 Ctrl 或 Alt（Win 组合键多被系统保留）。\n"
            "若提示被占用，换一个组合即可；备用快捷键可同时注册两套，任意一套都能召唤。\n"
            "召唤失败时也可以直接点击托盘图标唤出窗口。",
            box_hotkey,
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        form.addRow("", hint)
        root.addWidget(box_hotkey)

        # ---------------- 外观
        box_look = QGroupBox("外观", self)
        look = QFormLayout(box_look)
        look.setContentsMargins(12, 14, 12, 10)
        look.setSpacing(8)
        self.theme_combo = QComboBox(box_look)
        self.theme_combo.addItem("浅色", "light")
        self.theme_combo.addItem("深色", "dark")
        self.theme_combo.setCurrentIndex(1 if s.theme == "dark" else 0)
        look.addRow("主题", self.theme_combo)

        self.font_spin = QSpinBox(box_look)
        self.font_spin.setRange(11, 22)
        self.font_spin.setValue(s.font_size)
        self.font_spin.setSuffix(" px")
        look.addRow("正文字号", self.font_spin)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal, box_look)
        self.opacity_slider.setRange(50, 100)
        self.opacity_slider.setValue(s.opacity)
        self.opacity_label = QLabel(f"{s.opacity}%", box_look)
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
        row = QHBoxLayout()
        row.addWidget(self.opacity_slider, 1)
        row.addWidget(self.opacity_label)
        container = QWidget(box_look)
        container.setLayout(row)
        look.addRow("窗口不透明度", container)
        root.addWidget(box_look)

        # ---------------- 行为
        box_behavior = QGroupBox("行为", self)
        behavior = QFormLayout(box_behavior)
        behavior.setContentsMargins(12, 14, 12, 10)
        behavior.setSpacing(8)
        self.per_page_spin = QSpinBox(box_behavior)
        self.per_page_spin.setRange(3, 50)
        self.per_page_spin.setValue(s.per_page)
        self.per_page_spin.setSuffix(" 条/页")
        behavior.addRow("每页显示", self.per_page_spin)

        self.chk_top = QCheckBox("窗口始终悬浮在最上层", box_behavior)
        self.chk_top.setChecked(s.always_on_top)
        behavior.addRow("", self.chk_top)

        self.chk_pinned_first = QCheckBox("置顶便签排在最前面", box_behavior)
        self.chk_pinned_first.setChecked(s.show_pinned_first)
        behavior.addRow("", self.chk_pinned_first)

        self.chk_outside = QCheckBox("点击窗口外部时自动隐藏", box_behavior)
        self.chk_outside.setChecked(s.hide_on_outside_click)
        behavior.addRow("", self.chk_outside)

        self.chk_confirm = QCheckBox("删除便签前先确认", box_behavior)
        self.chk_confirm.setChecked(s.confirm_delete)
        behavior.addRow("", self.chk_confirm)
        root.addWidget(box_behavior)

        # ---------------- 系统 / 数据
        box_sys = QGroupBox("系统与数据", self)
        sysl = QFormLayout(box_sys)
        sysl.setContentsMargins(12, 14, 12, 10)
        sysl.setSpacing(8)
        self.chk_autostart = QCheckBox("开机自动启动", box_sys)
        self.chk_autostart.setChecked(is_autostart_enabled())
        sysl.addRow("", self.chk_autostart)

        path_label = QLabel(str(data_file()), box_sys)
        path_label.setObjectName("hint")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        sysl.addRow("数据文件", path_label)

        btn_row = QHBoxLayout()
        self.btn_open_dir = QPushButton("打开文件夹", box_sys)
        self.btn_export = QPushButton("导出分享包…", box_sys)
        self.btn_import = QPushButton("导入分享包…", box_sys)
        self.btn_open_dir.clicked.connect(self._open_dir)
        self.btn_export.clicked.connect(self._export)
        self.btn_import.clicked.connect(self._import)
        btn_row.addWidget(self.btn_open_dir)
        btn_row.addWidget(self.btn_export)
        btn_row.addWidget(self.btn_import)
        holder = QWidget(box_sys)
        holder.setLayout(btn_row)
        sysl.addRow("", holder)

        share_hint = QLabel(
            "分享包是一个 JSON 文件，发给别人后对方用「导入分享包」即可把你的便签集合合并进去"
            "（重复内容会自动跳过）。适合小团队互相分享模板、清单、常用话术等。",
            box_sys,
        )
        share_hint.setObjectName("hint")
        share_hint.setWordWrap(True)
        sysl.addRow("", share_hint)
        root.addWidget(box_sys)

        root.addStretch(1)

        # ---------------- 按钮
        btn_bar = QHBoxLayout()
        btn_bar.setContentsMargins(0, 0, 0, 0)
        btn_reset = QPushButton("恢复默认", self)
        btn_reset.clicked.connect(self._reset_defaults)
        btn_bar.addWidget(btn_reset)
        btn_bar.addStretch(1)
        btn_cancel = QPushButton("取消", self)
        btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton("保存", self)
        btn_ok.setObjectName("primary")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._accept)
        btn_bar.addWidget(btn_cancel)
        btn_bar.addWidget(btn_ok)
        root.addLayout(btn_bar)

    # ------------------------------------------------------------------ 动作
    def _reset_defaults(self) -> None:
        from .config import DEFAULT_SETTINGS

        self.hotkey_edit.setText(str(DEFAULT_SETTINGS["hotkey"]))
        self.hotkey_alt_edit.setText("")
        self.theme_combo.setCurrentIndex(0)
        self.font_spin.setValue(int(DEFAULT_SETTINGS["font_size"]))
        self.opacity_slider.setValue(int(DEFAULT_SETTINGS["opacity"]))
        self.per_page_spin.setValue(int(DEFAULT_SETTINGS["per_page"]))
        self.chk_top.setChecked(bool(DEFAULT_SETTINGS["always_on_top"]))
        self.chk_pinned_first.setChecked(bool(DEFAULT_SETTINGS["show_pinned_first"]))
        self.chk_outside.setChecked(bool(DEFAULT_SETTINGS["hide_on_outside_click"]))
        self.chk_confirm.setChecked(bool(DEFAULT_SETTINGS["confirm_delete"]))

    def _open_dir(self) -> None:
        path = app_data_dir()
        try:
            import subprocess

            subprocess.Popen(["explorer", str(path)])
        except OSError:
            pass

    @staticmethod
    def _reveal(target: Path) -> None:
        """在文件管理器中定位到指定文件。"""
        try:
            if sys.platform == "win32":
                subprocess.Popen(["explorer", "/select,", str(target)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target.parent)])
        except OSError:
            pass

    def _export(self) -> None:
        title, ok = QInputDialog.getText(
            self, "导出分享包", "给这份便签集起个名字：", text="我的便签集"
        )
        if not ok:
            return
        author, ok2 = QInputDialog.getText(
            self, "导出分享包", "分享者（可留空）：", text=os.environ.get("USERNAME", "")
        )
        if not ok2:
            author = ""
        stamp = time.strftime("%Y%m%d")
        safe = "".join(c for c in title if c not in r'\/:*?"<>|').strip() or "便签集"
        default = str(Path.home() / f"{safe}-{stamp}.json")
        path, _ = QFileDialog.getSaveFileName(self, "导出分享包", default, "JSON 文件 (*.json)")
        if not path:
            return
        ok = self.store.export_to(Path(path), title=title, author=author)
        if not ok:
            QMessageBox.information(self, "导出", "导出失败，请检查路径权限。")
            return

        n = len(self.store.notes)
        if n == 0:
            QMessageBox.warning(
                self,
                "导出",
                f"已导出，但当前便签是空的（0 条）。\n\n"
                f"分享包文件里没有任何内容，别人导入后也是空的。\n"
                f"请先在便签窗口里添加几条便签，再来导出。\n\n文件位置：\n{path}",
            )
            return

        box = QMessageBox(self)
        box.setWindowTitle("导出成功")
        box.setIcon(QMessageBox.Icon.Information)
        box.setText(f"已导出 {n} 条便签。")
        box.setInformativeText(
            f"文件位置：\n{path}\n\n"
            f"接下来：\n"
            f"· 想发给朋友 → 把这个 JSON 文件发给他，他用「导入分享包」即可\n"
            f"· 想放到网上集市 → 打开便签集市页面，选择这个文件上传\n"
            f"（注意：集市上传需要登录 WorkBuddy 账号）"
        )
        open_btn = box.addButton("打开所在文件夹", QMessageBox.ButtonRole.ActionRole)
        box.addButton("知道了", QMessageBox.ButtonRole.AcceptRole)
        box.exec()
        if box.clickedButton() is open_btn:
            self._reveal(Path(path))

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入分享包", str(Path.home()), "JSON 文件 (*.json)")
        if not path:
            return
        meta, notes = self.store.read_share(Path(path))
        if not notes:
            QMessageBox.warning(self, "导入", "这个文件里没有可导入的便签。")
            return
        info = f"《{meta.get('title', '未命名')}》"
        if meta.get("author"):
            info += f"　来自：{meta['author']}"
        if meta.get("exported_at"):
            info += f"　导出于：{meta['exported_at']}"
        info += f"\n共 {len(notes)} 条便签。\n\n要合并到你现在的便签里吗？（内容与 ID 重复的会自动跳过）"
        if not confirm(self, "导入分享包", info, "合并导入", "取消",
                       QMessageBox.Icon.Question):
            return
        added, skipped = self.store.import_notes(
            notes, meta.get("_tags"), meta.get("_tag_groups")
        )
        QMessageBox.information(self, "导入", f"已新增 {added} 条，跳过重复 {skipped} 条。")

    def _accept(self) -> None:
        combo = self.hotkey_edit.text().strip()
        if combo and not combo_is_valid(combo):
            QMessageBox.warning(
                self,
                "快捷键无效",
                "快捷键需要包含一个主按键，并且至少要带 Ctrl、Alt 或 Win 中的一个修饰键。",
            )
            return
        alt = self.hotkey_alt_edit.text().strip()
        if alt and not combo_is_valid(alt):
            QMessageBox.warning(self, "备用快捷键无效", "备用快捷键同样需要带 Ctrl / Alt / Win 修饰键。")
            return
        tip = combo_hint(combo) or combo_hint(alt)
        if tip:
            if not confirm(self, "这个快捷键可能按不出来",
                           tip + "。\n\n仍然要保存吗？（推荐改成 Ctrl+Alt+X 这类三键组合）",
                           "仍然保存", "回去修改", QMessageBox.Icon.Warning):
                return
        set_autostart(self.chk_autostart.isChecked())
        self.accept()

    # ------------------------------------------------------------------ 结果
    def result_settings(self) -> Settings:
        s = self.store.settings
        combo = self.hotkey_edit.text().strip()
        s.hotkey = combo or s.hotkey
        s.hotkey_alt = self.hotkey_alt_edit.text().strip()
        s.theme = self.theme_combo.currentData() or "light"
        s.font_size = self.font_spin.value()
        s.opacity = self.opacity_slider.value()
        s.per_page = self.per_page_spin.value()
        s.always_on_top = self.chk_top.isChecked()
        s.show_pinned_first = self.chk_pinned_first.isChecked()
        s.hide_on_outside_click = self.chk_outside.isChecked()
        s.confirm_delete = self.chk_confirm.isChecked()
        s.autostart = is_autostart_enabled()
        return s
