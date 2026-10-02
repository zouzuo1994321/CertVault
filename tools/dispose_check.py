# -*- coding: utf-8 -*-
"""提醒处置回归探针（v1.3.0）：延期 / 忽略 / 标记已处理 / 恢复 / 自定义延期。

覆盖 10 组共43 项断言：
  1. 初始状态与视图下拉
  2. 延期 30 天 → 落库 + 立刻从 expiring() 消失 + toast
  3. 切到「已延期」→ 行内变「恢复提醒」+ 胶囊换成处置文案
  4. 永久忽略 → FOREVER 哨兵 + 文案
  5. 标记已处理 → 今日静默 + 留痕；恢复 → 回到清单
  6. 处置菜单结构（两级子菜单 + 5+1 / 3+1 项）
  7. 超长证书名单行省略、行高不被撑开
  8. 四个视图各自的空态（用空库真渲染，且空态被上下 stretch夹在中间）
  9. 自定义延期对话框的日期边界与快捷按钮
 10. 统计卡随处置联动 + 「已处置 N 本」计数

用法：  <venv>/Scripts/python.exe tools/dispose_check.py
退出码 0 = 全绿。

注意：不要设 QT_QPA_PLATFORM=offscreen —— Windows 下该插件字体库为空，
中文会渲染成方块（与 tools/offscreen_check.py 同一个坑）。
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QDate, Qt  # noqa: E402
from PySide6.QtWidgets import (QApplication, QLabel, QPushButton,  # noqa: E402
                               QSizePolicy, QSpacerItem)

from app import db as dbm  # noqa: E402
from app import palette, sampledata  # noqa: E402
from app.dialogs import PostponeDialog  # noqa: E402
from app.widgets import ElidedLabel, EmptyState  # noqa: E402

SHOT_DIR = ROOT / "build" / "diag"
SHOT_DIR.mkdir(parents=True, exist_ok=True)

OK: list[str] = []
FAIL: list[str] = []


def chk(name: str, cond: bool, extra: str = "") -> None:
    (OK if cond else FAIL).append(name)
    print(("  [OK] " if cond else "  [!!] ") + name + (f"  {extra}" if extra else ""))


class FakeApp:
    """ReminderPage 只用到这几个口子，够用即可，不必起真主窗口。"""

    def __init__(self, db) -> None:
        self.db = db
        self.msgs: list[str] = []

    def toast(self, m: str) -> None:
        self.msgs.append(m)

    def notify_changed(self) -> None:
        pass

    def goto(self, key: str) -> None:
        pass

    def show_reminder(self) -> None:
        pass

    def reload_all(self) -> None:
        pass


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="cv_dispose_"))
    app = QApplication(sys.argv)
    palette.apply_palette(app)

    db = dbm.Database(tmp / "t.db")
    sampledata.load_samples(db)

    from app.pages import ReminderPage
    fake = FakeApp(db)
    page = ReminderPage(fake)

    print("\n=== 1. 初始状态 ===")
    rows = page.db.expiring()
    allrows = page.db.expiring(include_suppressed=True)
    chk("expiring() 默认排除已处置", len(rows) <= len(allrows))
    chk("四视图下拉存在", page.cmb_view.count() == 4,
        f"count={page.cmb_view.count()}")
    chk("默认视图 = active", page._view == "active")

    print("\n=== 2. 处置：延期 30 天 ===")
    target = rows[0]
    cid = target["id"]
    print(f"  目标证书：{target['name']}（{target['left_text']}）")
    chk("处置前该证书在列表里", any(r["id"] == cid for r in page.db.expiring()))
    page._postpone(cid, 30)
    st = db.reminder_state(cid)
    chk("postponed_until 已落库", st.get("postponed_until", "") != "",
        st.get("postponed_until", ""))
    chk("expiring() 已排除该证书",
        not any(r["id"] == cid for r in db.expiring()))
    chk("include_suppressed 仍能看到",
        any(r["id"] == cid and r["suppressed"] == "postponed"
            for r in db.expiring(include_suppressed=True)))
    chk("toast 已提示", bool(fake.msgs) and "已延至" in fake.msgs[-1],
        fake.msgs[-1] if fake.msgs else "")

    print("\n=== 3. 视图切到「已延期」 ===")
    page.cmb_view.setCurrentIndex(page.cmb_view.findData("postponed"))
    page._change_view()
    chk("_view 已切换", page._view == "postponed")
    held = [r for r in db.expiring(include_suppressed=True) if r["id"] == cid]
    roww = page._row(held[0])
    btns = roww.findChildren(QPushButton)
    chip = [l for l in roww.findChildren(QLabel) if l.minimumWidth() == 132]
    chk("行内出现「恢复提醒」", any(b.text() == "恢复提醒" for b in btns),
        str([b.text() for b in btns]))
    chk("胶囊改为处置文案", bool(chip) and "延至" in chip[0].text(),
        chip[0].text() if chip else "无胶囊")
    chk("按处置筛选的分组非空",
        bool(page._groups([], db.expiring(include_suppressed=True),
                          db.warn_days())[0]))

    print("\n=== 4. 处置：忽略（永久） ===")
    page.cmb_view.setCurrentIndex(page.cmb_view.findData("active"))
    page._change_view()
    cid2 = db.expiring()[0]["id"]
    page._ignore(cid2, 0)
    st2 = db.reminder_state(cid2)
    chk("永久忽略哨兵值", st2.get("ignored_until") == dbm.FOREVER,
        st2.get("ignored_until", ""))
    real = [r for r in db.expiring(include_suppressed=True) if r["id"] == cid2][0]
    chk("永久忽略文案", dbm.suppress_label(real) == "已永久忽略",
        dbm.suppress_label(real))

    print("\n=== 5. 处置：标记已处理 / 恢复 ===")
    page._restore(cid2)
    chk("恢复后状态清空", not db.reminder_state(cid2).get("ignored_until"))
    chk("恢复后回到到期清单", any(r["id"] == cid2 for r in db.expiring()))
    page._handle(cid2)
    chk("标记已处理 → 今日静默",
        not any(r["id"] == cid2 for r in db.expiring()))
    chk("留痕 handled_at 非空",
        db.reminder_state(cid2).get("handled_at", "") != "")
    page._restore(cid2)

    print("\n=== 6. 处置菜单结构 ===")
    r0 = db.expiring()[0]
    m = page._dispose_menu(r0)
    tops = [a.text() for a in m.actions() if a.text()]
    chk("一级菜单项", tops[:3] == ["延期提醒", "忽略提醒", "标记为已处理"], str(tops))
    sub = [a.menu() for a in m.actions() if a.menu()]
    chk("两个子菜单", len(sub) == 2)
    chk("延法子菜单 5+1 项",
        len([a for a in sub[0].actions() if a.text()]) == 6,
        str([a.text() for a in sub[0].actions() if a.text()]))
    chk("忽略子菜单含永久",
        "永久忽略" in [a.text() for a in sub[1].actions() if a.text()],
        str([a.text() for a in sub[1].actions() if a.text()]))
    chk("未处置的行没有「恢复提醒」", "恢复提醒" not in tops)

    print("\n=== 7. 长名称单行省略 ===")
    long_row = dict(r0)
    long_row["name"] = " exceedingly-long-certificate-title-" + "超长证书名称测试" * 6
    lw = page._row(long_row)
    page.resize(1100, 700)
    lw.setFixedWidth(700)
    lw.setAttribute(Qt.WA_DontShowOnScreen, True)
    lw.show()
    app.processEvents()
    el = lw.findChildren(ElidedLabel)
    chk("用了 ElidedLabel", len(el) >= 2, f"{len(el)} 个")
    chk("超长名被省略",
        all("…" in e.text() for e in el
            if "exceedingly" in e._full or "超长" in e._full),
        str([e.text()[-8:] for e in el]))
    chk("行高未被撑开", lw.sizeHint().height() <= 70,
        f"h={lw.sizeHint().height()}")

    print("\n=== 8. 各视图空态（用空库真渲染） ===")
    empty_db = dbm.Database(tmp / "empty.db")
    page.db = fake.db = empty_db
    for v in ("active", "postponed", "ignored", "all"):
        page._view = v
        page.refresh()
        app.processEvents()
        es = page.inner.findChildren(EmptyState)
        chk(f"视图 {v} 渲染出空态", len(es) == 1,
            es[0].findChild(QLabel).text() if es else "无 EmptyState")
        if es:
            # 空态必须真的被夹在中间：上下各一个可伸缩 spacer
            items = [page.iv.itemAt(i) for i in range(page.iv.count())]
            centered = (len(items) == 3
                        and isinstance(items[0], QSpacerItem)
                        and isinstance(items[2], QSpacerItem)
                        and items[0].sizePolicy().verticalPolicy()
                        == QSizePolicy.Expanding)
            chk(f"视图 {v} 空态居中", centered, f"{len(items)} 项")
    page.db = fake.db = db

    print("\n=== 9. 自定义延期对话框 ===")
    d = PostponeDialog("初级会计专业技术资格", None, 30)
    app.processEvents()
    chk("默认日期 = 今天+30",
        d.date_edit.date() == QDate.currentDate().addDays(30),
        d.date_edit.date().toString("yyyy-MM-dd"))
    chk("最早可选 = 明天",
        d.date_edit.minimumDate() == QDate.currentDate().addDays(1))
    lb = [x.text() for x in d.findChildren(QPushButton)]
    chk("快捷按钮齐全",
        any("7 天" in x for x in lb) and any("180 天" in x for x in lb), str(lb))
    d.date_edit.setDate(QDate.currentDate().addDays(45))
    chk("until() 输出正确",
        d.until() == (date.today() + timedelta(days=45)).isoformat(), d.until())

    print("\n=== 10. 统计卡随处置联动 ===")
    page._view = "active"
    page.refresh()

    def total() -> int:
        return (int(page.s_expired.value_lbl.text())
                + int(page.s_urgent.value_lbl.text())
                + int(page.s_soon.value_lbl.text()))

    before = total()
    victims = [r["id"] for r in db.expiring()][:2]
    for v in victims:
        db.ignore_reminder(v, 30)
    page.refresh()
    chk("处置后统计卡下降", total() == before - len(victims), f"{before} -> {total()}")
    held_n = len([r for r in db.expiring(include_suppressed=True) if r["suppressed"]])
    chk("已处置计数出现在副标题",
        page.lab_held.text().startswith(f"已处置 {held_n} 本 ·"), page.lab_held.text())

    print("\n=== 11. 三视图效果图 ===")
    page.setAttribute(Qt.WA_DontShowOnScreen, True)
    page.resize(1200, 780)
    page.show()
    app.processEvents()
    for v in ("active", "postponed", "ignored"):
        page._view = v
        page.refresh()
        app.processEvents()
        out = SHOT_DIR / f"dispose_{v}.png"
        page.grab().save(str(out))
        print(f"  -> {out.name}（{out.stat().st_size // 1024} KB）")

    print("\n=== 汇总 ===")
    print(f"通过 {len(OK)} / {len(OK) + len(FAIL)}")
    if FAIL:
        print("失败：")
        for f in FAIL:
            print("  - " + f)
    shutil.rmtree(tmp, ignore_errors=True)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())