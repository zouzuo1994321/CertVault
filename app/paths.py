# -*- coding: utf-8 -*-
"""运行时路径解析。

打包为单文件 exe 后，数据目录位于 exe 同级目录，保证绿色免安装；
开发态则位于源码根目录，便于调试。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def base_dir() -> Path:
    """程序根目录（数据目录的父目录）。"""
    if is_frozen():
        return Path(os.path.dirname(os.path.abspath(sys.executable)))
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resource_dir() -> Path:
    """只读资源目录（打包后位于 _MEIPASS）。"""
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
    return Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


BASE_DIR = base_dir()
DATA_DIR = BASE_DIR / "data"
FILES_DIR = DATA_DIR / "files"          # 证书附件副本
EXPORT_DIR = DATA_DIR / "exports"       # 导出产物
BACKUP_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "library.db"
LOG_PATH = DATA_DIR / "app.log"
ICON_PATH = resource_dir() / "assets" / "app.ico"


def ensure_dirs() -> None:
    for d in (DATA_DIR, FILES_DIR, EXPORT_DIR, BACKUP_DIR):
        d.mkdir(parents=True, exist_ok=True)
