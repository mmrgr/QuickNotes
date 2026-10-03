"""悬浮便签主窗口。"""

from __future__ import annotations

import math
import os
import time

from PyQt6.QtCore import QEvent, Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QCursor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QInputDialog,
    QScrollArea,
    QSizeGrip,
    QSystemTrayIcon,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import APP_TITLE
from .hotkey import HotkeyManager, combo_hint, force_foreground, foreground_hwnd
from .settings_dialog import SettingsDialog
from .theme import build_stylesheet
from .storage import Store
from .widgets import DragBar, EmptyHint, NoteCard, Pager, confirm, make_tool_button


class MainWindow(QWidget):
    """一个无边框、始终置顶、可用全局热键召唤的便签窗口。"""

    def __init__(self, store: Store, hotkey: HotkeyManager):
        super().__init__()
        self.store = store
        self.hotkey = hotkey
        self._query = ""
        self._active_tag_id: str | None = None
        self._active_group_id: str | None = None
        self._tag_panel_signature = None
        self._notes = []
        self._cards: dict[str, NoteCard] = {}
        self._page = 1
        self._page_cooldown = 0.0
        self._outside_since: float | None = None
        self._shown_at = 0.0
        self._risk_warned = False
        self._tray = None
        self._settings_dialog = None

        self.setWindowTitle(APP_TITLE)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)

        self._build_ui()
        self._build_tray()

        # 先连信号再应用设置，保证首次注册热键的状态也能被记录/显示
        self.hotkey.activated.connect(self.toggle_window)
        self.hotkey.registrationFailed.connect(self._on_hotkey_failed)
        self.hotkey.statusChanged.connect(self._on_hotkey_status)

        self.apply_settings()

        self.store.on_change = self._on_store_changed
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(700)
        self._save_timer.timeout.connect(self._save_now)

        self._fg_timer = QTimer(self)
        self._fg_timer.setInterval(400)
        self._fg_timer.timeout.connect(self._check_foreground)
        self._fg_timer.start()

        self.reload()

    def _on_hotkey_status(self, text: str, ok: bool) -> None:
        from .log import log

        log(f"hotkey status: {text}")
        combo = self.store.settings.hotkey
        tip = f"{APP_TITLE}\n召唤快捷键：{combo}\n状态：{text}"
        if self._tray is not None:
            self._tray.setToolTip(tip)

        # 用了容易冲突的组合时提醒一次（例如 Ctrl+F 会被前台软件的"查找"抢走）
        if ok and not self._risk_warned:
            hint = combo_hint(combo)
            if hint and self._tray is not None:
                self._risk_warned = True
                QTimer.singleShot(
                    1500,
                    lambda: self._tray.showMessage(
                        APP_TITLE,
                        f"当前快捷键 {combo}：{hint}。可在设置里换成 Ctrl+Alt+X 这类组合。",
                        QSystemTrayIcon.MessageIcon.Information,
                        8000,
                    ),
                )

    # ------------------------------------------------------------------ 界面
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(0)

        self.panel = QWidget(self)
        self.panel.setObjectName("panel")
        outer.addWidget(self.panel)

        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(22)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 90))
        self.panel.setGraphicsEffect(shadow)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(0)

        # 标题栏
        header = DragBar(self, self.panel)
        header.setObjectName("header")
        header.setFixedHeight(42)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(14, 0, 10, 0)
        hlayout.setSpacing(6)

        self.title_label = QLabel(APP_TITLE, header)
        self.title_label.setObjectName("title")
        hlayout.addWidget(self.title_label)

        self.count_label = QLabel("", header)
        self.count_label.setObjectName("count")
        hlayout.addWidget(self.count_label)
        hlayout.addStretch(1)

        self.btn_new = self._icon_button(header, "＋", "新建便签 (Ctrl+N)", self.new_note)
        self.btn_tags = self._icon_button(header, "🏷", "标签筛选与用法", self._show_tag_help)
        self.btn_settings = self._icon_button(header, "⚙", "设置", self.open_settings)
        self.btn_hide = self._icon_button(header, "✕", "隐藏窗口 (Esc)", self.hide_window)
        self.btn_hide.setObjectName("closebtn")
        for btn in (self.btn_new, self.btn_tags, self.btn_settings, self.btn_hide):
            hlayout.addWidget(btn)
        panel_layout.addWidget(header)

        # 搜索行
        search_row = QWidget(self.panel)
        search_layout = QHBoxLayout(search_row)
        search_layout.setContentsMargins(12, 0, 12, 8)
        search_layout.setSpacing(6)
        self.search_edit = QLineEdit(search_row)
        self.search_edit.setObjectName("search")
        self.search_edit.setPlaceholderText("搜索便签内容…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search_changed)
        search_layout.addWidget(self.search_edit, 1)
        panel_layout.addWidget(search_row)

        # 标签筛选栏：标签按类型分组，类型和标签都可以点击筛选，类型可折叠。
        self.tag_panel = QWidget(self.panel)
        self.tag_panel.setObjectName("tagPanel")
        self.tag_panel_layout = QVBoxLayout(self.tag_panel)
        self.tag_panel_layout.setContentsMargins(12, 0, 12, 8)
        self.tag_panel_layout.setSpacing(3)
        self.tag_panel.setMaximumHeight(150)
        panel_layout.addWidget(self.tag_panel)
        self.tag_panel.hide()

        # 便签区
        body = QWidget(self.panel)
        body.setObjectName("panelBody")
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.scroll = QScrollArea(body)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.installEventFilter(self)

        self.list_widget = QWidget()
        self.list_widget.setObjectName("panelBody")
        self.list_layout = QVBoxLayout(self.list_widget)
        self.list_layout.setContentsMargins(10, 8, 10, 8)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch(1)
        self.scroll.setWidget(self.list_widget)
        body_layout.addWidget(self.scroll, 1)
        panel_layout.addWidget(body, 1)

        # 底部分页
        footer = QWidget(self.panel)
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 2, 4, 4)
        footer_layout.setSpacing(4)
        self.pager = Pager(footer)
        self.pager.pageChanged.connect(self.go_page)
        footer_layout.addWidget(self.pager, 1)
        self.pageinfo_label = QLabel("", footer)
        self.pageinfo_label.setObjectName("muted")
        footer_layout.addWidget(self.pageinfo_label)
        grip = QSizeGrip(footer)
        grip.setFixedSize(16, 16)
        footer_layout.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        panel_layout.addWidget(footer)

        # 窗口内快捷键
        QShortcut(QKeySequence("Esc"), self, self.hide_window, context=Qt.ShortcutContext.WindowShortcut)
        QShortcut(QKeySequence("Ctrl+N"), self, self.new_note, context=Qt.ShortcutContext.WindowShortcut)
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search, context=Qt.ShortcutContext.WindowShortcut)
        QShortcut(QKeySequence("Alt+Left"), self, self.prev_page, context=Qt.ShortcutContext.WindowShortcut)
        QShortcut(QKeySequence("Alt+Right"), self, self.next_page, context=Qt.ShortcutContext.WindowShortcut)

    def _clear_tag_panel(self) -> None:
        while self.tag_panel_layout.count():
            item = self.tag_panel_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _refresh_tag_panel(self) -> None:
        signature = tuple(
            (group.id, group.name, group.collapsed,
             tuple((tag.id, tag.name) for tag in self.store.tags_for_group(group.id)))
            for group in self.store.tag_groups
        )
        signature = (signature, self._active_tag_id, self._active_group_id)
        if signature == self._tag_panel_signature:
            return
        self._tag_panel_signature = signature
        self._clear_tag_panel()
        if not self.store.tags:
            self.tag_panel.hide()
            return
        self.tag_panel.show()

        top = QWidget(self.tag_panel)
        top_layout = QHBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(4)
        label = QLabel("标签类型", top)
        label.setObjectName("muted")
        top_layout.addWidget(label)
        all_btn = QToolButton(top)
        all_btn.setObjectName("pagebtn")
        all_btn.setText("全部")
        all_btn.setToolTip("清除标签筛选")
        all_btn.clicked.connect(self._clear_tag_filter)
        top_layout.addWidget(all_btn)
        hint = QLabel("便签底部可输入 标签 或 类型/标签", top)
        hint.setObjectName("muted")
        top_layout.addWidget(hint)
        top_layout.addStretch(1)
        self.tag_panel_layout.addWidget(top)

        for group in self.store.tag_groups:
            tags = self.store.tags_for_group(group.id)
            if not tags:
                continue
            header = QWidget(self.tag_panel)
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 0, 0, 0)
            header_layout.setSpacing(2)
            collapse = QToolButton(header)
            collapse.setObjectName("pagebtn")
            collapse.setText("▸" if group.collapsed else "▾")
            collapse.setToolTip("展开类型" if group.collapsed else "折叠类型")
            collapse.clicked.connect(lambda _=False, gid=group.id: self._toggle_tag_group(gid))
            header_layout.addWidget(collapse)
            group_btn = QToolButton(header)
            group_btn.setObjectName("pagebtn")
            group_btn.setText(f"{group.name} ({len(tags)})")
            group_btn.setToolTip("查看此类型下的全部便签；右键管理类型")
            group_btn.setProperty("current", "true" if self._active_group_id == group.id else "false")
            group_btn.clicked.connect(lambda _=False, gid=group.id: self._select_group(gid))
            group_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            group_btn.customContextMenuRequested.connect(
                lambda pos, gid=group.id, btn=group_btn: self._group_menu(gid, btn.mapToGlobal(pos))
            )
            header_layout.addWidget(group_btn)
            header_layout.addStretch(1)
            self.tag_panel_layout.addWidget(header)

            tags_row = QWidget(self.tag_panel)
            tags_layout = QHBoxLayout(tags_row)
            tags_layout.setContentsMargins(24, 0, 0, 2)
            tags_layout.setSpacing(3)
            for tag in tags:
                btn = QToolButton(tags_row)
                btn.setObjectName("pagebtn")
                btn.setText(tag.name)
                btn.setToolTip(f"筛选标签：{tag.name}")
                btn.setProperty("current", "true" if self._active_tag_id == tag.id else "false")
                btn.clicked.connect(lambda _=False, tid=tag.id: self._select_tag(tid))
                tags_layout.addWidget(btn)
            tags_layout.addStretch(1)
            tags_row.setVisible(not group.collapsed)
            self.tag_panel_layout.addWidget(tags_row)

        self.tag_panel.adjustSize()

    def _select_tag(self, tag_id: str) -> None:
        self._active_tag_id = None if self._active_tag_id == tag_id else tag_id
        self._active_group_id = None
        self._page = 1
        self.reload()

    def _select_group(self, group_id: str) -> None:
        self._active_group_id = None if self._active_group_id == group_id else group_id
        self._active_tag_id = None
        self._page = 1
        self.reload()

    def _clear_tag_filter(self) -> None:
        self._active_tag_id = None
        self._active_group_id = None
        self._page = 1
        self.reload()

    def _toggle_tag_group(self, group_id: str) -> None:
        group = self.store.group_by_id(group_id)
        if group is None:
            return
        self.store.set_group_collapsed(group_id, not group.collapsed)
        self._schedule_save()
        self._refresh_tag_panel()

    def _group_menu(self, group_id: str, global_pos) -> None:
        menu = QMenu(self)
        rename = menu.addAction("重命名类型…")
        delete = menu.addAction("删除类型（标签移到未分类）")
        action = menu.exec(global_pos)
        if action is rename:
            group = self.store.group_by_id(group_id)
            if group is None:
                return
            name, ok = QInputDialog.getText(self, "重命名标签类型", "类型名称：", text=group.name)
            if ok and name.strip() and self.store.rename_group(group_id, name):
                self._save_now()
                self.reload()
        elif action is delete:
            if confirm(self, "删除标签类型", "删除类型后，其中的标签会移到“未分类”，确定继续吗？", "删除", "取消"):
                self.store.delete_group(group_id)
                if self._active_group_id == group_id:
                    self._active_group_id = None
                self._save_now()
                self.reload()

    def _show_tag_help(self) -> None:
        QMessageBox.information(
            self,
            "标签用法",
            "在每张便签底部输入标签，多个标签用逗号分隔。\n"
            "使用“类型/标签”（例如“项目/客户端”）即可归入标签类型。\n"
            "点击顶部的类型或标签可筛选；点击 ▾ / ▸ 可折叠类型。\n"
            "类型标题右键可以重命名或删除。",
        )

    def _icon_button(self, parent, text: str, tip: str, slot) -> QToolButton:
        return make_tool_button(parent, text, tip, slot, "iconbtn")

    # ------------------------------------------------------------------ 托盘
    def _build_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self._make_tray_icon(), self)
        self._tray.setToolTip(APP_TITLE)
        menu = self._tray_menu()
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(lambda reason: self.toggle_window()
                                     if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self._tray.show()

    def _tray_menu(self) -> QMenu:
        menu = QMenu()
        act_toggle = QAction("显示 / 隐藏", self)
        act_toggle.triggered.connect(self.toggle_window)
        act_new = QAction("新建便签", self)
        act_new.triggered.connect(self.new_note)
        act_settings = QAction("设置…", self)
        act_settings.triggered.connect(self.open_settings)
        act_quit = QAction("退出", self)
        act_quit.triggered.connect(QApplication.quit)
        menu.addAction(act_toggle)
        menu.addAction(act_new)
        menu.addAction(act_settings)
        menu.addSeparator()
        menu.addAction(act_quit)
        return menu

    @staticmethod
    def _make_tray_icon() -> QIcon:
        size = 64
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#2f6feb"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(10, 8, 44, 48, 8, 8)
        painter.setBrush(QColor("#ffffff"))
        for i, y in enumerate((22, 32, 42)):
            painter.drawRoundedRect(18, y, 28 - i * 4, 4, 2, 2)
        painter.end()
        return QIcon(pix)

    # ------------------------------------------------------------------ 设置
    def apply_settings(self) -> None:
        s = self.store.settings
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(s))
        font = QFont("Microsoft YaHei UI", s.font_size)
        self.setFont(font)
        self.setWindowOpacity(max(0.4, s.opacity / 100.0))

        # 只在窗口标志真正变化时才重设：setWindowFlags 会重建窗口句柄
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if s.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if flags != self.windowFlags():
            was_visible = self.isVisible()
            self.setWindowFlags(flags)
            if was_visible:
                self.show()

        self.resize(s.width, s.height)
        if s.pos:
            try:
                x, y = int(s.pos[0]), int(s.pos[1])
                self._move_to(x, y)
            except (ValueError, TypeError, IndexError):
                self._center_on_screen()
        else:
            self._center_on_screen()

        # 热键挂在独立的消息窗口上，不受主窗口句柄变化影响
        self._hwnd = int(self.winId())
        self._register_hotkeys()

    def _register_hotkeys(self) -> None:
        s = self.store.settings
        combos = [s.hotkey]
        if s.hotkey_alt:
            combos.append(s.hotkey_alt)
        self.hotkey.register_all(combos)

    def _center_on_screen(self) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.center().x() - self.width() // 2
        y = geo.center().y() - self.height() // 2
        self._move_to(x, y)

    def _move_to(self, x: int, y: int) -> None:
        screen = QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        if screen is not None:
            geo = screen.availableGeometry()
            x = max(geo.left(), min(x, geo.right() - self.width()))
            y = max(geo.top(), min(y, geo.bottom() - self.height()))
        self.move(x, y)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.store, self.hotkey, self)
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return
        self.store.settings = dialog.result_settings()
        self.apply_settings()
        self.reload()
        self._save_now()
        if not self.hotkey.ok:
            self._on_hotkey_failed(self.hotkey.status)

    def _on_hotkey_failed(self, message: str) -> None:
        from .log import log

        log("hotkey: " + message)
        if self._tray is not None:
            self._tray.showMessage(APP_TITLE, message + "（可在设置里换一个组合）",
                                   QSystemTrayIcon.MessageIcon.Warning, 6000)

    # ------------------------------------------------------------------ 显隐
    def toggle_window(self) -> None:
        if self.isVisible():
            self.hide_window()
        else:
            self.show_window()

    def show_window(self) -> None:
        s = self.store.settings
        if s.pos:
            try:
                self._move_to(int(s.pos[0]), int(s.pos[1]))
            except (ValueError, TypeError, IndexError):
                pass
        self.setWindowOpacity(max(0.4, s.opacity / 100.0))
        self.reload()
        self.show()
        self.raise_()
        self.activateWindow()
        QApplication.setActiveWindow(self)
        # Qt 在"桌面/全屏程序"为前台时常常抢不到焦点，补一次 Win32 前台切换，
        # 否则下面的"点击外部自动隐藏"会在窗口刚出现时就把它收起来
        force_foreground(int(self.winId()))
        self.setFocus()
        self._shown_at = time.time()
        self._outside_since = None

    def hide_window(self) -> None:
        if not self.isVisible():
            return
        s = self.store.settings
        s.pos = [self.x(), self.y()]
        s.width = self.width()
        s.height = self.height()
        self._save_now()
        self.hide()

    def closeEvent(self, event):  # noqa: N802
        self.hide_window()
        event.ignore()

    # ------------------------------------------------------------------ 数据
    def _on_store_changed(self) -> None:
        self._save_timer.start()

    def _save_now(self) -> None:
        self.store.save()

    def _schedule_save(self) -> None:
        self._save_timer.start()

    # ------------------------------------------------------------------ 渲染
    def reload(self, keep_page: bool = True) -> None:
        s = self.store.settings
        self._notes = self.store.visible_notes(self._query, self._active_tag_id, self._active_group_id)
        per_page = max(1, s.per_page)
        self._total_pages = max(1, math.ceil(len(self._notes) / per_page))
        if not keep_page:
            self._page = 1
        self._page = max(1, min(self._page, self._total_pages))
        self._refresh_tag_panel()
        self._render_page()
        self._update_header()

    def _update_header(self) -> None:
        total = len(self._notes)
        all_count = len(self.store.notes)
        if self._query or self._active_tag_id or self._active_group_id:
            self.count_label.setText(f"{total} / {all_count} 条")
        else:
            self.count_label.setText(f"{all_count} 条")
        self.pager.set_pages(self._total_pages, self._page)
        self.pageinfo_label.setText(
            f"第 {self._page}/{self._total_pages} 页 · 每页 {self.store.settings.per_page} 条"
        )

    def _clear_list(self) -> None:
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._cards.clear()

    def _render_page(self) -> None:
        self._clear_list()
        s = self.store.settings
        start = (self._page - 1) * s.per_page
        chunk = self._notes[start : start + s.per_page]
        for note in chunk:
            card = NoteCard(note, self.list_widget, self.store.note_tag_names(note))
            card.textEdited.connect(self._on_text_edited)
            card.pinRequested.connect(self._on_pin)
            card.deleteRequested.connect(self._on_delete)
            card.copyRequested.connect(self._on_copy)
            card.moveRequested.connect(self._on_move)
            card.tagsEdited.connect(self._on_tags_edited)
            self.list_layout.addWidget(card)
            self._cards[note.id] = card
        if not chunk:
            if self._query:
                empty_text = f"没有找到包含 “{self._query}” 的便签"
            elif self._active_tag_id or self._active_group_id:
                empty_text = "当前标签类型下没有便签"
            else:
                empty_text = "还没有便签\n点击右上角的 ＋ 新建一条"
            hint = EmptyHint(empty_text, self.list_widget)
            self.list_layout.addWidget(hint)
        self.list_layout.addStretch(1)
        self.list_widget.updateGeometry()

    def prev_page(self) -> None:
        self.go_page(self._page - 1, "bottom")

    def next_page(self) -> None:
        self.go_page(self._page + 1, "top")

    def go_page(self, page: int, scroll_to: str = "top") -> None:
        target = max(1, min(int(page), self._total_pages))
        if target == self._page:
            self._scroll_edge(scroll_to)
            return
        self._page = target
        self._render_page()
        self._update_header()
        QTimer.singleShot(0, lambda: self._scroll_edge(scroll_to))

    def _scroll_edge(self, where: str) -> None:
        sb = self.scroll.verticalScrollBar()
        sb.setValue(sb.maximum() if where == "bottom" else 0)

    # ------------------------------------------------------------------ 交互
    def _on_text_edited(self, note_id: str, text: str) -> None:
        self.store.update_text(note_id, text)
        self._schedule_save()

    def _on_pin(self, note_id: str) -> None:
        self.store.toggle_pin(note_id)
        self.reload()
        self._save_now()

    def _on_delete(self, note_id: str) -> None:
        if self.store.settings.confirm_delete:
            if not confirm(self, "删除便签", "确定要删除这条便签吗？", "删除", "取消",
                           QMessageBox.Icon.Question):
                return
        self.store.delete(note_id)
        self.reload()
        self._save_now()

    def _on_copy(self, note_id: str) -> None:
        note = self.store.get(note_id)
        if note:
            QApplication.clipboard().setText(note.text)

    def _on_move(self, note_id: str, delta: int) -> None:
        if self.store.move(note_id, delta):
            self.reload()
            self._save_now()

    def _on_search_changed(self, text: str) -> None:
        self._query = text.strip()
        self._page = 1
        self.reload()

    def _on_tags_edited(self, note_id: str, text: str) -> None:
        self.store.set_note_tags(note_id, text)
        self.reload()
        self._save_now()

    def _focus_search(self) -> None:
        if not self.isVisible():
            self.show_window()
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    def new_note(self) -> None:
        if not self.isVisible():
            self.show_window()
        # 先清掉历史遗留的空白便签，避免越积越多
        self._prune_empty()
        note = self.store.add("")
        self._page = 1
        self.reload()
        QTimer.singleShot(0, lambda: self._focus_card(note.id))
        self._save_now()

    def _prune_empty(self) -> None:
        before = len(self.store.notes)
        self.store.notes = [n for n in self.store.notes if n.text.strip()]
        if len(self.store.notes) != before:
            self._schedule_save()

    def _focus_card(self, note_id: str) -> None:
        card = self._cards.get(note_id)
        if card is not None:
            self.scroll.ensureWidgetVisible(card)
            card.set_editor_focus()

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Type.Wheel and obj in (self.scroll, self.scroll.viewport()):
            if self._handle_page_wheel(event):
                return True
        return super().eventFilter(obj, event)

    def _handle_page_wheel(self, event) -> bool:
        """滚到当前页顶部继续上滚 -> 上一页；滚到底部继续下滚 -> 下一页。"""
        delta = event.angleDelta().y()
        if delta == 0:
            return False
        sb = self.scroll.verticalScrollBar()
        now = time.time()
        if now - self._page_cooldown < 0.28:
            return False
        if delta < 0 and sb.value() >= sb.maximum():
            if self._page < self._total_pages:
                self._page_cooldown = now
                self.go_page(self._page + 1, "top")
                return True
        elif delta > 0 and sb.value() <= sb.minimum():
            if self._page > 1:
                self._page_cooldown = now
                self.go_page(self._page - 1, "bottom")
                return True
        return False

    def _check_foreground(self) -> None:
        if not self.isVisible() or not self.store.settings.hide_on_outside_click:
            self._outside_since = None
            return
        # 刚召唤出来的 1.5 秒内不判断，避免"抢焦点失败 -> 立刻自动隐藏"导致唤不出来
        if time.time() - getattr(self, "_shown_at", 0.0) < 1.5:
            self._outside_since = None
            return
        if QApplication.activeModalWidget() is not None:
            self._outside_since = None
            return
        hwnd = foreground_hwnd()
        if not hwnd:
            self._outside_since = None
            return
        if hwnd and hwnd != getattr(self, "_hwnd", 0):
            if self._outside_since is None:
                self._outside_since = time.time()
            elif time.time() - self._outside_since > 0.7:
                self.hide_window()
        else:
            self._outside_since = None

    def moveEvent(self, event):  # noqa: N802
        super().moveEvent(event)
        self.store.settings.pos = [self.x(), self.y()]

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        s = self.store.settings
        s.width = self.width()
        s.height = self.height()
        for card in self._cards.values():
            card.editor.updateGeometry()
