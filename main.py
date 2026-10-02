# -*- coding: utf-8 -*-
"""证书管理库 · CertVault —— 程序入口。

启动流程：
    1. 清理上一轮未正常退出的残留进程（仅 exe 态）；
    2. 打开 / 初始化本地数据库；
    3. 构建主窗口，调度到期提醒。

运行参数：
    --selftest <报告路径>   无界面自检，写入 JSON 报告后退出（用于打包后验收）
    --smoke <输出目录>      冻结态 GUI 冒烟，真实渲染六大页面并输出 JSON 结论
"""

from __future__ import annotations

import os
import sys
import traceback

# 保证以源码目录为根，便于 `python main.py` 直接运行
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_logging() -> None:
    from app import paths
    try:
        paths.ensure_dirs()
        sys.stderr = open(paths.LOG_PATH, "a", encoding="utf-8", buffering=1)
    except Exception:  # noqa: BLE001
        pass


def run_selftest(report_path: str) -> int:
    """无界面自检：数据库读写、PDF 引擎、图标绘制、导出链路。"""
    import json
    import tempfile
    from pathlib import Path

    result = {"ok": True, "checks": [], "error": ""}

    def check(name: str, fn) -> None:
        try:
            detail = fn()
            result["checks"].append({"name": name, "ok": True, "detail": str(detail)})
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["checks"].append({"name": name, "ok": False, "detail": repr(exc)})

    from app import paths, pdfexport, version
    from app.db import Database

    check("版本号", lambda: version.FULL_VERSION)

    def _db() -> str:
        tmp = Path(tempfile.mkdtemp(prefix="certvault_"))
        d = Database(tmp / "t.db")
        cid = d.save_certificate({
            "name": "自检证书", "category": "职业资格", "number": "T-001",
            "holder": "测试", "issuer": "自检机构", "level": "初级",
            "issue_date": "2026-01-01", "expiry_date": "2026-12-31",
            "active": 1, "remark": "selftest"})
        d.save_exam({"name": "自检考试", "category": "职业资格",
                     "exam_date": "2026-12-01", "reg_deadline": "2026-11-01",
                     "location": "线上", "fee": "0", "state": "计划中",
                     "score": "", "remark": ""})
        d.save_material({"title": "自检资料", "category": "其他", "kind": "link",
                         "target": "https://example.com", "note": ""})
        rows = d.certificates()
        assert len(rows) == 1 and rows[0]["status_key"] in ("valid", "soon", "urgent"), rows
        d.delete_certificate(cid)
        assert d.certificates() == []
        d.close()
        return "CRUD 正常"

    check("数据库", _db)

    def _pdf_export() -> str:
        from pathlib import Path
        tmp = Path(tempfile.mkdtemp(prefix="certvault_pdf_"))
        cert = {"name": "自检证书", "category": "职业资格", "number": "T-001",
                "holder": "测试", "issuer": "自检机构", "level": "初级",
                "issue_date": "2026-01-01", "expiry_date": "2026-12-31",
                "active": 1, "remark": "自检", "status_label": "有效",
                "left_text": "剩余 90 天"}
        from PySide6.QtGui import QGuiApplication
        p1 = pdfexport.export_certificate(cert, [], tmp / "a.pdf")
        p2 = pdfexport.export_ledger([cert], tmp / "b.pdf")
        p3 = pdfexport.export_csv([cert], tmp / "c.csv")
        sizes = [p1.stat().st_size, p2.stat().st_size, p3.stat().st_size]
        assert sizes[0] > 3000 and sizes[1] > 3000 and sizes[2] > 100, sizes
        return f"PDF/CSV 导出正常 {sizes}"

    check("导出链路", _pdf_export)

    def _qtpdf() -> str:
        from PySide6.QtPdf import QPdfDocument
        from PySide6.QtPdfWidgets import QPdfView
        tmp = tempfile.mktemp(suffix=".pdf")
        from PySide6.QtGui import QPainter, QPdfWriter
        w = QPdfWriter(tmp)
        p = QPainter(w)
        p.drawText(100, 100, "hello")
        p.end()
        doc = QPdfDocument()
        err = doc.load(tmp)
        n = doc.pageCount()
        assert n >= 1, (err, n)
        return f"QtPdf 可用，自建 PDF {n} 页"

    check("PDF 预览引擎", _qtpdf)

    def _icons() -> str:
        from app import icons
        names = ["dashboard", "cert", "bell", "calendar", "book", "info", "pdf",
                 "export", "trash", "settings"]
        for n in names:
            pm = icons.pixmap(n, "#2e6f9e", 20)
            assert not pm.isNull(), n
        assert not icons.logo_pixmap(64, 1.0).isNull()
        return f"{len(names)} 个矢量图标绘制正常"

    check("图标绘制", _icons)

    def _autostart() -> str:
        # ★ 只**读**注册表，绝不在自检里写 —— 自检可能被人反复跑，
        # 也可能在别人机器上跑，写了就是擅自改用户的开机启动项。
        from app import autostart
        on = autostart.is_enabled()
        assert isinstance(on, bool)
        return f"{'已注册' if on else '未注册'}（{'支持' if autostart.is_supported() else '当前环境不支持'}）"

    check("开机自启", _autostart)

    def _paths() -> str:
        return f"数据目录 {paths.DATA_DIR}"

    check("路径解析", _paths)

    Path(report_path).write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def run_smoke(out_dir: str) -> int:
    """冻结态 GUI 冒烟：真实构建主窗口并逐页渲染，输出 JSON 结论。

    用于验证打包后的 exe 在缺少某些 Qt 子模块时是否仍能正常出界面。
    """
    import json
    import tempfile
    import time
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from app.db import Database
    from app.main_window import MainWindow
    from app.palette import apply_palette
    from app.sampledata import load_samples

    app = QApplication(sys.argv)
    apply_palette(app)
    tmp = Path(tempfile.mkdtemp(prefix="certvault_smoke_"))
    db = Database(tmp / "smoke.db")
    load_samples(db)
    db.set_setting("popup_on_start", "0")

    result = {"ok": True, "pages": [], "error": ""}
    win = MainWindow(db)
    win.resize(1440, 900)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    for key in ("dashboard", "certs", "reminders", "exams", "materials", "about"):
        try:
            win.goto(key)
            scene = getattr(win.pages.get(key), "_scene", None)
            if scene is not None:      # 把入场/滚动/生长推到终态，截图才可复现
                scene.settle()
            for _ in range(4):
                app.processEvents()
                time.sleep(0.02)
            png = out / f"{key}.png"
            pm = win.grab()
            pm.save(str(png))
            size = png.stat().st_size
            ok = pm.width() > 800 and size > 15000
            result["pages"].append({"page": key, "ok": ok, "px": f"{pm.width()}x{pm.height()}",
                                    "png_bytes": size})
            if not ok:
                result["ok"] = False
        except Exception as exc:  # noqa: BLE001
            result["ok"] = False
            result["pages"].append({"page": key, "ok": False, "error": repr(exc)})

    # 悬浮窗：半透明 + 无边框 + Qt.Tool 的独立顶层窗口，是打包时最容易缺子模块的形态，
    # 所以单独渲染一次（光看主窗口六页测不出它）。
    try:
        from app.floatwin import FloatWindow
        fw = FloatWindow(db)
        fw.setAttribute(Qt.WA_DontShowOnScreen, True)
        fw.show()
        fw.refresh()
        for _ in range(4):
            app.processEvents()
            time.sleep(0.02)
        png = out / "floatwin.png"
        pm = fw.grab()
        pm.save(str(png))
        ok = (pm.width() == fw.width() and pm.height() > 150
              and png.stat().st_size > 8000)
        result["pages"].append({"page": "floatwin", "ok": ok,
                                "px": f"{pm.width()}x{pm.height()}",
                                "png_bytes": png.stat().st_size})
        if not ok:
            result["ok"] = False
        fw.close()
    except Exception as exc:  # noqa: BLE001
        result["ok"] = False
        result["pages"].append({"page": "floatwin", "ok": False, "error": repr(exc)})

    win.close()
    db.close()
    (out / "_smoke.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result["ok"] else 1


def main() -> int:
    argv = sys.argv[1:]
    if "--selftest" in argv:
        idx = argv.index("--selftest")
        out = argv[idx + 1] if len(argv) > idx + 1 else "selftest.json"
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QGuiApplication
        _app = QGuiApplication(sys.argv)
        return run_selftest(out)
    if "--smoke" in argv:
        idx = argv.index("--smoke")
        out = argv[idx + 1] if len(argv) > idx + 1 else "smoke"
        return run_smoke(out)

    _setup_logging()

    # 1) 清理残留进程（仅 exe 态生效）
    #    ⚠️ 必须走静默调用：tasklist / taskkill 是控制台程序，在无控制台的GUI 程序里
    #    会被 Windows 自动分配一个新控制台 ⇒ 双击 exe 先闪一个黑 cmd 窗口。
    from app.singleton import hard_exit, kill_previous_instances
    kill_previous_instances(lambda m: print(f"[启动] {m}"))

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    from app import icons, version
    from app.db import Database
    from app.main_window import MainWindow
    from app.palette import apply_palette

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    # 必须在创建任何窗口之前：固定 Fusion 样式 + 浅色调色板 + 全局样式表，
    # 屏蔽系统深色模式与紫红强调色对下拉弹层、日历的污染。
    apply_palette(app)
    # 主窗口最小化是 hide() 进托盘，「最后一个窗口」随之不可见 ——
    # Qt 默认会在这时直接 qApp.quit()，表现是「最小化一下软件就自己没了」。
    # 真退出由托盘菜单的「退出」触发 closeEvent 里的 _quitting 分支。
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName(version.APP_NAME)
    app.setApplicationVersion(version.FULL_VERSION)
    app.setOrganizationName(version.AUTHOR)
    # 不要设 setApplicationDisplayName：Qt 会自动给每个窗口标题追加
    # " - <显示名>"，导致标题栏出现「证书管理库 v1.1.1 (…) - 证书管理库」的重复。
    app.setWindowIcon(icons.app_icon())
    font = QFont("Microsoft YaHei UI", 10)
    app.setFont(font)

    # 2) 立刻放出启动动画，盖住建库 + 主窗口构造那段空窗期
    #    （实测主窗口构造 1.37s，占总耗时 75%；冻���态还多一段解包时间）
    from app.splash import Splash
    splash = Splash()
    splash.show()
    splash.begin()
    splash.advance()
    app.processEvents()

    try:
        database = Database()
    except Exception as exc:  # noqa: BLE001
        splash.shutdown()          # 失败也要收掉动画，否则用户被空窗困住
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动失败",
                             f"数据库初始化失败：\n{exc}\n\n{traceback.format_exc()}")
        return 2
    splash.advance()
    app.processEvents()

    # 开机自启自愈：设置项写着开、但注册表里没有（手工删过/ 换了机器/ 换了 exe 路径）
    # 就补上；反过来设置项关着、注册表里还留着就删掉。失败只记日志不打断启动 ——
    # 自启是便利功能，不该因为它进不去软件。
    try:
        from app import autostart
        _err = autostart.sync(database.get_setting("autostart", "0") == "1")
        if _err:
            print(f"[启动] 开机自启同步未完成：{_err}")
    except Exception as exc:  # noqa: BLE001
        print(f"[启动] 开机自启同步异常（忽略）：{exc}")
    splash.advance()
    app.processEvents()

    try:
        win = MainWindow(database)
    except Exception as exc:  # noqa: BLE001
        splash.shutdown()          # 同上：主窗口起不来时先把动画收掉
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.critical(None, "启动失败",
                             f"主窗口初始化失败：\n{exc}\n\n{traceback.format_exc()}")
        return 3
    win.show()
    splash.finish()                # 走完最短展示时间后淡出关闭

    code = app.exec()
    try:
        database.close()
    except Exception:  # noqa: BLE001
        pass
    hard_exit(code)
    return code


if __name__ == "__main__":
    sys.exit(main())
