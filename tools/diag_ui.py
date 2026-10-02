# -*- coding: utf-8 -*-
"""渲染缺陷排查工具：把图标表与界面局部按原始像素放大导出。

界面出问题时（图标残缺、文字裁切、颜色异常），整窗截图缩到屏幕宽度后根本看不出细节。
本工具做两件事：
    1. 把 app.icons 里全部图标按 16/24/48 三档画成一张对照表；
    2. 把主窗口按 3 倍最近邻放大裁切成若干局部（侧边栏 / 工具栏 / 顶栏 / 筛选条 / 状态栏）。

产物在 `build/diag/`。定位「图标只剩左上角一块」就是靠它一眼命中的。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QRect, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

OUT = ROOT / "build" / "diag"
OUT.mkdir(parents=True, exist_ok=True)


def icon_sheet(app) -> None:
    from app import icons
    names = sorted(icons._DISPATCH)
    cols, cell = 8, 96
    rows = (len(names) + cols - 1) // cols
    img = QImage(cols * cell, rows * cell, QImage.Format_ARGB32)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    for i, n in enumerate(names):
        r, c = divmod(i, cols)
        x, y = c * cell, r * cell
        for k, size in enumerate((16, 24, 48)):
            pm = icons.pixmap(n, "#2e6f9e", size)
            p.drawPixmap(x + 8 + k * 28, y + 10, int(size), int(size), pm)
        p.setPen(QColor("#333333"))
        p.setFont(QFont("Microsoft YaHei UI", 8))
        p.drawText(x + 6, y + 78, n)
        p.setPen(QColor("#dddddd"))
        p.drawRect(x, y, cell - 1, cell - 1)
    p.end()
    img.save(str(OUT / "icon_sheet.png"))
    print("[diag] icon_sheet.png", img.width(), img.height())


# 主窗口与数据库的存活引用。
# 主窗口内部有跨天检查定时器，会在后续每一次 processEvents 里继续跑并读数据库；
# 如果这里提前 db.close()，popup_crops() 阶段就会抛
# sqlite3.ProgrammingError: Cannot operate on a closed database。
# 因此整个诊断流程共用一份连接，最后统一关闭。
_ALIVE: dict = {}


def window_crops(app) -> None:
    from app.db import Database
    from app.main_window import MainWindow

    db_path = ROOT / "data" / "_diag.db"
    if db_path.exists():
        db_path.unlink()
    db = Database(db_path)
    db.set_setting("popup_on_start", "0")
    _ALIVE["db"] = db

    win = MainWindow(db)
    _ALIVE["win"] = win
    win.resize(1500, 950)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()

    for key in ("certs", "exams"):
        win.goto(key)
        for _ in range(10):
            app.processEvents()
            time.sleep(0.03)
        full = win.grab()
        full.save(str(OUT / f"window_{key}.png"))
        if key != "certs":
            continue
        crops = {
            "crop_sidebar": QRect(0, 0, 212, 470),
            "crop_toolbar": QRect(212, 70, 1000, 70),
            "crop_topright": QRect(1180, 70, 200, 60),
            "crop_infobar": QRect(212, 912, 1000, 38),
            "crop_sidebarfoot": QRect(0, 858, 212, 92),
            "crop_filterbar": QRect(212, 140, 1000, 55),
        }
        for name, rect in crops.items():
            # 3 倍放大，方便看清单个像素
            sub = full.copy(rect)
            big = sub.scaled(sub.width() * 3, sub.height() * 3,
                             Qt.IgnoreAspectRatio, Qt.FastTransformation)
            big.save(str(OUT / f"{name}.png"))
        print("[diag] crops done,", full.width(), full.height())


def popup_crops(app) -> None:
    """导出各类「弹层」的外观：下拉列表、日历、菜单、工具提示。

    这些弹层是独立顶层窗口，不跟着主窗口截图走，且最容易受系统深色主题 /
    强调色影响（未在 QSS 里写死颜色的地方会直接吃系统调色板）。
    """
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import (QCalendarWidget, QComboBox, QDateEdit, QMenu,
                                   QToolTip, QWidget)
    from app import theme

    holder = QWidget()
    holder.resize(360, 120)
    holder.setAttribute(Qt.WA_DontShowOnScreen, True)

    combo = QComboBox(holder)
    combo.setEditable(True)
    combo.addItems(["职业资格", "语言能力", "学历学位", "技能认证", "其他"])
    combo.move(10, 10)
    combo.resize(200, 30)
    holder.show()
    for _ in range(6):
        app.processEvents()
        time.sleep(0.02)
    combo.showPopup()
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    view = combo.view()
    popup = view.window()
    popup.grab().save(str(OUT / "popup_combo.png"))
    print("[diag] popup_combo.png", popup.width(), popup.height())
    combo.hidePopup()
    app.processEvents()

    de = QDateEdit(QDate(2027, 10, 2), holder)
    de.setCalendarPopup(True)
    de.move(10, 50)
    de.resize(200, 30)
    de.setAttribute(Qt.WA_DontShowOnScreen, True)
    cal = de.calendarWidget()
    if cal is not None:
        cal.setAttribute(Qt.WA_DontShowOnScreen, True)
        cal.resize(280, 220)
        cal.show()
        de.setDate(QDate(2027, 10, 2))
        for _ in range(10):
            app.processEvents()
            time.sleep(0.02)
        cal.grab().save(str(OUT / "popup_calendar.png"))
        print("[diag] popup_calendar.png", cal.width(), cal.height())
        cal.close()

    menu = QMenu(holder)
    menu.addAction("导出证书信息单 (PDF)")
    menu.addAction("导出台账 PDF")
    menu.addAction("导出 CSV")
    menu.setAttribute(Qt.WA_DontShowOnScreen, True)
    menu.popup(holder.mapToGlobal(combo.pos()))
    for _ in range(8):
        app.processEvents()
        time.sleep(0.02)
    menu.grab().save(str(OUT / "popup_menu.png"))
    menu.close()

    QToolTip.showText(holder.mapToGlobal(combo.pos()), "测试工具提示", holder)
    for _ in range(8):
        app.processEvents()
        time.sleep(0.02)
    holder.close()
    print("[diag] popups done; 主题 QSS 已应用 =", bool(app.styleSheet()))


def main() -> int:
    from app.palette import apply_palette
    app = QApplication(sys.argv)
    # 与 main.py 完全一致：Fusion + 浅色调色板 + 全局样式表
    apply_palette(app)
    print("[diag] 已应用显式浅色调色板，样式 =", app.style().objectName())
    icon_sheet(app)
    window_crops(app)
    popup_crops(app)
    win = _ALIVE.get("win")
    db = _ALIVE.get("db")
    if win is not None:
        win.close()
    if db is not None:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
