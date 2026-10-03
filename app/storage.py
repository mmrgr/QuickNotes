"""便签数据模型与本地 JSON 存储。"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import Settings, data_file


SHARE_TYPE = "quicknotes-share"


def _now() -> float:
    return time.time()


@dataclass
class Note:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    text: str = ""
    created: float = field(default_factory=_now)
    updated: float = field(default_factory=_now)
    pinned: bool = False
    # 保存稳定的标签 ID；旧版本数据没有此字段，会自动迁移为空列表。
    tags: list[str] = field(default_factory=list)

    @property
    def tag_ids(self) -> list[str]:
        """兼容使用 tag_ids 命名的调用方。"""
        return self.tags

    @tag_ids.setter
    def tag_ids(self, value: list[str]) -> None:
        self.tags = list(value or [])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "created": self.created,
            "updated": self.updated,
            "pinned": self.pinned,
            "tags": list(self.tags),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Note":
        raw_tags = data.get("tags") or data.get("tag_ids") or []
        if not isinstance(raw_tags, list):
            raw_tags = []
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            text=data.get("text", "") or "",
            created=float(data.get("created") or _now()),
            updated=float(data.get("updated") or _now()),
            pinned=bool(data.get("pinned", False)),
            tags=[str(v) for v in raw_tags if v],
        )


@dataclass
class TagGroup:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = "未分类"
    collapsed: bool = False

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "collapsed": self.collapsed}

    @classmethod
    def from_dict(cls, data: dict) -> "TagGroup":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "未分类").strip() or "未分类",
            collapsed=bool(data.get("collapsed", False)),
        )


@dataclass
class Tag:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    name: str = ""
    group_id: str = ""

    @property
    def type_id(self) -> str:
        return self.group_id

    @type_id.setter
    def type_id(self, value: str) -> None:
        self.group_id = str(value or "")

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "group_id": self.group_id}

    @classmethod
    def from_dict(cls, data: dict) -> "Tag":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            name=str(data.get("name") or "").strip(),
            group_id=str(data.get("group_id") or ""),
        )


class Store:
    """便签仓库：内存中的列表 + 本地 JSON 文件持久化。"""

    VERSION = 2

    def __init__(self, path: Path | None = None):
        self.path = path or data_file()
        self.settings = Settings()
        self.notes: list[Note] = []
        self.tag_groups: list[TagGroup] = []
        self.tags: list[Tag] = []
        self.on_change: Callable[[], None] | None = None
        self.fresh = not self.path.exists()   # 首次运行（还没有数据文件）
        self.load()

    @property
    def groups(self) -> list[TagGroup]:
        """标签类型的简短别名，便于脚本和旧调用方使用。"""
        return self.tag_groups

    @property
    def tag_types(self) -> list[TagGroup]:
        return self.tag_groups

    # -------------------------------------------------------------- 持久化
    def load(self) -> None:
        data = {}
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {}
        except (json.JSONDecodeError, OSError):
            self._backup_corrupted()
            data = {}

        self.settings = Settings.from_dict(data.get("settings"))
        notes = data.get("notes")
        self.notes = [Note.from_dict(n) for n in notes] if isinstance(notes, list) else []
        groups = data.get("tag_groups") or data.get("groups")
        self.tag_groups = [TagGroup.from_dict(g) for g in groups if isinstance(g, dict)] \
            if isinstance(groups, list) else []
        raw_tags = data.get("tags")
        self.tags = [Tag.from_dict(t) for t in raw_tags if isinstance(t, dict)] \
            if isinstance(raw_tags, list) else []
        # 清理损坏或指向不存在标签的引用，保留旧文件可读性。
        known = {t.id for t in self.tags}
        for note in self.notes:
            note.tags = [tag_id for tag_id in note.tags if tag_id in known]
        self._ensure_tag_integrity()

    def save(self) -> None:
        payload = {
            "version": self.VERSION,
            "settings": self.settings.to_dict(),
            "notes": [n.to_dict() for n in self.notes],
            "tag_groups": [g.to_dict() for g in self.tag_groups],
            "tags": [t.to_dict() for t in self.tags],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            try:
                with open(self.path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=2)
            except OSError:
                pass
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    def _backup_corrupted(self) -> None:
        try:
            if self.path.exists():
                backup = self.path.with_name(
                    self.path.stem + "_corrupted_" + time.strftime("%Y%m%d%H%M%S") + ".json"
                )
                self.path.replace(backup)
        except OSError:
            pass

    # -------------------------------------------------------------- 增删改
    def add(self, text: str = "", pinned: bool = False) -> Note:
        note = Note(text=text, pinned=pinned)
        self.notes.insert(0, note)
        self._changed()
        return note

    def get(self, note_id: str) -> Note | None:
        for n in self.notes:
            if n.id == note_id:
                return n
        return None

    def update_text(self, note_id: str, text: str) -> None:
        note = self.get(note_id)
        if note is None:
            return
        if note.text != text:
            note.text = text
            note.updated = _now()
            self._changed()

    def toggle_pin(self, note_id: str) -> None:
        note = self.get(note_id)
        if note:
            note.pinned = not note.pinned
            note.updated = _now()
            self._changed()

    def delete(self, note_id: str) -> None:
        self.notes = [n for n in self.notes if n.id != note_id]
        self._changed()

    def move(self, note_id: str, delta: int) -> bool:
        """在当前可视顺序中上移/下移一位（delta=-1 上移，+1 下移）。"""
        order = self.visible_notes()
        ids = [n.id for n in order]
        if note_id not in ids:
            return False
        src = ids.index(note_id)
        dst = src + delta
        if dst < 0 or dst >= len(ids):
            return False
        other_id = ids[dst]
        idx_a = next((i for i, n in enumerate(self.notes) if n.id == note_id), None)
        idx_b = next((i for i, n in enumerate(self.notes) if n.id == other_id), None)
        if idx_a is None or idx_b is None:
            return False
        a, b = self.notes[idx_a], self.notes[idx_b]
        if self.settings.show_pinned_first and a.pinned != b.pinned:
            # 跨越「置顶 / 普通」分组时同步交换置顶状态，保证视觉上真的换了个位置
            a.pinned, b.pinned = b.pinned, a.pinned
        self.notes[idx_a], self.notes[idx_b] = b, a
        a.updated = b.updated = _now()
        self._changed()
        return True

    # -------------------------------------------------------------- 标签
    @staticmethod
    def _key(value: str) -> str:
        return " ".join(str(value or "").strip().casefold().split())

    def _ensure_tag_integrity(self) -> None:
        """保证标签所属分组存在，并去除空标签。"""
        groups_by_id = {g.id: g for g in self.tag_groups}
        if not groups_by_id:
            return
        fallback = self.tag_groups[0].id
        for tag in self.tags:
            if not tag.group_id or tag.group_id not in groups_by_id:
                tag.group_id = fallback
        self.tags = [tag for tag in self.tags if tag.name]

    def group_by_id(self, group_id: str) -> TagGroup | None:
        return next((g for g in self.tag_groups if g.id == group_id), None)

    def tag_by_id(self, tag_id: str) -> Tag | None:
        return next((t for t in self.tags if t.id == tag_id), None)

    def ensure_group(self, name: str = "未分类") -> TagGroup:
        name = str(name or "未分类").strip() or "未分类"
        key = self._key(name)
        group = next((g for g in self.tag_groups if self._key(g.name) == key), None)
        if group is None:
            group = TagGroup(name=name)
            self.tag_groups.append(group)
        return group

    def create_group(self, name: str) -> TagGroup:
        return self.ensure_group(name)

    def rename_group(self, group_id: str, name: str) -> bool:
        group = self.group_by_id(group_id)
        name = str(name or "").strip()
        if group is None or not name:
            return False
        if any(g.id != group_id and self._key(g.name) == self._key(name) for g in self.tag_groups):
            return False
        group.name = name
        self._changed()
        return True

    def delete_group(self, group_id: str) -> bool:
        group = self.group_by_id(group_id)
        if group is None:
            return False
        remaining = [g for g in self.tag_groups if g.id != group_id]
        target = next((g for g in remaining if self._key(g.name) == self._key("未分类")), None)
        if target is None:
            target = self.ensure_group("未分类")
        for tag in self.tags:
            if tag.group_id == group_id:
                tag.group_id = target.id
        if target not in remaining:
            remaining.append(target)
        self.tag_groups = remaining
        self._changed()
        return True

    def tags_for_group(self, group_id: str) -> list[Tag]:
        return [t for t in self.tags if t.group_id == group_id]

    def ensure_tag(self, name: str, group_name: str = "未分类") -> Tag | None:
        name = str(name or "").strip()
        if not name:
            return None
        group = self.ensure_group(group_name)
        key = self._key(name)
        tag = next((t for t in self.tags if t.group_id == group.id and self._key(t.name) == key), None)
        if tag is None:
            tag = Tag(name=name, group_id=group.id)
            self.tags.append(tag)
        return tag

    def rename_tag(self, tag_id: str, name: str) -> bool:
        tag = self.tag_by_id(tag_id)
        name = str(name or "").strip()
        if tag is None or not name:
            return False
        if any(t.id != tag_id and t.group_id == tag.group_id and self._key(t.name) == self._key(name)
               for t in self.tags):
            return False
        tag.name = name
        self._changed()
        return True

    def delete_tag(self, tag_id: str) -> bool:
        if self.tag_by_id(tag_id) is None:
            return False
        self.tags = [t for t in self.tags if t.id != tag_id]
        for note in self.notes:
            note.tags = [value for value in note.tags if value != tag_id]
        self._changed()
        return True

    def set_group_collapsed(self, group_id: str, collapsed: bool) -> bool:
        group = self.group_by_id(group_id)
        if group is None:
            return False
        group.collapsed = bool(collapsed)
        self._changed()
        return True

    @staticmethod
    def _split_tag_name(raw: str) -> tuple[str, str]:
        value = str(raw or "").strip()
        for sep in ("/", "\\", ":", "："):
            if sep in value:
                group, name = value.split(sep, 1)
                if group.strip() and name.strip():
                    return group.strip(), name.strip()
        return "未分类", value

    def note_tag_names(self, note: Note) -> list[str]:
        result = []
        for tag_id in note.tags:
            tag = self.tag_by_id(tag_id)
            if tag is None:
                continue
            group = self.group_by_id(tag.group_id)
            result.append(tag.name if group is None or group.name == "未分类" else f"{group.name}/{tag.name}")
        return result

    def set_note_tags(self, note_id: str, names: list[str] | str) -> list[str]:
        note = self.get(note_id)
        if note is None:
            return []
        if isinstance(names, str):
            names = names.replace("；", ";").replace("，", ",").replace(";", ",").split(",")
        tag_ids = []
        for raw in names or []:
            group_name, tag_name = self._split_tag_name(raw)
            tag = self.ensure_tag(tag_name, group_name)
            if tag is not None and tag.id not in tag_ids:
                tag_ids.append(tag.id)
        if note.tags != tag_ids:
            note.tags = tag_ids
            note.updated = _now()
            self._changed()
        return self.note_tag_names(note)

    def visible_notes(self, query: str = "", tag_id: str | None = None,
                      group_id: str | None = None) -> list[Note]:
        q = (query or "").strip().lower()
        def matches(note: Note) -> bool:
            if tag_id and tag_id not in note.tags:
                return False
            if group_id and not any(t.group_id == group_id for t in self.tags if t.id in note.tags):
                return False
            if not q:
                return True
            labels = " ".join(self.note_tag_names(note)).lower()
            return q in note.text.lower() or q in labels
        items = [n for n in self.notes if matches(n)]
        if self.settings.show_pinned_first:
            items = sorted(items, key=lambda n: 0 if n.pinned else 1)
        return items

    def _changed(self) -> None:
        if self.on_change:
            self.on_change()

    # -------------------------------------------------------------- 导入导出
    def export_to(self, path: Path, title: str = "", author: str = "") -> bool:
        """导出为「分享包」：可在其它电脑上导入的单个 JSON 文件。"""
        payload = {
            "type": SHARE_TYPE,
            "version": self.VERSION,
            "exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "meta": {
                "title": title or "未命名便签集",
                "author": author or "",
                "count": len(self.notes),
            },
            "tag_groups": [g.to_dict() for g in self.tag_groups],
            "tags": [t.to_dict() for t in self.tags],
            "notes": [dict(n.to_dict(), tag_names=self.note_tag_names(n)) for n in self.notes],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    @staticmethod
    def read_share(path: Path) -> tuple[dict, list[dict]]:
        """读取分享包，返回 (meta, notes_dict_list)。"""
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}, []
        if isinstance(data, dict):
            raw = data.get("notes") or []
            meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
            meta = dict(meta)
            meta["_tag_groups"] = data.get("tag_groups") or []
            meta["_tags"] = data.get("tags") or []
        else:
            raw, meta = data, {}
        notes = [n for n in raw if isinstance(n, dict)]
        result_meta = {
            "title": meta.get("title") or Path(path).stem,
            "author": meta.get("author") or "",
            "count": meta.get("count") if meta.get("count") is not None else len(notes),
            "exported_at": meta.get("exported_at") if isinstance(data, dict) else "",
        }
        if isinstance(data, dict):
            result_meta["exported_at"] = data.get("exported_at", "")
            result_meta["_tag_groups"] = meta.get("_tag_groups", [])
            result_meta["_tags"] = meta.get("_tags", [])
        return result_meta, notes

    def import_notes(self, raw_notes: list[dict], tag_defs: list[dict] | None = None,
                     group_defs: list[dict] | None = None) -> tuple[int, int]:
        """导入一批便签，返回 (新增条数, 因重复跳过的条数)。"""
        existing = {n.id for n in self.notes}
        id_to_group_name: dict[str, str] = {}
        for raw_group in group_defs or []:
            if not isinstance(raw_group, dict):
                continue
            group = self.ensure_group(str(raw_group.get("name") or "未分类"))
            id_to_group_name[str(raw_group.get("id") or "")] = group.name
        id_to_tag_name: dict[str, str] = {}
        for raw_tag in tag_defs or []:
            if not isinstance(raw_tag, dict):
                continue
            name = str(raw_tag.get("name") or "").strip()
            if not name:
                continue
            group_name = id_to_group_name.get(str(raw_tag.get("group_id") or ""), "未分类")
            tag = self.ensure_tag(name, group_name)
            if tag is not None:
                id_to_tag_name[str(raw_tag.get("id") or "")] = tag.name
        added = skipped = 0
        for item in raw_notes:
            note = Note.from_dict(item)
            if note.id in existing:
                skipped += 1
                continue
            names = item.get("tag_names") if isinstance(item, dict) else None
            if isinstance(names, list):
                self._set_note_tag_names_direct(note, names)
            elif note.tags and id_to_tag_name:
                self._set_note_tag_names_direct(note, [
                    (id_to_group_name.get(str(next((t.get("group_id") for t in (tag_defs or [])
                                                    if isinstance(t, dict) and str(t.get("id")) == tag_id), "")),
                     "未分类") + "/" + id_to_tag_name.get(tag_id, ""))
                    for tag_id in note.tags if tag_id in id_to_tag_name
                ])
            self.notes.append(note)
            existing.add(note.id)
            added += 1
        if added:
            self._changed()
        return added, skipped

    def _set_note_tag_names_direct(self, note: Note, names: list[str]) -> None:
        tag_ids = []
        for raw in names:
            group_name, tag_name = self._split_tag_name(raw)
            tag = self.ensure_tag(tag_name, group_name)
            if tag is not None and tag.id not in tag_ids:
                tag_ids.append(tag.id)
        note.tags = tag_ids

    def import_from(self, path: Path) -> tuple[int, int]:
        meta, notes = self.read_share(path)
        return self.import_notes(notes, meta.get("_tags"), meta.get("_tag_groups"))
