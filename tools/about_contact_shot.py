# -*- coding: utf-8 -*-
"""把「关于与声明」页的联系作者卡片裁出来放大，用于核对品牌标识观感。

用法：<venv>/Scripts/python.exe tools/about_contact_shot.py
输出：build/diag/about_contact.png

⚠️ 沿用 offscreen_check 的做法：真实 windows 平台 + WA_DontShowOnScreen，
   不能设 QT_QPA_PLATFORM=offscreen（该插件下字体库为空，中文会变方块）。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, Qt          # noqa: E402
from PySide6.QtWidgets import QApplication     # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "build", "diag")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    from app.db import Database
    from app.main_window import MainWindow
    from app.pages import ContactRow
    from app.palette import apply_palette
    from app.sampledata import load_samples

    app = QApplication(sys.argv)
    apply_palette(app)

    db = Database()
    load_samples(db)

    win = MainWindow(db)
    win.resize(1440, 900)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    win.goto("about")
    for _ in range(6):
        app.processEvents()

    rows = win.findChildren(ContactRow)
    if len(rows) < 4:
        print(f"[shot] ContactRow 数量异常：{len(rows)}（应为 4）")
        return 1

    # ★ 用 mapTo 换算到**窗口坐标**再裁：卡片在 QScrollArea 里，
    # 直接拿局部 geometry 会得到 1162x282 的错误范围（scroll 内容比窗口大得多）。
    tops = [r.mapTo(win, r.rect().topLeft()) for r in rows]
    left = min(t.x() for t in tops)
    right = max(t.x() + r.width() for t, r in zip(tops, rows))
    top = min(t.y() for t in tops)
    bottom = max(t.y() + r.height() for t, r in zip(tops, rows))
    box = QRect(left - 16, top - 32, right - left + 32, bottom - top + 46)
    box = box.intersected(win.rect())

    shot = win.grab(box)
    path = os.path.join(OUT, "about_contact.png")
    shot.save(path)
    print(f"[shot] 卡片窗口坐标 {box.x()},{box.y()} {box.width()}x{box.height()}")
    print(f"[shot] 联系作者卡片 {shot.width()}x{shot.height()} -> {path}")
    print(f"[shot] 行数 {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())