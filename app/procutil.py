# -*- coding: utf-8 -*-
r"""子进程调用的统一封装 —— 核心目的是**静默运行**。

⚠️ 为什么需要这个模块：Windows 上从**无控制台的 GUI 程序**（PyInstaller 的
`--noconsole`）里调用 `tasklist` / `taskkill` / `explorer` 这类控制台程序时，
系统会**自动为它新建一个控制台窗口** —— 表现为双击 exe 后先闪出一个黑色 cmd 窗口。
（用户实测截图就是这个：标题栏显示 `C:\WINDOWS\SYSTEM32\task...` 的黑窗。）

解法是给 `subprocess` 传 `creationflags`：

- `CREATE_NO_WINDOW`（0x08000000）—— 不给子进程分配控制台窗口；
- `SW_HIDE` —— 双重保险。

⚠️⚠️ **绝对不能加 `STARTF_USESHOWWINDOW`**（v1.6.0 踩过，症状是**程序启动即挂死**）。
最初以为「三个标志一起给才彻底静默」，实测 8 种组合的结论是：

| 组合 | `tasklist` 结果 |
| -- | -- |
| 无标志 | 正常 |
| `CREATE_NO_WINDOW` | 正常 |
| **`STARTF_USESHOWWINDOW`** | **挂死** |
| **`STARTF_USESHOWWINDOW｜SW_HIDE`** | **挂死** |
| **`CREATE_NO_WINDOW｜STARTF_USESHOWWINDOW`** | **挂死** |
| **`CREATE_NO_WINDOW｜STARTF_USESHOWWINDOW｜SW_HIDE`** | **挂死** |
| **`CREATE_NO_WINDOW｜SW_HIDE`** | ✅ **正常** |

也就是说 `STARTF_USESHOWWINDOW` 与 `capture_output=True`（重定向管道）组合会让
`tasklist` **永久挂起**，调用方跟着一起死。冻结态的表现是「双击 exe 什么都不发生、
进程还在但没有窗口」—— 极难定位，因为冻结态没有 stderr，只有插桩写文件才看得见。

所以正确解法是 `CREATE_NO_WINDOW | SW_HIDE` **两个**。
"""

from __future__ import annotations

import subprocess
import sys
from typing import Sequence

# Windows 专有标志；非 Windows 平台没有这些常量，一律置 0（= 不传标志）
if sys.platform == "win32":                     # noqa: SIM108
    _NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    _SW_HIDE = getattr(subprocess, "SW_HIDE", 0)
    # ★ STARTF_USESHOWWINDOW **故意不给**：它与 capture_output=True 组合会让
    #   tasklist 永久挂死（实测 8 种组合，见模块 docstring 的对照表）。
    _STARTF_USESHOWWINDOW = 0
else:  # pragma: no cover - 本项目只跑 Windows
    _NO_WINDOW = _STARTF_USESHOWWINDOW = _SW_HIDE = 0


def silent_flags() -> int:
    """返回「静默运行」的 creationflags，可在需要时传给别处。"""
    if not _NO_WINDOW:
        return 0
    return _NO_WINDOW | _SW_HIDE


def run_silent(args: Sequence[str], **kwargs):
    """`subprocess.run` 的静默版：不会弹出任何窗口。"""
    kwargs.setdefault("creationflags", silent_flags())
    if sys.platform == "win32":
        # 让子进程不因缺控制台而报错（stdin 已被重定向时需要）
        kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.run(list(args), **kwargs)


def popen_silent(args: Sequence[str], **kwargs):
    """`subprocess.Popen` 的静默版。"""
    kwargs.setdefault("creationflags", silent_flags())
    if sys.platform == "win32":
        kwargs.setdefault("stdin", subprocess.DEVNULL)
    return subprocess.Popen(list(args), **kwargs)
