# -*- mode: python ; coding: utf-8 -*-
"""QuickNotes 打包配置（体积优化版）。

代码只用到 PyQt6 的 QtCore / QtGui / QtWidgets；单实例检测使用 Windows 命名互斥体。
本配置做两轮瘦身：
  1) excludes —— 剔除用不到的 Python / PyQt6 模块（QtQuick、Qml、Multimedia、3D 等）
  2) 手动过滤 —— 剔除 Qt 运行库里的重量级 DLL
     （opengl32sw 是软件 OpenGL 兜底，Qt6Pdf 已排除但 DLL 仍被连带打包），
     以及 96 个非中文翻译 .qm。注意 .qm 归在 a.datas，binaries 里过滤是无效的。
"""

import os

QT_BIN = os.path.join(
    os.path.dirname(os.environ.get('VIRTUAL_ENV', '.venv')), 'Lib', 'site-packages', 'PyQt6', 'Qt6', 'bin'
)

# 明确要剔除的 Qt 原生 DLL / 插件
# 匹配方式：文件名在 EXCLUDE_DLLS 里，或完整路径包含 EXCLUDE_PATHS 里的任一片段
EXCLUDE_DLLS = {
    # 20MB —— 软件 OpenGL 兜底。本应用是纯 Widgets + 2D 绘制，用不上
    'opengl32sw.dll',
    # 4.4MB —— 已排除 PyQt6.QtPdf，这个 DLL 是连带被打进来的
    'Qt6Pdf.dll',
    # 仅由 QtNetwork/QLocale 路径带入；本应用不使用网络，也不依赖系统 ICU。
    'Qt6Network.dll',
    'icudt78.dll', 'icuuc.dll', 'icuin.dll',
    'ucrtbase.dll',
    # 0.6MB —— SVG 支持。本应用的托盘图标是 QPainter 画的，不读 svg
    'Qt6Svg.dll',
    # 6.5MB —— OpenSSL。本应用不联网（QLocalServer 是本地 IPC，不走 TLS）
    'libcrypto-3-x64.dll',
    'libssl-3-x64.dll',
    # ~1.3MB —— 图像格式插件。应用只用 QPainter 画图形 + ico 图标，
    #          不解码 jpeg/webp/tiff 等外部图片
    'qjpeg.dll', 'qwebp.dll', 'qtiff.dll', 'qicns.dll',
    'qgif.dll', 'qpdf.dll', 'qsvg.dll', 'qtga.dll', 'qwbmp.dll',
    # ~0.8MB —— TLS 后端插件，本应用不走 https
    'qopensslbackend.dll', 'qschannelbackend.dll', 'qcertonlybackend.dll',
    # ~0.17MB —— SVG 图标引擎，本应用不用 svg 图标
    'qsvgicon.dll',
    # ~0.08MB —— 触摸输入模拟，本应用无触屏需求
    'qtuiotouchplugin.dll',
    # ~0.08MB —— 网络信息插件（应用不使用网络）
    'qnetworklistmanager.dll',
    # 额外平台插件，只用 Windows 平台
    'qoffscreen.dll', 'qminimal.dll',
    # 0.15MB —— 运行时不需要 lzma 解压（lzma 只在打包期用，产物不需要自带）
    '_lzma.pyd',
}

