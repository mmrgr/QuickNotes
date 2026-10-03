"""界面用到的自定义小部件：可拖拽标题栏、便签卡片、自动增高编辑器、分页器。"""

from __future__ import annotations

import time

from PyQt6.QtCore import QEvent, QPoint, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)


def confirm(parent, title: str, text: str, yes_text: str = "确定",
            no_text: str = "取消", icon=None) -> bool:
    """统一的「是 / 否」确认弹窗，返回用户是否点了「是」。

    icon 传 QMessageBox.Icon.Question 或 QMessageBox.Icon.Warning，默认 Question。
    """
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon if icon is not None else QMessageBox.Icon.Question)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    box.button(QMessageBox.StandardButton.Yes).setText(yes_text)
    box.button(QMessageBox.StandardButton.No).setText(no_text)
    box.setDefaultButton(QMessageBox.StandardButton.No)
    return box.exec() == QMessageBox.StandardButton.Yes


def format_time(ts: float) -> str:
    diff = time.time() - ts
    if diff < 60:
        return "刚刚"
    if diff < 3600:
        return f"{int(diff // 60)} 分钟前"
    if diff < 86400 and time.localtime(ts).tm_yday == time.localtime().tm_yday:
        return time.strftime("今天 %H:%M", time.localtime(ts))
    if diff < 86400 * 2:
        return time.strftime("昨天 %H:%M", time.localtime(ts))
    if time.localtime(ts).tm_year == time.localtime().tm_year:
        return time.strftime("%m-%d %H:%M", time.localtime(ts))
    return time.strftime("%Y-%m-%d", time.localtime(ts))


class DragBar(QFrame):
    """可拖动窗口的标题栏。"""

    def __init__(self, window: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._window = window
        self._dragging = False
        self._offset = QPoint()
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._offset = event.globalPosition().toPoint() - self._window.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # noqa: N802
        if self._dragging:
            self._window.move(event.globalPosition().toPoint() - self._offset)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._dragging = False
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)


