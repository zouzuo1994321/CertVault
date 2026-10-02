# -*- coding: utf-8 -*-
"""截出设置面板里的「开机自启」卡片，用于核对观感。

用法：<venv>/Scripts/python.exe tools/autostart_shot.py
输出：build/diag/autostart_card.png
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QRect, Qt          # noqa: E402
from PySide6.QtGui import QImage                     # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "build", "diag")


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    from app import autostart, palette
    from app.db import Database
    from app.dialogs import SettingsDialog

    app = QApplication(sys.argv)
    palette.apply_palette(app)

    db = Database()
    dlg = SettingsDialog(db)
    # ⚠️ 这里**不要**设 WA_DontShowOnScreen：该标志会让 grab() 返回空图。
    # 改用真 show()+ move()挪到主屏外，与 tray_check 验证原生行为时的做法一致。
    dlg.setAttribute(Qt.WA_DontShowOnScreen, False)
    dlg.show()
    dlg.move(-2400, 0)
    for _ in range(8):
        app.processEvents()

    # 开机自启卡片在滚动区**最底部**，默认视口看不到 —— 先滚到底再截图。
    from PySide6.QtWidgets import QScrollArea

    for sa in dlg.findChildren(QScrollArea):
        bar = sa.verticalScrollBar()
        bar.setValue(bar.maximum())
    for _ in range(8):
        app.processEvents()

    # 开机自启卡片 = cb_autostart 的祖先 Card（objectName 是 CardBox）
    card = dlg.cb_autostart.parentWidget()
    while card is not None and card.objectName() != "CardBox":
        card = card.parentWidget()
    if card is None:
        print("[shot] 没找到 Card 容器")
        return 1

    top_left = card.mapTo(dlg, card.rect().topLeft())
    bottom_right = card.mapTo(dlg, card.rect().bottomRight())
    box = QRect(top_left, bottom_right).adjusted(-16, -10, 16, 10)

    path = os.path.abspath(os.path.join(OUT, "autostart_card.png"))
    # ⚠️ 踩过的坑：① `grab()` 在 WA_DontShowOnScreen 下返回空图；② `render()` 带
    # sourceRegion 裁剪在对话框上输出全白。稳妥做法 = 真 show() 后 grab() 整窗，
    # 再用 QImage.copy() 裁。
    full = dlg.grab()
    if full.isNull():
        print("[shot] grab() 返回空图")
        return 1
    img = full.copy(box).toImage().convertToFormat(QImage.Format_ARGB32_Premultiplied)
    if not img.save(path, "PNG"):
        print(f"[shot] save 失败 -> {path}")
        return 1
    size = os.path.getsize(path) if os.path.exists(path) else 0
    print(f"[shot] 开机自启卡片 {img.width()}x{img.height()} "
          f"({size} 字节) -> {path}")
    print(f"[shot] 状态：{autostart.status()}")

    dlg.reject()
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())