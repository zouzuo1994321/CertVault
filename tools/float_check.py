# -*- coding: utf-8 -*-
"""悬浮窗回归探针：靠边吸附 / 贴边收起 / 内容块开关 / 位置记忆 / 尺寸稳定 / 主窗口联动。

为什么要有独立的探针：悬浮窗的核心体验全在「几何」上 —— 吸得准不准、收起后露出
多少、改内容后高度对不对。这些都不体现在「能不能打开」上，肉眼也看不出 1px 的偏差。
而且它踩过一个非常安静的坑（见 ``floatwin._show_deep`` 的注释：新建控件是 queued
show，布局会把整块算成 0 高度并缓存下来），这类回归只有断言守得住。

⚠️ 探针自己也会骗人（本项目已经栽过一次）：
  · 顶层窗口一旦 hide，所有子控件的 ``isVisible()`` 都会变 False ——
    「隐藏态下断言某块可见」必然失败，而且会把后面的用例一起带偏。
  · ``MainWindow.closeEvent`` 里会 ``db.close()``（真实行为）。所以联动用例
    必须用**独立的数据库实例**，否则会把共享库关掉、后续一律 ProgrammingError。

用法：
    <venv>/Scripts/python.exe tools/float_check.py
退出码 0 表示全部通过。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

FAILS: list = []


def check(name: str, fn) -> None:
    try:
        detail = fn()
        print(f"[float] {name:32s} OK   {detail}")
    except Exception as exc:  # noqa: BLE001
        FAILS.append((name, repr(exc)))
        print(f"[float] {name:32s} FAIL {exc!r}")


def show_offscreen(w):
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.show()
    return w


def pump(app, n: int = 4) -> None:
    for _ in range(n):
        app.processEvents()


def main() -> int:
    from app import version
    from app.db import Database
    from app.floatwin import FLOAT_W, PEEK, SNAP_PX, BLOCKS, FloatWindow
    from app.palette import apply_palette
    from app.sampledata import load_samples

    app = QApplication(sys.argv)
    apply_palette(app)

    tmp = Path(tempfile.mkdtemp(prefix="certvault_float_"))
    db = Database(tmp / "f.db")
    load_samples(db)
    db.set_setting("popup_on_start", "0")
    db.set_setting("float_on", "0")
    print(f"[float] 版本 {version.FULL_VERSION} · 示例数据已就绪")

    fw = show_offscreen(FloatWindow(db))
    pump(app, 6)

    g = fw._available()
    w, h = fw.width(), fw.height()

    # ---------------------------------------------------------- 1. 靠边吸附
    def _snap() -> str:
        cases = [
            ("左", (g.left() + 5, 200), (g.left(), 200)),
            ("右", (g.right() + 1 - w - 5, 200), (g.right() + 1 - w, 200)),
            ("上", (400, g.top() + 5), (400, g.top())),
            ("下", (400, g.bottom() + 1 - h - 5), (400, g.bottom() + 1 - h)),
        ]
        for name, src, want in cases:
            got = fw._snapped(*src)
            assert got == want, f"{name}边 期望{want} 实得{got}"
        assert fw._snapped(400, 300) == (400, 300), "屏幕中间不该被吸走"
        assert SNAP_PX >= 20, "吸附触发距离太小，手感会像没吸附"
        x, y = fw._snapped(g.left() - 800, g.top() - 800)
        assert (x, y) == (g.left(), g.top()), f"越界未夹回 {(x, y)}"
        return f"四边吸附 + 越界夹取 + 中间不动（触发距离 {SNAP_PX}px）"

    check("靠边吸附", _snap)

    # ------------------------------------------------------- 2. 停靠边判定
    def _dock() -> str:
        assert fw._dock_side(g.left(), 200) == "left"
        assert fw._dock_side(g.right() + 1 - w, 200) == "right"
        assert fw._dock_side(400, 300) is None
        assert fw._edge_of(g.left() + 3, 200) == "left"
        assert fw._edge_of(g.right() + 1 - w - 3, 200) == "right"
        assert fw._edge_of(400, 300) is None
        return "left / right / 不靠边 三种判定正确"

    check("停靠边判定", _dock)

    # --------------------------------------------------------- 3. 贴边收起
    def _autohide() -> str:
        fw.autohide = True
        fw._docked = "right"
        fw._rest = QPoint(g.right() + 1 - w, 200)
        fw.move(fw._rest)
        fw._slide_out()
        assert fw._slid is True, "未进入收起态"
        want = QPoint(g.right() + 1 - PEEK, 200)
        got = fw._anim.endValue()
        assert got == want, f"右收起目标 期望{want} 实得{got}"
        assert 0 < PEEK <= 12, "露出的窄边宽度不合理（太宽不像收起，太窄抓不住）"
        fw._slide_in(instant=True)
        assert fw._slid is False and fw.pos() == fw._rest, "展开未回到原位"
        fw._docked = "left"
        fw._rest = QPoint(g.left(), 200)
        fw.move(fw._rest)
        fw._slide_out()
        want = QPoint(g.left() - w + PEEK, 200)
        got = fw._anim.endValue()
        assert got == want, f"左收起目标 期望{want} 实得{got}"
        fw._slide_in(instant=True)
        fw.autohide = False
        return f"左右各收起至露 {PEEK}px，展开归位"

    check("贴边收起 / 展开", _autohide)

    # ------------------------------------------------- 4. 拖动 → 吸附 → 落位
    def _drag() -> str:
        start = QPoint(g.left() + 200, g.top() + 200)
        fw.move(start)
        fw.begin_drag(start + QPoint(10, 10))
        fw.drag_to(QPoint(g.right() + 1 - w - 6, g.top() + 240))
        assert fw._snap_preview == "right", f"拖动中未预告吸附边：{fw._snap_preview}"
        fw.end_drag()
        assert fw.pos().x() == g.right() + 1 - w, f"松手未贴边：{fw.pos().x()}"
        assert fw._docked == "right", "未记录停靠边"
        assert db.get_setting("float_x") == str(fw.pos().x()), "位置未落库 x"
        assert db.get_setting("float_y") == str(fw.pos().y()), "位置未落库 y"
        return f"拖动预告→松手贴边→落库 {fw.pos().x()},{fw.pos().y()}"

    check("拖动 / 吸附 / 位置落库", _drag)

    # ------------------------------------------------------- 5. 位置记忆
    def _remember() -> str:
        other = show_offscreen(FloatWindow(db))
        pump(app, 4)
        target = QPoint(g.left() + 60, g.top() + 120)
        other.move(target)
        # 注意 drag_to() 收的是**光标**全局坐标，窗口位置 = 光标 − 按下时的偏移
        grip = target + QPoint(5, 5)
        other.begin_drag(grip)
        other.drag_to(grip)            # 光标没动 → 窗口原地；且不靠边，不该被吸附
        other.end_drag()
        assert other.pos() == target, f"非边缘位置被改动：{other.pos()}"
        other.hide_window()
        assert db.get_setting("float_on") == "0", "隐藏后总开关未置 0"
        third = show_offscreen(FloatWindow(db))
        pump(app, 4)
        assert third.pos() == target, f"新面板未回到上次位置 期望{target} 实得{third.pos()}"
        # 位置越界（比如拔掉副屏）→ 回落到屏幕内
        db.set_setting("float_x", "-99999")
        db.set_setting("float_y", "-99999")
        fourth = show_offscreen(FloatWindow(db))
        assert fourth._visible_enough(fourth.pos()), "越界位置未回落到可见区"
        db.set_setting("float_x", str(target.x()))
        db.set_setting("float_y", str(target.y()))
        for o in (other, third, fourth):
            o.close()
        return f"重启回到 {target.x()},{target.y()}；越界自动回落"

    check("位置记忆 / 越界回落", _remember)

    # ---------------------------------------------------- 6. 内容块开关
    def _blocks() -> str:
        fw.show_window()               # 前面可能被隐藏过，先确保可见
        pump(app, 4)
        keys = [k for k, _ in BLOCKS]
        for k in keys:
            fw.set_block(k, True)
        assert fw.blocks == keys, f"全开后顺序应等于登记表顺序：{fw.blocks}"
        assert db.get_setting("float_blocks") == ",".join(keys), "勾选未落库"
        tall = fw.height()
        for k in keys:
            assert fw._block_widgets[k].isVisible(), f"{k} 未显示"
        fw.set_block("clock", False)
        fw.set_block("stats", False)
        short = fw.height()
        assert short < tall, f"关掉两块后面板没变矮：{tall} → {short}"
        assert not fw._block_widgets["clock"].isVisible(), "clock 未隐藏"
        for k in fw.blocks:
            fw.set_block(k, False)
        assert fw.blocks == [], "未清空"
        assert fw._none.isVisible(), "全关时没有占位提示"
        assert fw.height() > 150, f"全关时面板高度异常：{fw.height()}"
        for k in ("clock", "stats", "expiring", "exams"):
            fw.set_block(k, True)
        assert fw.blocks == ["clock", "stats", "expiring", "exams"], fw.blocks
        return f"全开 {tall}px → 关两块 {short}px → 全关留占位 → 还原"

    check("内容块开关 / 落库", _blocks)

    # ------------------------------------------- 7. 尺寸稳定（回归守卫）
    def _stable() -> str:
        pump(app, 4)
        fw.refresh()
        h1 = fw.height()
        fw.refresh()
        h2 = fw.height()
        assert h1 == h2, f"连续刷新高度漂移：{h1} → {h2}"
        for k in fw.blocks:
            b = fw._block_widgets[k]
            body = b.body.sizeHint().height()
            assert body > 0, f"{k} 的内容层高度为 0（布局把内容当空项了）"
            assert b.sizeHint().height() >= 60, f"{k} 整块高度异常 {b.sizeHint().height()}"
        fw.set_block("tip", True)
        fw.set_block("tip", False)
        pump(app, 4)
        assert fw.height() == h1, f"开关往返后高度不一致：{h1} → {fw.height()}"
        return f"连刷两次 {h1}px 不变；各块内容均计入高度"

    check("尺寸稳定（回归守卫）", _stable)

    # --------------------------------------------------------- 8. 收起态
    def _roll() -> str:
        fw.show_window()
        pump(app, 4)
        full = fw.height()
        fw.toggle_roll()
        pump(app, 4)
        rolled = fw.height()
        assert fw._rolled and not fw._scroll.isVisible(), "收起后内容区仍可见"
        assert rolled < full, f"收起后没变矮：{full} → {rolled}"
        assert fw._btn_main.isVisible(), "收起后底部动作按钮不该消失"
        fw.toggle_roll()
        pump(app, 4)
        assert fw.height() == full, f"展开未恢复：{fw.height()} vs {full}"
        return f"展开 {full}px ↔ 收起 {rolled}px（底部按钮保留）"

    check("收起 / 展开", _roll)

    # --------------------------------------------------------- 9. 结构
    def _structure() -> str:
        assert fw.width() == FLOAT_W, "面板宽度不是固定值"
        assert fw.lbl_meta.text().startswith(version.FULL_VERSION), fw.lbl_meta.text()
        assert fw.lbl_chip.text(), "头部计数胶囊为空"
        for name, b in (("置顶", fw.btn_top), ("收起", fw.btn_roll),
                        ("关闭", fw.btn_close), ("主窗口", fw._btn_main),
                        ("到期提醒", fw._btn_bell), ("内容…", fw._btn_cfg)):
            assert b is not None, f"缺少控件：{name}"
        assert fw.btn_top.toolTip() and fw.btn_close.toolTip(), "图标按钮缺少提示"
        assert not fw.grab().isNull(), "面板无法渲染"
        return f"宽 {FLOAT_W}px · 头部素材齐 · 三个动作按钮齐 · 可渲染"

    check("结构完整性", _structure)

    # ------------------------------------------------ 10. 主窗口联动
    def _mainlink() -> str:
        from app.main_window import MainWindow
        # ★ 必须用独立库：MainWindow.closeEvent 会 db.close()，会把共享库关掉
        db2 = Database(tmp / "main.db")
        load_samples(db2)
        db2.set_setting("popup_on_start", "0")
        db2.set_setting("float_on", "0")
        win = show_offscreen(MainWindow(db2))
        win.resize(1440, 900)
        pump(app, 4)
        try:
            assert win.btn_float is not None, "顶栏缺少悬浮窗开关"
            assert win.btn_float in win._caption_exempt, "开关未加入命中测试白名单"
            assert win.floatwin is None, "未开启时不该预先创建悬浮窗"
            win.toggle_float()
            pump(app, 4)
            assert db2.get_setting("float_on") == "1", "开启后未落库"
            assert win.floatwin is not None and win.floatwin.isVisible(), "悬浮窗未显示"
            win.toggle_float()
            pump(app, 4)
            assert db2.get_setting("float_on") == "0", "隐藏后未落库"
            assert not win.floatwin.isVisible(), "悬浮窗未隐藏"
            # 设置面板改了内容 → 主窗口回读
            db2.set_setting("float_on", "1")
            db2.set_setting("float_blocks", "exams,tip")
            win._apply_float_setting()
            pump(app, 4)
            assert win.floatwin.blocks == ["exams", "tip"], win.floatwin.blocks
            # 悬浮窗上的「主窗口」按钮
            win.floatwin.open_main.emit()
            pump(app, 4)
            win.toggle_float()
            return "顶栏开关 ↔ 落库 ↔ 设置面板改动回读 ↔ 主窗口按钮 全部同步"
        finally:
            win.close()
            db2.close()

    check("主窗口联动", _mainlink)

    def _independent() -> str:
        """独立驻留：主窗口最小化 / 隐藏时，悬浮窗必须还在桌面上。

        ★ 这条不能只看 `QWidget.isVisible()` —— 悬浮窗一旦被挂成主窗口的
          transient child，Qt 层面 `isVisible()` 在它被系统藏掉之后**仍然返回
          True**（实测过），只有 `IsWindowVisible(hwnd)` 才会说实话。
          所以这里直接查原生层，顺带断言 `GW_OWNER == 0`（不是 owned window）——
          owner 非 0 就意味着它跟着 owner 的生死走。
        """
        import ctypes
        from ctypes import wintypes
        from app.main_window import MainWindow
        u32 = ctypes.windll.user32
        u32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
        u32.GetWindow.restype = wintypes.HWND

        # 独立库（同上：closeEvent 会 db.close()）
        db2 = Database(tmp / "indep.db")
        load_samples(db2)
        db2.set_setting("popup_on_start", "0")
        db2.set_setting("float_on", "0")
        win = show_offscreen(MainWindow(db2))
        pump(app, 4)
        fw2 = win._ensure_float()
        fw2.setGeometry(200, 200, FLOAT_W, 400)
        fw2.show()
        pump(app, 4)
        # ⚠️ `GetWindow` 的 restype 设成 HWND(=c_void_p) 时，**没有 owner 会返回
        #    None 而不是 0** —— 写 `== 0` 永远为False，会把「本来就独立」误判成
        #    「有 owner」。用 `not owner` 判空。
        owner = u32.GetWindow(int(fw2.winId()), 4)
        assert not owner, f"悬浮窗不该有 owner，却拿到 0x{int(owner or 0):08X}"
        fw2.show_window()
        pump(app, 4)
        win.showMinimized()
        pump(app, 8)
        still = bool(u32.IsWindowVisible(int(fw2.winId())))
        assert still, "主窗口最小化后悬浮窗被系统藏掉了（owner 关联没断干净）"
        return "owner=0 且主窗口最小化后仍驻留桌面"
    check("独立驻留（不随主窗口最小化）", _independent)

    fw.hide_window()
    db.close()
    print("[float] 失败项：", FAILS if FAILS else "无")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