class NoteEditor(QPlainTextEdit):
    """随内容自动增高、滚轮透传给外层滚动区的多行输入框。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("notetext")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setTabChangesFocus(True)
        self.document().setDocumentMargin(2)
        self.textChanged.connect(self._fit_height)
        self._cached_height = 0

    def _content_height(self) -> int:
        fm = QFontMetrics(self.font())
        line_h = fm.lineSpacing()
        doc_h = int(self.document().size().height())
        return max(line_h + 4, doc_h + 6)

    def _fit_height(self) -> None:
        h = self._content_height()
        if h != self._cached_height:
            self._cached_height = h
            self.setMinimumHeight(h)
            self.updateGeometry()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._cached_height = 0
        self._fit_height()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(super().sizeHint().width(), self._content_height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(60, self._content_height())

    def wheelEvent(self, event):  # noqa: N802
        # 内容不需要内部滚动时把滚轮交给外层滚动区，保证整页滚动流畅
        if self.verticalScrollBar().maximum() == 0:
            event.ignore()
        else:
            super().wheelEvent(event)


def make_tool_button(parent, text: str, tip: str, slot, name: str = "cardbtn") -> QToolButton:
    """创建一个统一样式的小图标按钮（objectName 决定样式，见 theme.py）。"""
    btn = QToolButton(parent)
    btn.setObjectName(name)
    btn.setText(text)
    btn.setToolTip(tip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.clicked.connect(slot)
    return btn


class NoteCard(QFrame):
    """一张便签卡片。"""

    textEdited = pyqtSignal(str, str)      # note_id, text
    pinRequested = pyqtSignal(str)
    deleteRequested = pyqtSignal(str)
    copyRequested = pyqtSignal(str)
    moveRequested = pyqtSignal(str, int)
    focusChanged = pyqtSignal(str, bool)
    tagsEdited = pyqtSignal(str, str)       # note_id, comma-separated names

    def __init__(self, note, parent: QWidget | None = None, tag_names: list[str] | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.note = note
        self._suppress = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 6)
        layout.setSpacing(4)

        self.editor = NoteEditor(self)
        self._suppress = True
        self.editor.setPlainText(note.text)
        self._suppress = False
        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.installEventFilter(self)
        layout.addWidget(self.editor)

        self.tag_edit = QLineEdit(self)
        self.tag_edit.setObjectName("tags")
        self.tag_edit.setPlaceholderText("标签：逗号分隔，可用 类型/标签 分类")
        self.tag_edit.setText(", ".join(tag_names or []))
        self.tag_edit.setClearButtonEnabled(True)
        self.tag_edit.editingFinished.connect(
            lambda: self.tagsEdited.emit(self.note.id, self.tag_edit.text())
        )
        layout.addWidget(self.tag_edit)

        bar = QWidget(self)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(0, 0, 0, 0)
        bar_layout.setSpacing(2)

        self.time_label = QLabel(format_time(note.updated), bar)
        self.time_label.setObjectName("muted")
        bar_layout.addWidget(self.time_label)
        bar_layout.addStretch(1)

        self.pin_btn = QToolButton(bar)
        self.pin_btn.setObjectName("pinbtn")
        self.pin_btn.setText("★" if note.pinned else "☆")
        self.pin_btn.setToolTip("取消置顶" if note.pinned else "置顶这条便签")
        self.pin_btn.setProperty("active", "true" if note.pinned else "false")
        self.pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pin_btn.clicked.connect(lambda: self.pinRequested.emit(self.note.id))
        bar_layout.addWidget(self.pin_btn)

        self.up_btn = self._mk_button(bar, "↑", "上移", lambda: self.moveRequested.emit(self.note.id, -1))
        self.down_btn = self._mk_button(bar, "↓", "下移", lambda: self.moveRequested.emit(self.note.id, 1))
        self.copy_btn = self._mk_button(bar, "⧉", "复制内容", lambda: self.copyRequested.emit(self.note.id))
        self.del_btn = self._mk_button(bar, "✕", "删除", lambda: self.deleteRequested.emit(self.note.id))
        self.del_btn.setObjectName("delbtn")
        for btn in (self.up_btn, self.down_btn, self.copy_btn, self.del_btn):
            bar_layout.addWidget(btn)

        layout.addWidget(bar)
        self.apply_pinned(note.pinned)

    def _mk_button(self, parent, text, tip, slot) -> QToolButton:
        return make_tool_button(parent, text, tip, slot, "cardbtn")

    def apply_pinned(self, pinned: bool) -> None:
        self.setProperty("pinned", "true" if pinned else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def _on_text_changed(self) -> None:
        if self._suppress:
            return
        self.textEdited.emit(self.note.id, self.editor.toPlainText())

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self.editor:
            if event.type() == QEvent.Type.FocusIn:
                self.focusChanged.emit(self.note.id, True)
            elif event.type() == QEvent.Type.FocusOut:
                self.focusChanged.emit(self.note.id, False)
        return super().eventFilter(obj, event)

    def set_editor_focus(self) -> None:
        self.editor.setFocus()
        cur = self.editor.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.editor.setTextCursor(cur)


class Pager(QWidget):
    """底部分页器：‹ 1 2 3 … ›"""

    pageChanged = pyqtSignal(int)

    MAX_BUTTONS = 7

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._total = 1
        self._current = 1

    def set_pages(self, total: int, current: int) -> None:
        self._total = max(1, total)
        self._current = max(1, min(current, self._total))
        self._rebuild()

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()

    def _mk(self, text: str, page: int | None, current: bool = False, tip: str = "") -> QToolButton:
        btn = QToolButton(self)
        btn.setObjectName("pagebtn")
        btn.setText(text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        if tip:
            btn.setToolTip(tip)
        btn.setProperty("current", "true" if current else "false")
        if page is not None:
            btn.clicked.connect(lambda _=False, p=page: self.pageChanged.emit(p))
        else:
            btn.setEnabled(False)
        self.style().unpolish(btn)
        self.style().polish(btn)
        return btn

    def _page_numbers(self) -> list:
        total, cur = self._total, self._current
        if total <= self.MAX_BUTTONS:
            return list(range(1, total + 1))
        pages = {1, total, cur}
        for d in (-1, 1):
            p = cur + d
            if 1 < p < total:
                pages.add(p)
        if cur <= 3:
            pages.update({2, 3, 4})
        if cur >= total - 2:
            pages.update({total - 1, total - 2, total - 3})
        ordered = sorted(p for p in pages if 1 <= p <= total)
        result = []
        prev = 0
        for p in ordered:
            if prev and p - prev > 1:
                result.append(None)
            result.append(p)
            prev = p
        return result

    def _rebuild(self) -> None:
        self._clear()
        self._layout.addStretch(1)
        self._layout.addWidget(self._mk("‹", self._current - 1, False, "上一页"))
        for p in self._page_numbers():
            if p is None:
                label = QLabel("…", self)
                label.setObjectName("muted")
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self._layout.addWidget(label)
            else:
                self._layout.addWidget(self._mk(str(p), p, p == self._current))
        self._layout.addWidget(self._mk("›", self._current + 1, False, "下一页"))
        self._layout.addStretch(1)


class EmptyHint(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self.setObjectName("empty")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
