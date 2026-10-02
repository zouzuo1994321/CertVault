# -*- coding: utf-8 -*-
"""离屏回归：逐页渲染主窗口、校验数据链路、导出界面效果图。

说明：不能用 QT_QPA_PLATFORM=offscreen —— 该平台插件在 Windows 下
字体库为空（QFontDatabase.families() 返回 0），中文会渲染成方块。
因此这里使用真实 windows 平台 + WA_DontShowOnScreen，窗口不弹出来但字体正确。
"""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

SHOT_DIR = ROOT / "docs" / "shots"
SHOT_DIR.mkdir(parents=True, exist_ok=True)


def prep(widget) -> None:
    """让窗口完成布局但不真正弹到屏幕上，避免打扰用户。"""
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.show()


def main() -> int:
    from app import icons, theme, version  # noqa: F401
    from app.db import Database
    from app.main_window import MainWindow
    from app.palette import apply_palette
    from app.sampledata import load_samples

    app = QApplication(sys.argv)
    apply_palette(app)

    db_path = ROOT / "data" / "_devcheck.db"
    if db_path.exists():
        db_path.unlink()
    database = Database(db_path)
    n = load_samples(database)
    # 关掉启动弹窗，避免回归脚本被模态对话框阻塞
    database.set_setting("popup_on_start", "0")
    print(f"[check] 示例数据 {n} 条")

    win = MainWindow(database)
    win.resize(1440, 900)
    prep(win)
    app.processEvents()

    failures = []
    for key in ("dashboard", "certs", "reminders", "exams", "materials", "about"):
        try:
            win.goto(key)
            # 效果图必须是「静止态」：先停掉 60fps 定时器（否则待机呼吸会一直
            # 改柔光强度，同一份代码两次截图都不一样），再把入场 / 数字滚动 /
            # 条形生长一步推到终态、视线与呼吸归零。
            scene = getattr(win.pages.get(key), "_scene", None)
            if scene is not None:
                scene.stop()
                scene.settle()
            app.processEvents()
            pm = win.grab()
            out = SHOT_DIR / f"{key}.png"
            pm.save(str(out))
            print(f"[check] {key:10s} OK  {pm.width()}x{pm.height()}  -> {out.name}")
        except Exception as exc:  # noqa: BLE001
            failures.append((key, repr(exc)))
            print(f"[check] {key:10s} FAIL {exc!r}")
            traceback.print_exc()

    # 悬浮窗（独立顶层窗口，不进主窗口截图）
    try:
        from app.floatwin import BLOCKS, FloatWindow
        database.set_setting("float_blocks", ",".join(k for k, _ in BLOCKS))
        fw = FloatWindow(database)
        fw.resize(fw.width(), fw.height())      # 触发一次尺寸落定
        prep(fw)
        fw.refresh()
        app.processEvents()
        # 半透明底 + 圆角：直接存 PNG 四角是透明的，垫一层灰底才看得出边缘
        from PySide6.QtGui import QColor, QImage, QPainter
        src = fw.grab().toImage()
        pad = 16
        canvas = QImage(src.width() + pad * 2, src.height() + pad * 2,
                        QImage.Format_ARGB32)
        canvas.fill(QColor("#8593a3"))
        p = QPainter(canvas)
        p.drawImage(pad, pad, src)
        p.end()
        out = SHOT_DIR / "floatwin.png"
        canvas.save(str(out))
        print(f"[check] {'floatwin':10s} OK  {canvas.width()}x{canvas.height()}  -> {out.name}")
        fw.close()
    except Exception as exc:  # noqa: BLE001
        failures.append(("floatwin", repr(exc)))
        print(f"[check] floatwin   FAIL {exc!r}")
        traceback.print_exc()

    # 打开各个对话框做一次构造校验（不进入事件循环）
    try:
        from app.dialogs import (CertDialog, CategoryDialog, ExamDialog,
                                 MaterialDialog, PdfViewer, ReminderDialog,
                                 SettingsDialog)
        certs = database.certificates()
        cid = certs[0]["id"]
        d1 = CertDialog(database, cid, win)
        d2 = CertDialog(database, None, win)
        d3 = ExamDialog(database, None, win)
        d4 = MaterialDialog(database, None, win)
        d5 = CategoryDialog(database, win)
        d6 = SettingsDialog(database, win)
        d7 = ReminderDialog(database, win, startup=True)
        print("[check] 对话框构造 OK")
        for name, dlg in (("dlg_cert", d1), ("dlg_exam", d3),
                          ("dlg_material", d4), ("dlg_category", d5),
                          ("dlg_settings", d6), ("dlg_reminder", d7)):
            dlg.resize(900, 660)
            prep(dlg)
            app.processEvents()
            dlg.grab().save(str(SHOT_DIR / f"{name}.png"))
            dlg.close()
        for d in (d1, d2, d3, d4, d5, d6, d7):
            d.deleteLater()
    except Exception as exc:  # noqa: BLE001
        failures.append(("dialogs", repr(exc)))
        print(f"[check] dialogs FAIL {exc!r}")
        traceback.print_exc()

    # PDF 预览（用导出的信息单做输入）
    try:
        from app import pdfexport
        from app.dialogs import PdfViewer
        cert = database.certificate_with_status(certs[0]["id"])
        out = ROOT / "data" / "exports" / "_devcheck.pdf"
        pdfexport.export_certificate(cert, [], out)
        v = PdfViewer(out, "自检预览", win)
        v.resize(900, 700)
        prep(v)
        # QPdfDocument 异步渲染，等它画完再截图
        import time
        for _ in range(30):
            app.processEvents()
            time.sleep(0.05)
        v.grab().save(str(SHOT_DIR / "pdf_viewer.png"))
        v.close()
        print(f"[check] pdf_viewer OK  大小 {out.stat().st_size} 字节")
    except Exception as exc:  # noqa: BLE001
        failures.append(("pdf_viewer", repr(exc)))
        print(f"[check] pdf_viewer FAIL {exc!r}")
        traceback.print_exc()

    win.close()
    database.close()
    print("[check] 失败项：", failures if failures else "无")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