# 用不到的 PyQt6 模块（按体积从大到小）
EXCLUDES = [
    # Qt Quick / QML 声明式 UI —— 本项目是纯 Widgets
    'PyQt6.QtQuick',
    'PyQt6.QtQuick3D',
    'PyQt6.QtQuick3DRuntimeRender',
    'PyQt6.QtQuick3DPhysics',
    'PyQt6.QtQuick3DParticles',
    'PyQt6.QtQuick3DUtils',
    'PyQt6.QtQuick3DAssetImport',
    'PyQt6.QtQuickControls2',
    'PyQt6.QtQuickDialogs2',
    'PyQt6.QtQuickDialogs2QuickImpl',
    'PyQt6.QtQuickDialogs2QmlImpl',
    'PyQt6.QtQuickLayouts',
    'PyQt6.QtQuickShapes',
    'PyQt6.QtQuickTemplates2',
    'PyQt6.QtQuickWidgets',
    'PyQt6.QtQml',
    'PyQt6.QtQmlModels',
    'PyQt6.QtQmlWorkerScript',
    'PyQt6.QtQuickTest',
    # 多媒体（带 ffmpeg，十几兆）
    'PyQt6.QtMultimedia',
    'PyQt6.QtMultimediaWidgets',
    'PyQt6.QtSpatialAudio',
    # 3D / 着色器 / 设计器
    'PyQt6.Qt3DCore',
    'PyQt6.Qt3DRender',
    'PyQt6.Qt3DAnimation',
    'PyQt6.Qt3DExtras',
    'PyQt6.Qt3DInput',
    'PyQt6.Qt3DLogic',
    'PyQt6.QtShaderTools',
    'PyQt6.QtDesigner',
    'PyQt6.QtUiTools',
    'PyQt6.QtHelp',
    # 本项目不用的其它 Qt 模块
    'PyQt6.QtWebEngineCore',
    'PyQt6.QtWebEngineWidgets',
    'PyQt6.QtWebEngineQuick',
    'PyQt6.QtWebChannel',
    'PyQt6.QtWebSockets',
    'PyQt6.QtSql',
    'PyQt6.QtTest',
    'PyQt6.QtBluetooth',
    'PyQt6.QtNfc',
    'PyQt6.QtPositioning',
    'PyQt6.QtLocation',
    'PyQt6.QtSensors',
    'PyQt6.QtSerialPort',
    'PyQt6.QtSerialBus',
    'PyQt6.QtCharts',
    'PyQt6.QtDataVisualization',
    'PyQt6.QtGraphs',
    'PyQt6.QtPdf',
    'PyQt6.QtPdfWidgets',
    'PyQt6.QtScxml',
    'PyQt6.QtStateMachine',
    'PyQt6.QtTextToSpeech',
    'PyQt6.QtRemoteObjects',
    'PyQt6.QtHttpServer',
    'PyQt6.QtNetworkAuth',
    'PyQt6.QtNetwork',
    'PyQt6.QtOpenGL',
    'PyQt6.QtOpenGLWidgets',
    'PyQt6.QtQuick',
    'PyQt6.QtQuickEffects',
    'PyQt6.QtCore5Compat',
    'PyQt6.QtDBus',
    # 用不到的 Python 大包（只排确定无依赖的，标准库一律不动）
    'tkinter',
    'pydoc_data',
    'test',
    'lib2to3',
    'numpy',
    'PIL',
    'matplotlib',
    'pytest',
    'IPython',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=2,          # 去掉断言与 docstring
)

# ---- 第二轮：剔除重量级 Qt 原生 DLL 与用不到的插件/翻译 ----
# 保留 qtbase_zh_CN.qm（中文界面提示）；其余 95 个语言包与基础翻译全剔
KEEP_DLL_NAMES = {'qico.dll', 'qwindows.dll', 'qmodernwindowsstyle.dll',
                  'qtbase_zh_CN.qm', 'qt_zh_CN.qm'}

_dropped = []
_kept = []
for _entry in a.binaries:
    _name = _entry[0] if isinstance(_entry, (tuple, list)) else getattr(_entry, 'name', '')
    _base = os.path.basename(str(_name))
    # 翻译文件：只留简体中文
    if _base.endswith('.qm') and _base not in KEEP_DLL_NAMES:
        _dropped.append(_base)
        continue
    if _base in EXCLUDE_DLLS:
        _dropped.append(_base)
        continue
    _kept.append(_entry)
a.binaries = _kept

# Qt 翻译文件（.qm）在 PyInstaller 里归到 datas 而非 binaries，
# 必须单独过滤，否则 96 个语言包 6.4MB 会被原样打进去。
_data_dropped = []
_data_kept = []
for _entry in a.datas:
    _name = _entry[0] if isinstance(_entry, (tuple, list)) else getattr(_entry, 'name', '')
    _base = os.path.basename(str(_name))
    if _base.endswith('.qm') and _base not in KEEP_DLL_NAMES:
        _data_dropped.append(_base)
        continue
    _data_kept.append(_entry)
a.datas = _data_kept

print(f"[spec] 已剔除 DLL/插件 {len(set(_dropped))} 项")
print(f"[spec] 已剔除翻译文件 {len(set(_data_dropped))} 个")
print(f"[spec] 保留二进制 {len(_kept)} 个 / 数据 {len(_data_kept)} 个")


pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='QuickNotes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,          # 去掉符号表
    upx=False,           # 本机未安装 UPX，硬开只会拖慢打包且无收益
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['app_icon.ico'],
)
