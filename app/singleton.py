# -*- coding: utf-8 -*-
"""进程治理：启动清理残留在后台的旧实例，退出时确保自身进程彻底结束。"""

from __future__ import annotations

import os
import sys
from typing import Callable, List, Optional

from . import procutil


def _log_default(msg: str) -> None:
    print(f"[singleton] {msg}")


def _ancestor_pids() -> set:
    """返回自己的**全部祖先 PID**（含直接父进程）。

    ★★ 这是 `kill_previous_instances` 里最关键的一条守卫。
    PyInstaller **onefile** 模式下，同一个 exe 会有**两个**同名进程：
    `bootloader`（父，解包 + 拉起子进程）和真正的应用（子，跑 Python）。
    两者 `IMAGENAME` 完全相同，`tasklist /FI "IMAGENAME eq ..."` 两个都匹配。

    如果只排除 `os.getpid()`（应用自己），那个 `taskkill /F` 就会把**父 bootloader
    一起杀掉** —— 父进程一死，onefile 子进程失去依附被挂起，表现为
    **「双击 exe 什么都没发生、进程还在但不显示窗口」**。
    （v1.6.0 真机验证时抓到的就是这个：程序停在 `kill_previous_instances` 之后、
    `QApplication` 创建之前，日志里再无任何进展。）

    所以要排除的是「自己 + 自己的整条祖先链」。
    """
    out = set()
    try:
        import ctypes
        from ctypes import wintypes

        TH32CS_SNAPPROCESS = 0x00000002

        class _PE32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        k32 = ctypes.windll.kernel32
        k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        k32.Process32FirstW.restype = wintypes.BOOL
        k32.Process32NextW.restype = wintypes.BOOL
        snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
        if snap in (0, ctypes.c_void_p(-1).value):
            return out
        parents = {}
        ent = _PE32W()
        ent.dwSize = ctypes.sizeof(_PE32W)
        try:
            if k32.Process32FirstW(snap, ctypes.byref(ent)):
                while True:
                    parents[int(ent.th32ProcessID)] = int(ent.th32ParentProcessID)
                    if not k32.Process32NextW(snap, ctypes.byref(ent)):
                        break
        finally:
            k32.CloseHandle(snap)
        pid = os.getpid()
        for _ in range(16):          # 防环，16 层足够覆盖任何真实父子链
            ppid = parents.get(pid, 0)
            if not ppid or ppid in out:
                break
            out.add(ppid)
            pid = ppid
    except Exception:  # noqa: BLE001
        pass
    return out


def kill_previous_instances(log: Optional[Callable[[str], None]] = None) -> List[int]:
    """结束本程序残留的其他进程，返回被结束的 PID 列表。

    仅在冻结（exe）状态下生效 —— 开发态解释器名为 python.exe，
    贸然结束会误杀用户其它 Python 程序。

    ⚠️ `tasklist` / `taskkill` **必须走静默调用**（`procutil.run_silent`）：
    本程序是无控制台的 GUI 程序，Windows 会给这两个控制台程序**自动新建控制台窗口**
    ⇒ 双击 exe 会先闪出一个黑色 cmd 窗口（用户实测截图：标题栏是
    `C:\\WINDOWS\\SYSTEM32\\task...`）。见 `procutil` 模块说明。

    ⚠️⚠️ **必须跳过自己的祖先进程**（bootloader），否则会把自己父进程杀掉 ——
    详见 `_ancestor_pids()` 的说明。
    """
    log = log or _log_default
    if os.name != "nt" or not getattr(sys, "frozen", False):
        log("非 exe 运行环境，跳过旧进程清理")
        return []

    image = os.path.basename(sys.executable)
    me = os.getpid()
    protected = _ancestor_pids() | {me}
    killed: List[int] = []

    try:
        raw = procutil.run_silent(
            ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
            capture_output=True,
            timeout=15,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        log(f"tasklist 调用失败：{exc}")
        return []

    text = raw.decode("gbk", errors="ignore")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith('"'):
            continue
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) < 2 or parts[0].lower() != image.lower():
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        if pid in protected:
            continue
        try:
            procutil.run_silent(["taskkill", "/PID", str(pid), "/F"],
                                capture_output=True, timeout=15)
            killed.append(pid)
        except Exception as exc:  # noqa: BLE001
            log(f"结束进程 {pid} 失败：{exc}")

    if killed:
        log(f"已清理残留进程：{killed}")
    else:
        log("没有需要清理的残留进程")
    return killed


def hard_exit(code: int = 0) -> None:
    """强制结束自身进程，避免 Qt 线程/插件残留导致进程驻留。"""
    try:
        sys.stdout.flush()
    except Exception:  # noqa: BLE001
        pass
    os._exit(code)
