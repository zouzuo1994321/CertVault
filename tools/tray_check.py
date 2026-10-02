# -*- coding: utf-8 -*-
"""系统托盘回归探针（v1.4.0）。

覆盖 5 组共 24 项断言：
  1. 托盘模块本身：可用性/ 图标 / 菜单项 / 勾选态 / 提示文案
  2. 最小化收进托盘：窗口隐藏、任务栏不再有它、悬浮窗仍驻留
  3. 悬浮窗独立性：原生 ``IsWindowVisible`` + ``GW_OWNER`` 必须为 0
     （这是本轮最关键的一条 —— ``QWidget.isVisible()`` 在 owned window
      被系统藏掉时**仍返回 True**，只看它会漏判）
  4. 从托盘恢复：showNormal 后窗口可见且非最小化
  5. 关窗口 ≠ 退出：closeEvent 被 ignore，真退出才放行

用法：  <venv>/Scripts/python.exe tools/tray_check.py
退出码 0 = 全绿。
⚠️ 不要设 QT_QPA_PLATFORM=offscreen（Windows 下该插件字体库为空）。
"""

from __future__ import annotations

import ctypes
import shutil
import sys
import tempfile
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QSystemTrayIcon  # noqa: E402

OK: list[str] = []
FAIL: list[str] = []

GWL_EXSTYLE = -20
GW_OWNER = 4
WS_EX_TOOLWINDOW = 0x00000080

_u32 = ctypes.windll.user32
_u32.IsWindowVisible.argtypes = [wintypes.HWND]
_u32.IsWindowVisible.restype = wintypes.BOOL
_u32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_u32.GetWindowLongW.restype = ctypes.c_long
_u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
_u32.GetWindow.restype = wintypes.HWND


def chk(name: str, cond: bool, extra: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (f"  {extra}" if extra else ""))


def native_visible(w) -> bool:
    """Windows 原生可见性 —— owned window 被系统藏掉时 Qt 的 isVisible() 仍是 True。"""
    return bool(_u32.IsWindowVisible(int(w.winId())))


def native_owner(w) -> int:
    # ⚠️ GetWindow 的 restype 是 HWND(=c_void_p) → **无 owner 时返回 None 而非 0**。
    # 写 `owner == 0` 永远为 False，会把「本来就独立」误判成「有 owner」。
    #统一用 `or 0` 归一成整数。
    return int(_u32.GetWindow(int(w.winId()), GW_OWNER) or 0)


def native_exstyle(w) -> int:
    return int(_u32.GetWindowLongW(int(w.winId()), GWL_EXSTYLE))


