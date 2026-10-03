"""端到端验证 QuickNotes 分享包导出/导入链路。"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.storage import Store, Note, SHARE_TYPE  # noqa: E402
read_share = Store.read_share

results = []


def ok(name, cond, extra=""):
    results.append((name, bool(cond), extra))


tmp = Path(tempfile.mkdtemp(prefix="qn_share_"))
db = tmp / "data.json"

# 1. 造 3 条便签
store = Store(db)
store.notes = [
    Note(text="第一条：快捷键备忘", pinned=True),
    Note(text="第二条：常用命令"),
    Note(text="第三条：会议要点"),
]
store.save()
ok("写入 3 条便签", len(store.notes) == 3, f"n={len(store.notes)}")

# 2. 导出
share_path = tmp / "my-share.json"
res = store.export_to(share_path, title="我的便签集", author="mmrgr")
ok("export_to 返回 True", res is True)

# 3. 校验文件内容
ok("分享包文件已生成", share_path.exists())
if share_path.exists():
    raw = share_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    ok("type 字段正确", data.get("type") == SHARE_TYPE, f"got={data.get('type')}")
    ok("version 存在", data.get("version") is not None, f"got={data.get('version')}")
    ok("exported_at 存在", bool(data.get("exported_at")), f"got={data.get('exported_at')}")
    meta = data.get("meta") or {}
    ok("meta.title 正确", meta.get("title") == "我的便签集", f"got={meta.get('title')}")
    ok("meta.author 正确", meta.get("author") == "mmrgr", f"got={meta.get('author')}")
    ok("meta.count == 3", meta.get("count") == 3, f"got={meta.get('count')}")
    ok("notes 数组长度 3", len(data.get("notes") or []) == 3, f"got={len(data.get('notes') or [])}")
    first = (data.get("notes") or [{}])[0]
    ok("便签项含 text 字段", "text" in first, f"keys={list(first.keys())}")
    ok("便签项含 pinned 字段", "pinned" in first, f"keys={list(first.keys())}")

    # 4. 集市页面校验逻辑（复刻 index.html 里的那段）
    ok("集市校验：obj.type 判定通过", data.get("type") == SHARE_TYPE)
    ok("集市校验：notes 是数组", isinstance(data.get("notes"), list))
    ok("集市校验：便签条数 = 3", len(data.get("notes") or []) == 3)

# 5. read_share 静态方法
meta2, notes2 = read_share(share_path)
ok("read_share 返回 3 条", len(notes2) == 3, f"n={len(notes2)}")
ok("read_share meta.title", meta2.get("title") == "我的便签集", f"got={meta2.get('title')}")

# 6. 导入到全新库
store2 = Store(tmp / "data2.json")
added, skipped = store2.import_notes(notes2)
ok("全新库导入新增 3 条", added == 3, f"added={added} skipped={skipped}")
ok("导入后便签数正确", len(store2.notes) == 3, f"n={len(store2.notes)}")

# 7. 重复导入应去重
added2, skipped2 = store2.import_notes(notes2)
ok("重复导入新增 0 条", added2 == 0, f"added={added2}")
ok("重复导入跳过 3 条", skipped2 == 3, f"skipped={skipped2}")

# 8. 合并导入（对方已有便签）
store3 = Store(tmp / "data3.json")
store3.notes = [Note(text="我自己的便签")]
store3.save()
added3, skipped3 = store3.import_notes(notes2)
ok("合并导入新增 3 条", added3 == 3, f"added={added3}")
ok("合并后共 4 条", len(store3.notes) == 4, f"n={len(store3.notes)}")

# 9. 导出空库
store_empty = Store(tmp / "data4.json")
empty_path = tmp / "empty.json"
store_empty.export_to(empty_path, title="空的", author="x")
ok("空库也能导出文件", empty_path.exists())
if empty_path.exists():
    d = json.loads(empty_path.read_text(encoding="utf-8"))
    ok("空库 notes 为空数组", d.get("notes") == [], f"got={d.get('notes')}")
    m, n = read_share(empty_path)
    ok("read_share 对空包返回 0 条", len(n) == 0, f"n={len(n)}")

# 10. 坏文件容错
bad = tmp / "bad.json"
bad.write_text("{ not valid json", encoding="utf-8")
m3, n3 = read_share(bad)
ok("坏 JSON 不崩溃且返回 0 条", len(n3) == 0, f"n={len(n3)}")

# 输出
print("\n===== 分享功能端到端验证 =====")
passed = 0
for name, passed_flag, extra in results:
    tag = "PASS" if passed_flag else "FAIL"
    print(f"{tag}  {name}" + (f"   ({extra})" if extra else ""))
    if passed_flag:
        passed += 1
print(f"\n通过 {passed}/{len(results)}")
print(f"\n测试目录: {tmp}")
sys.exit(0 if passed == len(results) else 1)
