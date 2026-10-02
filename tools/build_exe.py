# -*- coding: utf-8 -*-
"""一键打包：PyInstaller 单文件 exe + 旧版归档 + 冻结态自检。

构建流程（与 README 的迭代约定一致）：
    1. 把根目录里上一版 exe 归档到 history/（用 .last_build 记录旧版本号命名）；
    2. PyInstaller 打成单文件、无控制台窗口的绿色 exe；
    3. 新 exe 放到项目根目录，文件名固定为「证书管理库.exe」；
    4. 立刻用 exe 自带 --selftest 做一次冻结态自检，输出 JSON 报告。

不删除任何文件（只做移动/重命名），避免触发 safe-delete 拦截。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENV = Path(r"C:\Users\zouzu\.workbuddy\binaries\python\envs\default")
PYINSTALLER = VENV / "Scripts" / "pyinstaller.exe"

APP_EXE_NAME = "证书管理库"
HISTORY = ROOT / "history"
BUILD = ROOT / "build"
SIDECAR = HISTORY / ".last_build"

# 本项目用不到的 Qt 模块，显式排除以缩小体积（--collect-submodules PySide6 会全量收集）
EXCLUDES = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngine", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets", "PySide6.QtQml", "PySide6.QtQmlModels",
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtDesigner", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtRemoteObjects", "PySide6.QtScxml", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtNetworkAuth",
    "PySide6.QtHelp", "PySide6.QtUiTools", "PySide6.QtPdfQuick",
]


def read_version() -> tuple[str, str]:
    src = (ROOT / "app" / "version.py").read_text(encoding="utf-8")
    ver = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', src).group(1)  # type: ignore[union-attr]
    build = re.search(r'BUILD\s*=\s*"([^"]+)"', src).group(1)  # type: ignore[union-attr]
    return ver, build


def archive_current(tag: str) -> Path | None:
    """把根目录当前 exe 移到 history/。"""
    cur = ROOT / f"{APP_EXE_NAME}.exe"
    if not cur.exists():
        return None
    HISTORY.mkdir(parents=True, exist_ok=True)
    label = SIDECAR.read_text(encoding="utf-8").strip() if SIDECAR.exists() else ""
    if not label:
        label = datetime.fromtimestamp(cur.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[\\/:*?"<>|\s]+', "", label)
    dst = HISTORY / f"{APP_EXE_NAME}_{safe}.exe"
    i = 2
    while dst.exists():
        dst = HISTORY / f"{APP_EXE_NAME}_{safe}_{i}.exe"
        i += 1
    shutil.move(str(cur), str(dst))
    print(f"[archive] 旧版本 → {dst.name}")
    return dst


def run_pyinstaller() -> Path:
    cmd = [
        str(PYINSTALLER),
        "--noconfirm", "--clean", "--noconsole", "--onefile",
        "--name", APP_EXE_NAME,
        "--icon", str(ROOT / "assets" / "app.ico"),
        "--distpath", str(BUILD / "dist"),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        "--collect-submodules", "PySide6",
        "--hidden-import", "PySide6.QtPdf",
        "--hidden-import", "PySide6.QtPdfWidgets",
        "--paths", str(ROOT),
    ]
    for name in EXCLUDES:
        cmd += ["--exclude-module", name]
    cmd.append(str(ROOT / "main.py"))
    print("[build] PyInstaller 打包中，请稍候…")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"PyInstaller 失败，退出码 {proc.returncode}")
    exe = BUILD / "dist" / f"{APP_EXE_NAME}.exe"
    if not exe.exists():
        raise SystemExit(f"未找到产物 {exe}")
    print(f"[build] 打包完成，用时 {time.time() - t0:.0f}s，"
          f"体积 {exe.stat().st_size / 1024 / 1024:.1f} MB")
    return exe


def selftest(exe: Path, ver: str, build: str) -> bool:
    report = ROOT / f"selftest_exe_{build}.json"
    print("[verify] 冻结态自检…")
    try:
        subprocess.run([str(exe), "--selftest", str(report)],
                       timeout=180, capture_output=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 自检进程异常：{exc}")
        return False
    if not report.exists():
        print("[verify] 未生成自检报告")
        return False
    data = json.loads(report.read_text(encoding="utf-8"))
    for c in data["checks"]:
        mark = "OK  " if c["ok"] else "FAIL"
        print(f"[verify]   {mark} {c['name']}：{c['detail']}")
    print(f"[verify] 结论：{'全部通过' if data['ok'] else '存在失败项'}")
    return bool(data["ok"])


def smoke(exe: Path) -> bool:
    """冻结态 GUI 冒烟：真实渲染六大页面，验证打包未漏 Qt 子模块。"""
    out = ROOT / "build" / "smoke"
    print("[verify] 冻结态 GUI 冒烟…")
    try:
        subprocess.run([str(exe), "--smoke", str(out)], timeout=300, capture_output=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[verify] 冒烟进程异常：{exc}")
        return False
    report = out / "_smoke.json"
    if not report.exists():
        print("[verify] 未生成冒烟报告")
        return False
    data = json.loads(report.read_text(encoding="utf-8"))
    for p in data["pages"]:
        mark = "OK  " if p.get("ok") else "FAIL"
        print(f"[verify]   {mark} {p['page']:10s} {p.get('px','')}  "
              f"{p.get('png_bytes', 0)} 字节 {p.get('error','')}")
    print(f"[verify] GUI 冒烟结论：{'通过' if data['ok'] else '存在失败项'}")
    return bool(data["ok"])


def main() -> int:
    ver, build = read_version()
    print(f"[info] 目标版本 {ver} ({build})")

    archive_current(build)
    exe = run_pyinstaller()

    target = ROOT / f"{APP_EXE_NAME}.exe"
    if target.exists():  # 理论上已被 archive 移走；兜底再加时间戳归档
        archive_current(build)
    shutil.move(str(exe), str(target))
    print(f"[deliver] 最新版本 → {target}")

    HISTORY.mkdir(parents=True, exist_ok=True)
    SIDECAR.write_text(f"{ver} ({build})", encoding="utf-8")

    ok = selftest(target, ver, build)
    ok = smoke(target) and ok
    print(f"[done] 版本 {ver} ({build}) · 根目录 exe 已就绪 · "
          f"自检 {'通过' if ok else '未通过'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