def pump(app, n: int = 8) -> None:
    for _ in range(n):
        app.processEvents()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cv_tray_"))
    app = QApplication(sys.argv)
    from app import db as dbm, palette, sampledata
    palette.apply_palette(app)
    app.setQuitOnLastWindowClosed(False)

    db = dbm.Database(tmp / "t.db")
    sampledata.load_samples(db)
    db.set_setting("popup_on_start", "0")

    from app.main_window import MainWindow
    win = MainWindow(db)
    # ★ 这里**不能**用 WA_DontShowOnScreen。
    #   那一行会让窗口在 Windows 原生层始终「不可见」，于是
    #   `IsWindowVisible(hwnd)` 恒为 False —— 而本探针要验的恰恰是原生层行为
    #   （owned window 被系统藏掉时 `QWidget.isVisible()` 仍返回 True）。
    #   用它做托盘探针，断言会「全绿但什么都没测到」。
    #   改成真显示 + 挪到主屏之外：既有真实原生行为，又不打扰用户。
    win.resize(1280, 800)
    win.move(-2400, 0)
    win.show()
    pump(app, 10)
    print(f"[info] 主窗口原生可见={native_visible(win)}（挪到主屏外，不打扰桌面）")

    print("\n=== 1. 托盘模块 ===")
    tray = win._ensure_tray()
    chk("系统托盘可用", QSystemTrayIcon.isSystemTrayAvailable())
    chk("托盘对象已创建", tray is not None)
    if tray is None:
        print("\n[abort] 本机没有系统托盘，后续断言无法执行")
        shutil.rmtree(tmp, ignore_errors=True)
        return 1
    chk("托盘图标已 show", tray.icon.isVisible())
    chk("提示带版本号", version_in(tray.icon.toolTip()),
        tray.icon.toolTip())
    texts = [a.text() for a in tray.menu.actions() if a.text()]
    chk("菜单含五个动作",
        texts == ["显示主窗口", "到期提醒", "隐藏窗口悬浮窗",
                  "立即检查提醒", "退出证书管理库"]
        or texts == ["显示主窗口", "到期提醒", "窗口悬浮窗",
                     "立即检查提醒", "退出证书管理库"], str(texts))
    chk("退出是最后一项", texts[-1].startswith("退出"), texts[-1])
    chk("悬浮窗项可勾选", tray.act_float.isCheckable())
    chk("待关注数进提示", "待关注" in tray.icon.toolTip(),
        tray.icon.toolTip())
    tray.set_float_on(True)
    chk("勾选态同步", tray.act_float.isChecked()
        and tray.act_float.text() == "隐藏窗口悬浮窗", tray.act_float.text())
    tray.set_float_on(False)
    chk("取消勾选后文案变开", tray.act_float.text() == "窗口悬浮窗",
        tray.act_float.text())
    chk("支持桌面通知", QSystemTrayIcon.supportsMessages())

    print("\n=== 2. 最小化收进托盘 ===")
    fw = win._ensure_float()
    fw.setGeometry(260, 200, 344, 420)
    fw.show_window()
    pump(app, 8)
    chk("悬浮窗已显示", native_visible(fw))
    win.minimize_to_tray()
    pump(app, 10)
    chk("主窗口已隐藏", not win.isVisible())
    chk("主窗口不是最小化态（是收进托盘）", not win.isMinimized())
    chk("原生层主窗口不可见", not native_visible(win))
    chk("悬浮窗仍驻留桌面", native_visible(fw),
        f"IsWindowVisible={native_visible(fw)}")
    chk("托盘图标仍在", tray.icon.isVisible())

    print("\n=== 3. 悬浮窗独立性（原生层）==")
    chk("owner == 0（不是 owned window）", native_owner(fw) == 0,
        f"owner=0x{native_owner(fw):08X}")
    chk("WS_EX_TOOLWINDOW 置位（不进任务栏）",
        bool(native_exstyle(fw) & WS_EX_TOOLWINDOW))
    chk("Qt 层isVisible 与原生一致",
        fw.isVisible() == native_visible(fw),
        f"Qt={fw.isVisible()} 原生={native_visible(fw)}")

    print("\n=== 4. 从托盘恢复 ===")
    win._raise_from_tray()
    pump(app, 10)
    chk("主窗口恢复可见", win.isVisible())
    chk("恢复后不是最小化态", not win.isMinimized())
    chk("原生层可见", native_visible(win))

    print("\n=== 5. 关窗口 ≠ 退出 ===")
    win.close()
    pump(app, 10)
    chk("close 被拦截（收进托盘）", win.isVisible() is False)
    chk("进程仍在（未退出）", tray.icon.isVisible())
    chk("退出闸门仍为 False", win._quitting is False)
    win._raise_from_tray()
    pump(app, 6)

    # 真退出：置闸门后再 close
    win.quit_app()
    pump(app, 8)
    chk("退出闸门已置位", win._quitting is True)
    chk("托盘图标已收掉", not tray.icon.isVisible())

    try:
        db.close()
    except Exception:  # noqa: BLE001
        pass
    shutil.rmtree(tmp, ignore_errors=True)

    print("\n=== 汇总 ===")
    print(f"通过 {len(OK)} / {len(OK) + len(FAIL)}")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  - " + f)
    return 1 if FAIL else 0


def version_in(text: str) -> bool:
    from app import version
    return version.APP_VERSION in text


if __name__ == "__main__":
    sys.exit(main())