# -*- coding: utf-8 -*-
"""开机自启（Windows）。

实现方式：**当前用户**注册表 `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`
—— 写入 `HKLM` 需要管理员权限并会弹 UAC，而 `HKCU` 任何用户都能写、同样在登录时启动，
是这个场景下的正确选择（免提权、免安装、可随时手动删除）。

为什么不用「启动文件夹快捷方式」：那要生成 `.lnk` 文件，得依赖 COM 或额外写文件，
而注册表项就是一行字符串，创建/删除/查证都干净可靠。

⚠️ 开发态（`python main.py`）**不提供**自启：那时候 `sys.executable` 是
`python.exe`，写进去会让系统每次开机去跑解释器。必须明确拒绝并说明原因，
而不是默默写一个坏掉的启动项。
"""

from __future__ import annotations

import os
import sys
from typing import Optional

from .paths import is_frozen

# 注册表值名。带上前缀便于用户在自己的启动项里一眼认出这是哪个程序。
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "证书管理库 CertVault"


class AutostartUnavailable(Exception):
    """当前环境不支持设置开机自启（开发态 / 非 Windows / 注册表不可写）。"""


def _winreg():
    """延迟导入 winreg —— 非 Windows 平台上 import 会直接失败。"""
    if os.name != "nt":
        return None
    try:
        import winreg  # noqa: PLC0415
    except ImportError:      # pragma: no cover - 理论上不会发生
        return None
    return winreg


def _command() -> str:
    """要写进注册表的启动命令。

    冻结态用 `"<exe 路径>"`（**必须带引号**：exe 路径里通常有空格，
    比如 `E:\\【01】自研软件\\…`，不引号会被截断成 `E:\\【01】自研软件\\…`）。
    """
    if not is_frozen():
        raise AutostartUnavailable("开发态不支持开机自启")
    exe = os.path.abspath(sys.executable)
    return f'"{exe}"'


def is_enabled() -> bool:
    """注册表里是否已有本程序的启动项。读不出来一律当「未启用」——

    宁可显示「关」让人手动打开，也不能反过来谎报「开」却实际没生效。
    """
    wr = _winreg()
    if wr is None:
        return False
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY) as k:
            value, _ = wr.QueryValueEx(k, VALUE_NAME)
            return bool(value)
    except FileNotFoundError:
        return False
    except OSError:
        return False


def is_supported() -> bool:
    """当前运行环境是否支持设置开机自启。"""
    return os.name == "nt" and is_frozen() and _winreg() is not None


def status() -> str:
    """给设置面板用的一句话状态说明。"""
    if os.name != "nt":
        return "当前系统不是 Windows，无法设置开机自启。"
    if not is_frozen():
        return ("开发态（源码直接运行）下不提供开机自启 —— "
                "否则系统每次开机都会去启动 Python 解释器。"
                "打包成 exe 后即可使用。")
    if _winreg() is None:
        return "当前 Python 环境缺少 winreg 模块，无法设置开机自启。"
    if is_enabled():
        return "已注册开机自启（当前用户）。"
    return "未注册开机自启。"


def enable() -> None:
    """写入注册表启动项。"""
    wr = _winreg()
    if wr is None:
        raise AutostartUnavailable("当前系统不支持开机自启")
    cmd = _command()
    try:
        with wr.CreateKeyEx(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
            wr.SetValueEx(k, VALUE_NAME, 0, wr.REG_SZ, cmd)
    except OSError as exc:
        raise AutostartUnavailable(f"写入注册表失败：{exc}") from exc
    if not is_enabled():
        raise AutostartUnavailable("已尝试写入，但注册表里读不到该项，注册表可能被策略锁定。")


def disable() -> None:
    """删除注册表启动项。项不存在时静默成功（幂等）。"""
    wr = _winreg()
    if wr is None:
        return
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
            wr.DeleteValue(k, VALUE_NAME)
    except FileNotFoundError:
        return
    except OSError:
        # 项不存在也可能表现为别的错误码，这里再确认一次即可
        if is_enabled():
            raise


def sync(enabled: bool) -> Optional[str]:
    """把设置项同步到注册表，返回失败原因（None 表示成功或无需处理）。

    批量导入设置、或从旧版本升级时可能有「设置项写着开、注册表里没有」的不一致，
    启动时调一次 `sync(get_setting("autostart"))` 就能自愈。
    """
    if not enabled:
        # 关：删掉残留项即可。**开发态也要删** —— 用户可能先用 exe 开启过自启，
        # 后来改成源码运行，注册表里那个项还在指向旧 exe，不清掉就成了僵尸启动项。
        if os.name == "nt" and is_enabled():
            try:
                disable()
            except AutostartUnavailable as exc:
                return str(exc)
        return None
    # 开：不支持就如实返回原因，不静默失败也不静默成功
    if not is_supported():
        return status()
    try:
        if not is_enabled():
            enable()
    except AutostartUnavailable as exc:
        return str(exc)
    return None
