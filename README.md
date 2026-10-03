# QuickNotes

一个 Windows 本地快捷便签工具：按全局快捷键召唤窗口，数据保存在本机，不需要账号或联网。

## 直接使用

1. 打开 GitHub Releases，下载 `QuickNotes-Portable-windows-x64.zip`。
2. 解压后双击 `QuickNotes.exe`。
3. 默认快捷键是 `Ctrl + Alt + N`；可以在托盘图标的“设置”中修改。

便携版不需要安装 Python 或 PyQt6。用户数据保存在：

```text
%LOCALAPPDATA%\QuickNotes\data.json
```

## 功能

- 全局快捷键快速打开便签窗口
- 本地 JSON 存储，支持导出/导入分享包
- 置顶、排序、分页、自动收起
- 标签和标签类型：支持 `类型/标签` 写法
- 按标签或标签类型筛选，标签类型可折叠
- Windows 单实例运行，重复打开时激活已有窗口

## 从源码运行

需要 Python 3.13 和 PyQt6：

```powershell
python -m pip install PyQt6
python main.py
```

打包需要 PyInstaller：

```powershell
python -m PyInstaller --clean --noconfirm QuickNotes.spec
```

## 许可

本项目按 GNU GPL-3.0 发布。第三方组件许可说明见 [THIRD_PARTY_NOTICES.txt](THIRD_PARTY_NOTICES.txt)。

