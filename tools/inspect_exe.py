"""分析 PyInstaller 产物内部构成，用于定位体积大头。"""
import sys
from PyInstaller.archive.readers import CArchiveReader

path = sys.argv[1] if len(sys.argv) > 1 else "dist/QuickNotes.exe"
arc = CArchiveReader(path)

rows = []
for key, entry in arc.toc.items():
    # CArchive TOC: (offset, compressed_len, uncompressed_len, compress_flag, type)
    try:
        rows.append((entry[2], key))
    except Exception:
        pass

rows.sort(reverse=True)
total = sum(s for s, _ in rows)
print("条目总数: %d  总计: %.2f MB" % (len(rows), total / 1048576))
print("-" * 58)
for size, key in rows[:30]:
    print("%9.2f MB  %s" % (size / 1048576, key))

qm = [s for s, k in rows if k.lower().endswith(".qm")]
print("-" * 58)
print("qm 翻译文件: %d 个, 合计 %.2f MB" % (len(qm), sum(qm) / 1048576))
