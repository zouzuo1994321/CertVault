# -*- coding: utf-8 -*-
"""各功能页面：首页概览 / 证书管理 / 到期提醒 / 考试计划 / 学习资料 / 关于与声明。"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox,
                               QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMenu,
                               QPushButton, QScrollArea, QSizePolicy,
                               QSplitter, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from . import db as dbm
from . import icons, paths, pdfexport, theme, version
from .dialogs import (CertDialog, CategoryDialog, ExamDialog, MaterialDialog,
                      PdfViewer, PostponeDialog, ReminderDialog,
                      SettingsDialog, confirm, error, info, open_path, open_url,
                      reveal, warn)
from .widgets import (GAZE_FPS, GAZE_INSET_X, GAZE_INSET_Y, GAZE_TAU, Badge,
                      Card, ComboBox, ElidedLabel, EmptyState, GazeLogo,
                      GazeScene, HBarChart, IconButton, InfoRow, SearchBox,
                      SectionTitle, StatCard, bold, hline, mono_label,
                      realize, status_badge, tag)

# 首页总览的模块要「整块」跟着视线动，就必须给每块留出走位余量（见 widgets）。
# 于是承载它们的布局要把等量的边距 / 间距让出来 —— 让完之后静止位形与
# v1.1.8 逐像素一致，而模块本身获得了 ±(6, 8)px 的平移空间。
_ROOM = (GAZE_INSET_X, GAZE_INSET_Y)

STATUS_FILTERS = [("", "全部"), ("valid", "有效"), ("soon", "即将到期"),
                  ("urgent", "紧急"), ("expired", "已过期"),
                  ("permanent", "长期有效")]


class Page(QWidget):
    """页面基类：统一提供 refresh() 与标题信息。"""

    PAGE_TITLE = ""
    PAGE_SUB = ""

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.app = app
        self.db = app.db

    def refresh(self) -> None:  # pragma: no cover - 子类覆写
        pass

    # --- 便捷构造
    def _table(self, headers: List[str]) -> QTableWidget:
        t = QTableWidget(0, len(headers))
        t.setHorizontalHeaderLabels(headers)
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectRows)
        t.setSelectionMode(QAbstractItemView.SingleSelection)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setWordWrap(False)
        t.verticalHeader().setDefaultSectionSize(40)
        t.horizontalHeader().setHighlightSections(False)
        return t


# =============================================================== 首页概览


class DashboardPage(Page):
    PAGE_TITLE = "证书总览"
    PAGE_SUB = "证书资产、到期分布与近期安排一览"

    goto_page = Signal(str)

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        # ★ 把「走位余量」从布局里让出来：每个模块的宿主比可视卡面大
        #   2×(6, 8)，所以左右边距 24−6、上边距 20−8、下边距 24−8、
        #   模块间距 16−2×8。让完之后模块的**可视**边界与 v1.1.8 逐像素一致，
        #   而每个模块自己获得了 ±6px 横向、±8px 纵向的平移空间。
        v.setContentsMargins(24 - GAZE_INSET_X, 20 - GAZE_INSET_Y,
                             24 - GAZE_INSET_X, 24 - GAZE_INSET_Y)
        v.setSpacing(16 - 2 * GAZE_INSET_Y)

        # --- 统计卡
        cards = QHBoxLayout()
        cards.setSpacing(14 - 2 * GAZE_INSET_X)     # 让出余量后视觉间距仍是 14
        self.c_total = StatCard("证书总数", "0", theme.PRIMARY, "cert", room=_ROOM)
        self.c_valid = StatCard("有效证书", "0", theme.SUCCESS, "check", room=_ROOM)
        self.c_soon = StatCard("即将到期（≤阈值）", "0", theme.WARN, "clock",
                               room=_ROOM)
        self.c_expired = StatCard("已过期", "0", theme.DANGER, "warn", room=_ROOM)
        for c in (self.c_total, self.c_valid, self.c_soon, self.c_expired):
            c.clicked.connect(lambda _=None, s=self._sender_name(): None)
            cards.addWidget(c, 1)
        self.c_total.clicked.connect(lambda: self.goto_page.emit("certs"))
        self.c_valid.clicked.connect(lambda: self.goto_page.emit("certs"))
        self.c_soon.clicked.connect(lambda: self.goto_page.emit("reminders"))
        self.c_expired.clicked.connect(lambda: self.goto_page.emit("reminders"))
        v.addLayout(cards)

        # --- 中部：分类分布 + 最近到期
        mid = QHBoxLayout()
        mid.setSpacing(14 - 2 * GAZE_INSET_X)

        card_chart = Card("证书分类分布", "按分类统计证书数量", glow_q=2.0, room=_ROOM)
        self.chart = HBarChart()
        card_chart.add(self.chart)
        mid.addWidget(card_chart, 5)
        card_exp = Card("最近到期", glow_q=2.0, room=_ROOM)
        btn_all = QPushButton("全部")
        btn_all.setObjectName("Ghost")
        realize(btn_all, "chevron-right", theme.PRIMARY, 14)
        btn_all.clicked.connect(lambda: self.goto_page.emit("reminders"))
        card_exp.add_head_widget(btn_all)
        self.exp_box = QVBoxLayout()
        self.exp_box.setSpacing(8)
        card_exp.add(self.exp_box)
        mid.addWidget(card_exp, 4)
        v.addLayout(mid)

        # --- 近期考试
        # 通栏大卡片关掉卡面柔光：面积太大（≈28 万像素），一层 alpha 30 的极淡径向
        # 渐变铺上去基本看不出来，却要每次整卡重绘 —— 性价比太低。它们的「活」交给
        # 内容视差 + 悬停描边，视觉上并不dead。
        card_exam = Card("近期考试计划", glow=False, room=_ROOM)
        btn_exam = QPushButton("去规划")
        btn_exam.setObjectName("Ghost")
        realize(btn_exam, "chevron-right", theme.PRIMARY, 14)
        btn_exam.clicked.connect(lambda: self.goto_page.emit("exams"))
        card_exam.add_head_widget(btn_exam)
        self.exam_box = QVBoxLayout()
        self.exam_box.setSpacing(8)
        card_exam.add(self.exam_box)
        v.addWidget(card_exam)

        # --- 资料概览
        card_mat = Card("学习资料库", glow=False, room=_ROOM)
        btn_mat = QPushButton("去整理")
        btn_mat.setObjectName("Ghost")
        realize(btn_mat, "chevron-right", theme.PRIMARY, 14)
        btn_mat.clicked.connect(lambda: self.goto_page.emit("materials"))
        card_mat.add_head_widget(btn_mat)
        self.mat_box = QHBoxLayout()
        self.mat_box.setSpacing(12)
        card_mat.add(self.mat_box)
        v.addWidget(card_mat)

        v.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll)

        # --- 「视角跟随」：不只有徽标会看人，首页的每个模块都跟着视线轻微视差
        #
        # 一页只起一个编排器（GazeScene），所有模块共享同一条视线 —— 各自起定时器
        # 的话缓动相位会错开，整页看起来是散的。位移分量按「远近」分三档：
        #   · 统计卡的图标徽标    移得最多（近处）—— 正文 6px + 徽标额外 6px
        #   · 分类分布图的条形    在卡片位移之外自己再平移一份（自绘，可亚像素）
        #   · 各卡片的正文/标题   移得最少，只当背景板
        #   · 卡面柔光 + 悬停描边 paintEvent 里随视线游走，不碰任何几何
        #
        # ref（视线饱和距离）= 500：鼠标离页面中心 500px 时位移打满。
        # 这个值直接决定「1px 台阶的疏密」—— 台阶间隔 = ref / 幅度。
        # 660 时是每 110 鼠标像素跳 1px（慢扫时能数出来），降到 500 后
        # 变成每 83px 跳 1px，同样的手腕行程下台阶多了三分之一，
        # 观感从「一格一格」变成连续推进。QWidget 的几何只能整数像素，
        # 这是在不引入 pixmap 亚像素层（会带来重采样模糊与每帧整卡重绘）
        # 的前提下，最划算的一档。
        self._scene = GazeScene(self, ref=500.0, tau=GAZE_TAU, fps=GAZE_FPS)
        self._gaze_targets = [self.c_total, self.c_valid, self.c_soon,
                              self.c_expired, card_chart, self.chart,
                              card_exp, card_exam, card_mat]
        for t in self._gaze_targets:
            t.set_gaze_enabled(True)
            # 图表不参与「悬停放大」：它的位移是亚像素的，放大后会和卡片正文对不齐
            self._scene.add(t, hover=(t is not self.chart))
        self._scene.tick.connect(self._on_anim_tick)
        self._shown_once = False

    def _on_anim_tick(self, dt: float) -> None:
        """数字滚动 / 图表生长：搭同一个 60fps 定时器的便车，不再各开一个。"""
        for c in (self.c_total, self.c_valid, self.c_soon, self.c_expired):
            c.tick_anim(dt)
        self.chart.tick_anim(dt)

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._scene.start()
        self._scene.play_enter()          # 每次回到首页都重新编排一遍入场
        self._shown_once = True

    def hideEvent(self, e):  # noqa: N802
        super().hideEvent(e)
        self._scene.stop()                # 看不见就别空转 60fps

    def _sender_name(self) -> str:
        return ""

    # ----------------------------------------------------------- 刷新
    def refresh(self) -> None:
        # 首帧不滚数字：那会儿窗口还没露脸，滚了也看不见，白浪费一次动画
        anim = self._shown_once
        st = self.db.certificate_stats()
        self.c_total.set_value(str(st["total"]), animate=anim)
        self.c_valid.set_value(str(st["valid"] + st["permanent"]), animate=anim)
        self.c_soon.set_value(str(st["soon"] + st["urgent"]), animate=anim)
        self.c_expired.set_value(str(st["expired"]), animate=anim)

        stats = self.db.category_stats()
        self.chart.set_data([(s["name"], s["total"], s["color"]) for s in stats],
                            animate=anim)

        _clear(self.exp_box)
        rows = self.db.expiring()[:6]
        if not rows:
            self.exp_box.addWidget(_hint_row("check", theme.SUCCESS,
                                             "暂无临近到期的证书"))
        for r in rows:
            self.exp_box.addWidget(_mini_cert_row(r))

        _clear(self.exam_box)
        exams = self.db.upcoming_exams(4)
        if not exams:
            self.exam_box.addWidget(_hint_row("calendar", theme.MUTED,
                                              "暂无未开始的考试计划"))
        for e in exams:
            self.exam_box.addWidget(_mini_exam_row(e))

        _clear(self.mat_box)
        mstats = self.db.material_stats()
        if not mstats:
            self.mat_box.addWidget(_hint_row("book", theme.MUTED, "还没有整理学习资料"))
        else:
            total = sum(mstats.values())
            self.mat_box.addWidget(_stat_pill("资料总数", str(total), theme.PRIMARY))
            for k, v in sorted(mstats.items(), key=lambda x: -x[1])[:4]:
                self.mat_box.addWidget(_stat_pill(k, str(v), theme.GOLD))
            self.mat_box.addStretch(1)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w:
            w.setParent(None)
            w.deleteLater()


def _hint_row(icon_name: str, color: str, text: str) -> QWidget:
    w = QFrame()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(4, 8, 4, 8)
    lay.setSpacing(8)
    ic = QLabel()
    ic.setPixmap(icons.pixmap(icon_name, color, 18))
    lay.addWidget(ic)
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
    lay.addWidget(lbl, 1)
    return w


def _mini_cert_row(r: Dict[str, Any]) -> QWidget:
    w = QFrame()
    w.setStyleSheet(f"background:#fbfcfe; border:1px solid {theme.BORDER};"
                    f" border-radius:9px;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(8)
    col = QVBoxLayout()
    col.setSpacing(1)
    n = QLabel(r["name"])
    n.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; font-size:13px;")
    col.addWidget(n)
    meta = QLabel(f"{r['category']} · 到期 {r['expiry_date'] or '长期'}")
    meta.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
    col.addWidget(meta)
    lay.addLayout(col, 1)
    b = status_badge(r["status_key"])
    lay.addWidget(b)
    left = QLabel(r["left_text"])
    left.setStyleSheet(f"color:{theme.status_color(r['status_key'])};"
                       f" font-size:12px; font-weight:600;")
    left.setFixedWidth(88)
    left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(left)
    return w


def _mini_exam_row(e: Dict[str, Any]) -> QWidget:
    w = QFrame()
    w.setStyleSheet(f"background:#fbfcfe; border:1px solid {theme.BORDER};"
                    f" border-radius:9px;")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(12, 8, 12, 8)
    lay.setSpacing(8)
    ic = QLabel()
    ic.setPixmap(icons.pixmap("calendar", theme.PRIMARY, 18))
    lay.addWidget(ic)
    col = QVBoxLayout()
    col.setSpacing(1)
    n = QLabel(e["name"])
    n.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; font-size:13px;")
    col.addWidget(n)
    meta = QLabel(f"{e['exam_date']} · {e['location'] or '考点待定'} · {e['state']}")
    meta.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
    col.addWidget(meta)
    lay.addLayout(col, 1)
    d = e.get("days_left")
    tone = theme.SUCCESS if (d or 0) > 30 else (theme.WARN if (d or 0) > 7 else "#e0622c")
    lbl = QLabel(f"还有 {d} 天" if d is not None else "—")
    lbl.setStyleSheet(f"color:{tone}; font-weight:700; font-size:12px;")
    lay.addWidget(lbl)
    return w


def _stat_pill(name: str, value: str, color: str) -> QWidget:
    # 注意：Qt 样式表的十六进制颜色是 #AARRGGBB（透明度在前），
    # 直接拼接 "#RRGGBB" + "14" 会被解析成半透明深红，必须用 rgba()。
    c = QColor(color)
    bg = f"rgba({c.red()},{c.green()},{c.blue()},20)"
    bd = f"rgba({c.red()},{c.green()},{c.blue()},60)"
    w = QFrame()
    w.setStyleSheet(f"background:{bg}; border:1px solid {bd}; border-radius:10px;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(14, 10, 14, 10)
    lay.setSpacing(1)
    v = QLabel(value)
    # 注意：统计数字不要用等宽字体，Consolas 的 0 带斜杠，会看成 Ø
    v.setStyleSheet(f"color:{color}; font-size:22px; font-weight:700;")
    lay.addWidget(v)
    n = QLabel(name)
    n.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:11px;")
    lay.addWidget(n)
    w.setMinimumWidth(110)
    return w


# =============================================================== 证书管理


class CertificatePage(Page):
    PAGE_TITLE = "证书管理"
    PAGE_SUB = "录入、分类、检索与归档全部证书"

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        self.kw = ""
        self.cat = ""
        self.status = ""
        self._rows: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        # --- 工具栏
        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_new = QPushButton("新增证书")
        self.btn_new.setObjectName("Primary")
        realize(self.btn_new, "plus", "#ffffff")
        self.btn_edit = QPushButton("编辑")
        realize(self.btn_edit, "edit", theme.TEXT_SUB)
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("Danger")
        realize(self.btn_del, "trash", theme.DANGER)
        self.btn_pdf = QPushButton("预览 PDF")
        self.btn_pdf.setObjectName("Gold")
        realize(self.btn_pdf, "pdf", "#3a2f07")
        self.btn_sheet = QPushButton("导出信息单")
        realize(self.btn_sheet, "doc", theme.TEXT_SUB)
        self.btn_ledger = QPushButton("导出台账")
        realize(self.btn_ledger, "export", theme.TEXT_SUB)
        self.btn_csv = QPushButton("导出 CSV")
        realize(self.btn_csv, "table", theme.TEXT_SUB)
        self.btn_cat = QPushButton("分类管理")
        realize(self.btn_cat, "folder", theme.TEXT_SUB)

        for b in (self.btn_new, self.btn_edit, self.btn_del, self.btn_pdf):
            bar.addWidget(b)
        bar.addSpacing(10)
        for b in (self.btn_sheet, self.btn_ledger, self.btn_csv, self.btn_cat):
            bar.addWidget(b)
        bar.addStretch(1)
        root.addLayout(bar)

        # --- 筛选条
        fbar = QHBoxLayout()
        fbar.setSpacing(8)
        self.search = SearchBox("搜索证书名称、编号、机构、持证人…")
        self.search.setMinimumWidth(320)
        self.cb_cat = ComboBox()
        self.cb_cat.setMinimumWidth(130)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self._chip_btns = {}
        for key, label in STATUS_FILTERS:
            b = QPushButton(label)
            b.setObjectName("FilterChip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setProperty("key", key)
            b.clicked.connect(lambda _=False, k=key: self._set_status(k))
            self.group.addButton(b)
            self.chips.addWidget(b)
            self._chip_btns[key] = b
        self._chip_btns[""].setChecked(True)
        fbar.addWidget(self.search)
        fbar.addWidget(self.cb_cat)
        fbar.addLayout(self.chips)
        fbar.addStretch(1)
        self.lbl_count = QLabel("—")
        self.lbl_count.setObjectName("Muted")
        fbar.addWidget(self.lbl_count)
        root.addLayout(fbar)

        # --- 内容：表格 + 详情
        split = QSplitter(Qt.Horizontal)
        self.split = split
        self.table = self._table(["证书名称", "分类", "到期日期", "剩余有效期",
                                  "状态", "发证机构", "附件"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3, 4, 5, 6):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.Interactive)
        self.table.horizontalHeader().setMinimumSectionSize(44)
        for i, w in ((1, 94), (2, 98), (3, 98), (4, 96), (5, 132), (6, 44)):
            self.table.setColumnWidth(i, w)
        split.addWidget(self.table)

        self.detail = QScrollArea()
        self.detail.setWidgetResizable(True)
        self.detail.setFrameShape(QFrame.NoFrame)
        self.detail.setMinimumWidth(300)
        self.detail_body = QWidget()
        self.dv = QVBoxLayout(self.detail_body)
        self.dv.setContentsMargins(2, 0, 2, 0)
        self.dv.setSpacing(12)
        self.detail.setWidget(self.detail_body)
        split.addWidget(self.detail)
        split.setSizes([980, 300])
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 1)
        root.addWidget(split, 1)

        self.empty = EmptyState("还没有录入任何证书", "点击下方按钮开始建立你的证书档案库",
                                "cert", "新增第一本证书")
        self.empty.action_clicked.connect(self._new)
        self.empty.setParent(self.table.parent())
        # 空态要占满剩下的整块空间：EmptyState 内部是 AlignCenter，
        # 给它 stretch 才会真正落在「界面中间」。同时必须把 split 一起藏掉 ——
        # split 在根布局里带 stretch=1，只藏它内部的两个子控件的话，
        # 它自己仍然照单全收剩余高度，空态就被压到底部去了。
        root.addWidget(self.empty, 1)
        self.empty.hide()

        # --- 信号
        self.search.textChanged.connect(self._on_search)
        self.cb_cat.currentTextChanged.connect(self._on_cat)
        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_pdf.clicked.connect(self._preview)
        self.btn_sheet.clicked.connect(self._export_sheet)
        self.btn_ledger.clicked.connect(self._export_ledger)
        self.btn_csv.clicked.connect(self._export_csv)
        self.btn_cat.clicked.connect(self._categories)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.itemDoubleClicked.connect(lambda _: self._edit())

    # ------------------------------------------------------------ 事件
    def _on_search(self, text: str) -> None:
        self.kw = text.strip()
        self.refresh()

    def _on_cat(self, text: str) -> None:
        self.cat = "" if text.startswith("全部分类") else text
        self.refresh()

    def _set_status(self, key: str) -> None:
        self.status = key
        self.refresh()

    def _selected_id(self) -> Optional[int]:
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            return None
        return self._rows[r]["id"]

    def _on_select(self) -> None:
        cid = self._selected_id()
        self._render_detail(self.db.get_certificate(cid) if cid else None)

    # ------------------------------------------------------------ 刷新
    def refresh(self) -> None:
        cats = ["全部分类"] + self.db.category_names()
        cur = self.cb_cat.currentText()
        self.cb_cat.blockSignals(True)
        self.cb_cat.clear()
        self.cb_cat.addItems(cats)
        self.cb_cat.setCurrentText(cur if cur in cats else "全部分类")
        self.cb_cat.blockSignals(False)

        self._rows = self.db.certificates(self.kw, self.cat, self.status)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            self._fill_row(i, r)
        self.lbl_count.setText(
            f"共 {len(self._rows)} 本"
            + (f" · 筛选：{self.cat}" if self.cat else "")
            + (f" · {dict(STATUS_FILTERS).get(self.status, '')}" if self.status else ""))

        empty_all = len(self._rows) == 0 and not self.kw and not self.cat and not self.status
        self.table.setVisible(not empty_all)
        self.detail.setVisible(not empty_all)
        self.split.setVisible(not empty_all)
        self.empty.setVisible(empty_all)
        if empty_all:
            self._render_detail(None)
        else:
            cid = self._selected_id()
            if cid is None and self._rows:
                self.table.selectRow(0)
                cid = self._rows[0]["id"]
            self._render_detail(self.db.get_certificate(cid) if cid else None)

    def _fill_row(self, i: int, r: Dict[str, Any]) -> None:
        def item(text: str, color: str = theme.TEXT, bold_: bool = False,
                 tip: str = "") -> QTableWidgetItem:
            it = QTableWidgetItem(text)
            it.setForeground(QColor(color))
            if bold_:
                f = it.font()
                f.setBold(True)
                it.setFont(f)
            if tip:
                it.setToolTip(tip)
            return it

        name = item(r["name"], theme.TEXT, True, r.get("remark", "") or r["name"])
        name.setIcon(QIcon(icons.pixmap("cert", theme.PRIMARY, 16)))
        if not r.get("active", 1):
            name.setText(f"{r['name']}（已停用）")
            name.setForeground(QColor(theme.MUTED))
        self.table.setItem(i, 0, name)

        cat_color = self.db.category_color(r["category"])
        it_cat = item(f"● {r['category']}", cat_color)
        it_cat.setToolTip(r["category"])
        self.table.setItem(i, 1, it_cat)
        self.table.setItem(i, 2, item(r["expiry_date"] or "长期有效", theme.TEXT_SUB))
        self.table.setItem(i, 3, item(r["left_text"], theme.status_color(r["status_key"]),
                                      True))
        st = item(f"● {r['status_label']}", theme.status_color(r["status_key"]), True)
        self.table.setItem(i, 4, st)
        issuer = item(r["issuer"] or "—", theme.TEXT_SUB, False, r["issuer"])
        self.table.setItem(i, 5, issuer)
        ac = r.get("attach_count", 0)
        self.table.setItem(i, 6, item(f"{ac}" if ac else "—",
                                      theme.PRIMARY if ac else theme.MUTED))

    def _render_detail(self, cert: Optional[Dict[str, Any]]) -> None:
        _clear(self.dv)
        if not cert:
            self.dv.addWidget(EmptyState("未选择证书", "在上方表格中选择一本证书查看详情",
                                         "doc"))
            self.dv.addStretch(1)
            return
        key, label, left = dbm.cert_validity(cert.get("expiry_date", ""),
                                             self.db.warn_days(), self.db.urgent_days())

        head = Card()
        t = QLabel(cert["name"])
        t.setWordWrap(True)
        t.setStyleSheet(f"font-size:16px; font-weight:700; color:{theme.TEXT};")
        head.add(t)
        brow = QHBoxLayout()
        brow.setSpacing(6)
        brow.addWidget(status_badge(key))
        brow.addWidget(tag(cert["category"], self.db.category_color(cert["category"])))
        if not cert.get("active", 1):
            brow.addWidget(tag("已停用", theme.MUTED))
        brow.addStretch(1)
        head.add(brow)
        left_lbl = QLabel(dbm.left_text(left))
        left_lbl.setStyleSheet(f"color:{theme.status_color(key)}; font-size:14px;"
                               f" font-weight:700;")
        head.add(left_lbl)
        self.dv.addWidget(head)

        info_card = Card("证书信息")
        pairs = [("证书编号", cert.get("number") or "—"),
                 ("持证人", cert.get("holder") or "—"),
                 ("级别 / 等级", cert.get("level") or "—"),
                 ("发证机构", cert.get("issuer") or "—"),
                 ("发证日期", cert.get("issue_date") or "—"),
                 ("到期日期", cert.get("expiry_date") or "长期有效")]
        # 详情栏窄，采用「标签左 / 取值右」单列排版，避免长机构名过度折行
        for k, v in pairs:
            row = QHBoxLayout()
            row.setSpacing(8)
            kl = QLabel(k)
            kl.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
            kl.setFixedWidth(74)
            kl.setAlignment(Qt.AlignRight | Qt.AlignTop)
            vl = QLabel(v)
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vl.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
            row.addWidget(kl)
            row.addWidget(vl, 1)
            holder = QWidget()
            holder.setLayout(row)
            info_card.add(holder)
        if cert.get("remark"):
            info_card.add(hline())
            rl = QLabel(cert["remark"])
            rl.setWordWrap(True)
            rl.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px;")
            info_card.add(rl)
        self.dv.addWidget(info_card)

        acard = Card("附件", f"{cert.get('attach_count', 0)} 个")
        atts = self.db.attachments(cert["id"])
        if not atts:
            acard.add(QLabel_hint("暂无附件，可在编辑窗口中添加 PDF / 扫描件。"))
        else:
            for a in atts:
                row = QHBoxLayout()
                row.setSpacing(6)
                ic = QLabel()
                ic.setPixmap(icons.pixmap("pdf" if a["kind"] == "pdf" else "doc",
                                          theme.DANGER if a["kind"] == "pdf" else theme.TEXT_SUB,
                                          16))
                row.addWidget(ic)
                name = QLabel(a["title"])
                name.setWordWrap(True)
                name.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
                row.addWidget(name, 1)
                if a["kind"] == "pdf":
                    b = QPushButton("预览")
                    b.setObjectName("Ghost")
                    b.setCursor(Qt.PointingHandCursor)
                    b.clicked.connect(lambda _=False, x=a: self._open_attach(x))
                    row.addWidget(b)
                holder = QWidget()
                holder.setLayout(row)
                acard.add(holder)
        self.dv.addWidget(acard)

        arow = QHBoxLayout()
        b1 = QPushButton("编辑证书")
        b1.setObjectName("Primary")
        realize(b1, "edit", "#ffffff")
        b1.clicked.connect(self._edit)
        b2 = QPushButton("导出信息单")
        realize(b2, "doc", theme.TEXT_SUB)
        b2.clicked.connect(self._export_sheet)
        arow.addWidget(b1)
        arow.addWidget(b2)
        holder = QWidget()
        holder.setLayout(arow)
        self.dv.addWidget(holder)
        self.dv.addStretch(1)

    def _open_attach(self, a: Dict[str, Any]) -> None:
        p = self.db.attachment_abspath(a["path"])
        if not p.exists():
            error(self, "附件文件不存在。")
            return
        PdfViewer(p, "证书 PDF 预览", self).exec()

    # ------------------------------------------------------------ 操作
    def _new(self) -> None:
        dlg = CertDialog(self.db, None, self)
        if dlg.exec():
            self.refresh()
            self.app.notify_changed()
            self.app.toast(f"已新增证书，当前共 {len(self.db.certificates())} 本")

    def _edit(self) -> None:
        cid = self._selected_id()
        if not cid:
            warn(self, "请先选择一本证书。")
            return
        dlg = CertDialog(self.db, cid, self)
        if dlg.exec():
            self.refresh()
            self.app.notify_changed()

    def _delete(self) -> None:
        cid = self._selected_id()
        if not cid:
            warn(self, "请先选择一本证书。")
            return
        cert = self.db.get_certificate(cid)
        if not confirm(self, f"确定删除证书「{cert['name']}」？\n"
                             "其附件副本也会一并删除，操作不可撤销。"):
            return
        self.db.delete_certificate(cid)
        self.refresh()
        self.app.notify_changed()
        self.app.toast("证书已删除")

    def _preview(self) -> None:
        cid = self._selected_id()
        if not cid:
            warn(self, "请先选择一本证书。")
            return
        atts = [a for a in self.db.attachments(cid) if a["kind"] == "pdf"]
        if not atts:
            warn(self, "该证书还没有 PDF 附件。\n可在「编辑」窗口中添加。")
            return
        p = self.db.attachment_abspath(atts[0]["path"])
        if not p.exists():
            error(self, "附件文件不存在。")
            return
        PdfViewer(p, "证书 PDF 预览", self).exec()

    def _export_sheet(self) -> None:
        cid = self._selected_id()
        if not cid:
            warn(self, "请先选择一本证书。")
            return
        cert = self.db.certificate_with_status(cid)
        default = paths.EXPORT_DIR / f"证书信息单_{_safe(cert['name'])}_{_stamp()}.pdf"
        target, _ = QFileDialog.getSaveFileName(self, "导出证书信息单",
                                                str(default), "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            pdfexport.export_certificate(cert, self.db.attachments(cid), Path(target))
        except Exception as exc:  # noqa: BLE001
            error(self, f"导出失败：{exc}")
            return
        if confirm(self, f"已导出到：\n{target}\n\n是否立即打开？"):
            open_path(target)

    def _export_ledger(self) -> None:
        rows = self._rows or self.db.certificates()
        if not rows:
            warn(self, "没有可导出的数据。")
            return
        default = paths.EXPORT_DIR / f"证书台账_{_stamp()}.pdf"
        target, _ = QFileDialog.getSaveFileName(self, "导出台账 PDF",
                                                str(default), "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            pdfexport.export_ledger(rows, Path(target),
                                    scope=self.cat or "全部证书")
        except Exception as exc:  # noqa: BLE001
            error(self, f"导出失败：{exc}")
            return
        if confirm(self, f"已导出 {len(rows)} 条记录到：\n{target}\n\n是否立即打开？"):
            open_path(target)

    def _export_csv(self) -> None:
        rows = self._rows or self.db.certificates()
        if not rows:
            warn(self, "没有可导出的数据。")
            return
        default = paths.EXPORT_DIR / f"证书台账_{_stamp()}.csv"
        target, _ = QFileDialog.getSaveFileName(self, "导出 CSV",
                                                str(default), "CSV 文件 (*.csv)")
        if not target:
            return
        try:
            pdfexport.export_csv(rows, Path(target))
        except Exception as exc:  # noqa: BLE001
            error(self, f"导出失败：{exc}")
            return
        info(self, f"已导出 {len(rows)} 条记录到：\n{target}")

    def _categories(self) -> None:
        dlg = CategoryDialog(self.db, self)
        dlg.changed.connect(self.refresh)
        dlg.changed.connect(lambda: self.app.notify_changed())
        dlg.exec()
        self.refresh()


def QLabel_hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setObjectName("Muted")
    return lbl


def _safe(name: str) -> str:
    return "".join(ch for ch in name if ch not in '\\/:*?"<>|').strip()[:40] or "证书"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


# =============================================================== 到期提醒


class ReminderPage(Page):
    """到期提醒 + 提醒处置。

    版式（v1.3.0 重排）：一行 = 状态色徽标 / 证书名 + 一行元信息 / **一个**状态胶囊 /
    处置 / 查看。

    ★ 旧版被用户指出「排版不对」，实测下来是三件事叠在一起：
      - 名称列被右侧四件套挤到一半宽，长名字换行 → 同组行高参差；
      - 「已过期」在状态徽章和剩余天数里**各说了一遍**；
      - 元信息（分类 · 编号 · 发证机构）既不省略也不换行，直接把行撑宽。
    """

    PAGE_TITLE = "到期提醒"
    PAGE_SUB = "按剩余天数分级跟踪证书有效期，支持逐条处置"

    VIEWS = [("active", "需要关注"), ("postponed", "已延期"),
             ("ignored", "已忽略"), ("all", "全部到期")]

    HELD = {
        "postponed": ("已延期的证书", theme.PRIMARY,
                      "这些证书在所选日期之前不会再打扰你；过了那天自动回到「需要关注」。"),
        "ignored": ("已忽略的证书", theme.MUTED,
                    "已按你的选择静默，随时可以恢复提醒。"),
    }

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        self._view = "active"
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        bar = QHBoxLayout()
        self.cards = QHBoxLayout()
        self.cards.setSpacing(14)
        self.s_expired = StatCard("已过期", "0", theme.DANGER, "warn")
        self.s_urgent = StatCard("紧急", "0", "#e0622c", "clock")
        self.s_soon = StatCard("即将到期", "0", theme.WARN, "bell")
        self.s_valid = StatCard("安全期内", "0", theme.SUCCESS, "check")
        for c in (self.s_expired, self.s_urgent, self.s_soon, self.s_valid):
            self.cards.addWidget(c, 1)
        bar.addLayout(self.cards)
        root.addLayout(bar)

        head = QHBoxLayout()
        head.setSpacing(10)
        self.sec_title = SectionTitle("需要关注的证书")
        head.addWidget(self.sec_title)
        self.lab_held = QLabel("")
        self.lab_held.setObjectName("Muted")
        head.addWidget(self.lab_held)
        head.addStretch(1)
        self.cmb_view = ComboBox()
        for k, label in self.VIEWS:
            self.cmb_view.addItem(label, k)
        self.cmb_view.setToolTip("切换清单：只看待处理的，或回看已延期 / 已忽略的")
        self.cmb_view.currentIndexChanged.connect(self._change_view)
        self.spin_warn = ComboBox()
        for v in (30, 60, 90, 180, 365):
            self.spin_warn.addItem(f"提前 {v} 天提醒", v)
        self.spin_warn.setCurrentIndex(2)
        self.spin_warn.setToolTip("进入「即将到期」的天数阈值")
        self.spin_warn.currentIndexChanged.connect(self._change_warn)
        btn_set = QPushButton("提醒设置")
        realize(btn_set, "settings", theme.TEXT_SUB)
        btn_set.setToolTip("提醒阈值、启动弹窗等全局设置")
        btn_set.clicked.connect(self._settings)
        btn_now = QPushButton("立即检查")
        btn_now.setObjectName("Primary")
        realize(btn_now, "bell", "#ffffff")
        btn_now.setToolTip("弹出一览面板")
        btn_now.clicked.connect(self.app.show_reminder)
        for w in (self.cmb_view, self.spin_warn, btn_set, btn_now):
            head.addWidget(w)
        root.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.inner = QWidget()
        self.iv = QVBoxLayout(self.inner)
        self.iv.setContentsMargins(0, 0, 6, 0)
        self.iv.setSpacing(10)
        scroll.setWidget(self.inner)
        root.addWidget(scroll, 1)

    # ---------------------------------------------------------------- 交互
    def _change_warn(self) -> None:
        self.db.set_setting("warn_days", str(self.spin_warn.currentData()))
        self.refresh()
        self.app.notify_changed()

    def _change_view(self) -> None:
        self._view = self.cmb_view.currentData() or "active"
        self.refresh()

    def _settings(self) -> None:
        dlg = SettingsDialog(self.db, self)
        dlg.changed.connect(self.app.reload_all)
        dlg.exec()

    def _dispose_menu(self, r: Dict[str, Any]) -> QMenu:
        """一行证书的处置菜单：延期 / 忽略 / 标记已处理 / 恢复。"""
        m = QMenu(self)
        cid = r["id"]

        mp = m.addMenu("延期提醒")
        for d in dbm.POSTPONE_CHOICES:
            a = mp.addAction(f"延后 {d} 天")
            a.triggered.connect(lambda _=False, c=cid, dd=d: self._postpone(c, dd))
        mp.addSeparator()
        a = mp.addAction("自定义日期…")
        a.triggered.connect(lambda _=False, c=cid: self._postpone_custom(c))

        mi = m.addMenu("忽略提醒")
        for d in dbm.IGNORE_CHOICES:
            a = mi.addAction("永久忽略" if d == 0 else f"忽略 {d} 天")
            a.triggered.connect(lambda _=False, c=cid, dd=d: self._ignore(c, dd))

        m.addSeparator()
        a = m.addAction("标记为已处理")
        a.setToolTip("我已自行换证 / 提交材料，今天不要再提醒")
        a.triggered.connect(lambda _=False, c=cid: self._handle(c))
        if r.get("postponed_until") or r.get("ignored_until"):
            a = m.addAction("恢复提醒")
            a.triggered.connect(lambda _=False, c=cid: self._restore(c))
        return m

    def _postpone(self, cid: int, days: int) -> None:
        until = self.db.postpone_reminder(cid, days)
        self._done(f"已延至 {until}，之前不再提醒")

    def _postpone_custom(self, cid: int) -> None:
        row = self.db.certificate_with_status(cid) or {}
        dlg = PostponeDialog(row.get("name", "这本证书"), self)
        if not dlg.exec():
            return
        until = self.db.postpone_reminder(cid, 0, dlg.until())
        self._done(f"已延至 {until}，之前不再提醒")

    def _ignore(self, cid: int, days: int) -> None:
        until = self.db.ignore_reminder(cid, days)
        self._done("已永久忽略" if days <= 0 else f"已忽略至 {until}")

    def _handle(self, cid: int) -> None:
        self.db.handle_reminder(cid)
        self._done("已标记处理，今天不再提醒")

    def _restore(self, cid: int) -> None:
        self.db.restore_reminder(cid)
        self._done("已恢复正常提醒")

    def _done(self, msg: str) -> None:
        self.app.toast(msg)
        self.refresh()
        self.app.notify_changed()

    # ---------------------------------------------------------------- 渲染
    def refresh(self) -> None:
        warn_days = self.db.warn_days()
        idx = self.spin_warn.findData(warn_days)
        self.spin_warn.blockSignals(True)
        self.spin_warn.setCurrentIndex(idx if idx >= 0 else 2)
        self.spin_warn.blockSignals(False)
        # 视图下拉与 self._view 必须一致：程序化切视图（探针 / 快捷入口）时
        # 下拉框也要跟上，否则标题写着「已延期的证书」而下拉还显示「需要关注」
        vidx = self.cmb_view.findData(self._view)
        if vidx != self.cmb_view.currentIndex():
            self.cmb_view.blockSignals(True)
            self.cmb_view.setCurrentIndex(max(0, vidx))
            self.cmb_view.blockSignals(False)

        rows = self.db.expiring()                        # 已排除被处置的
        allrows = self.db.expiring(include_suppressed=True)
        expired = [r for r in rows if r["status_key"] == "expired"]
        urgent = [r for r in rows if r["status_key"] == "urgent"]
        soon = [r for r in rows if r["status_key"] == "soon"]
        st = self.db.certificate_stats()
        self.s_expired.set_value(str(len(expired)))
        self.s_urgent.set_value(str(len(urgent)))
        self.s_soon.set_value(str(len(soon)))
        self.s_valid.set_value(str(st["valid"] + st["permanent"]))

        held = [r for r in allrows if r["suppressed"]]
        n_post = sum(1 for r in held if r["suppressed"] == "postponed")
        n_ign = len(held) - n_post
        self.lab_held.setText(
            f"已处置 {len(held)} 本 · 延期 {n_post} · 忽略 {n_ign}" if held else "")

        _clear(self.iv)
        self.sec_title.setText(self._view_title())
        groups, empty = self._groups(rows, allrows, warn_days)
        if not groups:
            # 上下各一个 stretch，把空态夹在正中间（此前只在下面加 stretch，
            # 空态会贴着统计卡下方，看着像没排完版）
            self.iv.addStretch(1)
            self.iv.addWidget(EmptyState(*empty))
            self.iv.addStretch(1)
            return
        for title, group, tone, desc in groups:
            card = Card(title, f"{len(group)} 本", padding=16)
            card.title.setStyleSheet(
                f"font-size:15px; font-weight:700; color:{tone};")
            d = QLabel(desc)
            d.setObjectName("Muted")
            d.setWordWrap(True)
            card.add(d)
            for r in group:
                card.add(self._row(r))
            self.iv.addWidget(card)
        self.iv.addStretch(1)

    def _view_title(self) -> str:
        return {
            "active": "需要关注的证书",
            "postponed": "已延期的证书",
            "ignored": "已忽略的证书",
            "all": "全部到期记录",
        }.get(self._view, "需要关注的证书")

    def _groups(self, rows: List[Dict[str, Any]], allrows: List[Dict[str, Any]],
                warn_days: int):
        """按当前视图算出 [(标题, 行, 主色, 说明)]；没有内容时同时返回空态参数。"""
        view = self._view
        if view in ("active", "all"):
            src = rows if view == "active" else allrows
            out = []
            for title, key, tone, desc in (
                    ("已过期", "expired", theme.DANGER,
                     "已超出有效期，请尽快核实并办理换证、续期或更新档案。"),
                    ("紧急", "urgent", "#e0622c",
                     f"距到期不足 {self.db.urgent_days()} 天，建议立即安排续期。"),
                    ("即将到期", "soon", theme.WARN,
                     f"距到期不足 {warn_days} 天，可提前准备材料。")):
                g = [r for r in src if r["status_key"] == key]
                if g:
                    out.append((title, g, tone, desc))
            if out:
                return out, ()
            if view == "active":
                return [], ("当前没有需要关注的证书",
                            "所有证书都在有效期内，保持定期复查即可。", "check")
            return [], ("暂无到期记录", "证书库里还没有临近到期的证书。", "clock")

        title, tone, desc = self.HELD[view]
        g = [r for r in allrows if r["suppressed"] == view]
        if g:
            return [(title, g, tone, desc)], ()
        if view == "postponed":
            return [], ("没有延期的证书",
                        "在需要关注的证书上点「处置 → 延期提醒」，"
                        "可以把它推到以后再提醒。", "clock")
        return [], ("没有已忽略的证书",
                    "在需要关注的证书上点「处置 → 忽略提醒」，"
                    "可以暂时不再提醒它。", "bell")

    def _row(self, r: Dict[str, Any]) -> QWidget:
        tone = theme.status_color(r["status_key"])
        w = QFrame()
        w.setObjectName("RemindRow")
        w.setStyleSheet(f"#RemindRow {{ background:#fbfcfe;"
                        f" border:1px solid {theme.BORDER}; border-radius:9px; }}")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(13, 10, 13, 10)
        lay.setSpacing(11)

        ic = QLabel()
        ic.setFixedSize(32, 32)
        ic.setAlignment(Qt.AlignCenter)
        ic.setPixmap(icons.pixmap("cert", tone, 18))
        ic.setStyleSheet(f"background:{_tint(tone)}; border-radius:9px;")
        lay.addWidget(ic, 0, Qt.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(3)
        name = ElidedLabel(r["name"])       # 单行省略，名字再长也不换行撑高
        name.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; font-size:13px;")
        col.addWidget(name)
        bits = [f"到期 {r['expiry_date'] or '长期有效'}", r["category"]]
        if r.get("number"):
            bits.append(f"编号 {r['number']}")
        if r.get("issuer"):
            bits.append(r["issuer"])
        meta = ElidedLabel(" · ".join(bits))
        meta.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
        col.addWidget(meta)
        lay.addLayout(col, 1)

        # 一个胶囊说完一件事：状态 + 剩余天数（不再「徽章一遍、剩余天数一遍」）
        if r.get("suppressed"):
            txt = dbm.suppress_label(r)
            tone_chip = theme.PRIMARY if r["suppressed"] == "postponed" else theme.MUTED
        else:
            txt = r["left_text"]
            tone_chip = tone
        chip = QLabel(txt)
        chip.setAlignment(Qt.AlignCenter)
        chip.setFixedWidth(132)            # 固定宽 → 同一视图里右侧按钮列才对得齐
        chip.setStyleSheet(f"background:{_tint(tone_chip, 32)}; color:{tone_chip};"
                           f" border-radius:9px; padding:4px 8px;"
                           f" font-weight:700; font-size:12px;")
        lay.addWidget(chip, 0, Qt.AlignVCenter)

        if r.get("suppressed"):
            b_act = QPushButton("恢复提醒")
            realize(b_act, "refresh", theme.PRIMARY, 15)
            b_act.setCursor(Qt.PointingHandCursor)
            b_act.setToolTip("清除处置，恢复正常提醒")
            b_act.clicked.connect(lambda _=False, c=r["id"]: self._restore(c))
        else:
            b_act = QPushButton("处置")
            realize(b_act, "more", theme.TEXT_SUB, 15)
            b_act.setCursor(Qt.PointingHandCursor)
            b_act.setToolTip("延期 / 忽略 / 标记已处理")
            b_act.setMenu(self._dispose_menu(r))
        b_act.setFixedWidth(88)
        lay.addWidget(b_act, 0, Qt.AlignVCenter)

        btn = QPushButton("查看")
        btn.setObjectName("Ghost")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedWidth(56)
        btn.setToolTip("到证书管理里查看这本证书")
        btn.clicked.connect(lambda _=False: self.app.goto("certs"))
        lay.addWidget(btn, 0, Qt.AlignVCenter)
        return w



# =============================================================== 考试计划


class ExamPage(Page):
    PAGE_TITLE = "考试计划"
    PAGE_SUB = "规划考试节点、报名截止与备考进度"

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        self._rows: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_new = QPushButton("新增考试")
        self.btn_new.setObjectName("Primary")
        realize(self.btn_new, "plus", "#ffffff")
        self.btn_edit = QPushButton("编辑")
        realize(self.btn_edit, "edit", theme.TEXT_SUB)
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("Danger")
        realize(self.btn_del, "trash", theme.DANGER)
        self.btn_pdf = QPushButton("导出计划表")
        realize(self.btn_pdf, "export", theme.TEXT_SUB)
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_del)
        bar.addSpacing(10)
        bar.addWidget(self.btn_pdf)
        bar.addStretch(1)
        self.search = SearchBox("搜索考试名称、考点、备注…")
        bar.addWidget(self.search)
        root.addLayout(bar)

        stat = QHBoxLayout()
        stat.setSpacing(14)
        self.s_plan = StatCard("计划中", "0", theme.PRIMARY, "calendar")
        self.s_hot = StatCard("30 天内", "0", theme.WARN, "clock")
        self.s_done = StatCard("已通过", "0", theme.SUCCESS, "check")
        for c in (self.s_plan, self.s_hot, self.s_done):
            stat.addWidget(c, 1)
        root.addLayout(stat)

        self.table = self._table(["考试名称", "关联证书", "考试日期", "倒计时",
                                  "报名截止", "考点", "费用", "状态", "成绩"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)
        for i, w in ((1, 110), (2, 100), (3, 110), (4, 100), (6, 90), (7, 80), (8, 80)):
            self.table.setColumnWidth(i, w)
        root.addWidget(self.table, 1)

        self.empty = EmptyState("还没有考试计划", "把下一次考证的时间节点记下来，到期自动倒计时",
                                "calendar", "新增考试计划")
        self.empty.action_clicked.connect(self._new)
        # stretch=1：空态要占满表格让出的整块空间，内部 AlignCenter 才能把它放在正中间
        root.addWidget(self.empty, 1)
        self.empty.hide()

        self.search.textChanged.connect(lambda _: self.refresh())
        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_pdf.clicked.connect(self._export)
        self.table.itemDoubleClicked.connect(lambda _: self._edit())

    def _selected_id(self) -> Optional[int]:
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            return None
        return self._rows[r]["id"]

    def refresh(self) -> None:
        self._rows = self.db.exams(self.search.text().strip())
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rows))
        for i, r in enumerate(self._rows):
            def item(text: str, color: str = theme.TEXT, bold_: bool = False):
                it = QTableWidgetItem(text)
                it.setForeground(QColor(color))
                if bold_:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                return it
            it = item(r["name"], theme.TEXT, True)
            it.setIcon(QIcon(icons.pixmap("calendar", theme.PRIMARY, 16)))
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, item(r["category"] or "—", theme.TEXT_SUB))
            self.table.setItem(i, 2, item(r["exam_date"] or "—", theme.TEXT_SUB))
            d = r.get("days_left")
            if d is None:
                tone, txt = theme.MUTED, "—"
            elif d < 0:
                tone, txt = theme.MUTED, f"已结束 {abs(d)} 天"
            elif d == 0:
                tone, txt = theme.DANGER, "今天"
            elif d <= 7:
                tone, txt = theme.DANGER, f"{d} 天"
            elif d <= 30:
                tone, txt = "#e0622c", f"{d} 天"
            else:
                tone, txt = theme.SUCCESS, f"{d} 天"
            self.table.setItem(i, 3, item(txt, tone, True))
            self.table.setItem(i, 4, item(r["reg_deadline"] or "—", theme.TEXT_SUB))
            self.table.setItem(i, 5, item(r["location"] or "—", theme.TEXT_SUB))
            self.table.setItem(i, 6, item(r["fee"] or "—", theme.TEXT_SUB))
            state_tone = {"计划中": theme.PRIMARY, "已报名": theme.WARN,
                          "已通过": theme.SUCCESS, "未通过": theme.DANGER,
                          "已取消": theme.MUTED}.get(r["state"], theme.TEXT_SUB)
            self.table.setItem(i, 7, item(r["state"], state_tone, True))
            self.table.setItem(i, 8, item(r["score"] or "—", theme.TEXT_SUB))

        plan = [r for r in self._rows if r["state"] in ("计划中", "已报名")]
        self.s_plan.set_value(str(len(plan)))
        self.s_hot.set_value(str(len([r for r in plan
                                      if r["days_left"] is not None and 0 <= r["days_left"] <= 30])))
        self.s_done.set_value(str(len([r for r in self._rows if r["state"] == "已通过"])))

        has = len(self._rows) > 0
        self.table.setVisible(has)
        self.empty.setVisible(not has)

    def _new(self) -> None:
        if ExamDialog(self.db, None, self).exec():
            self.refresh()
            self.app.notify_changed()
            self.app.toast("已保存考试计划")

    def _edit(self) -> None:
        eid = self._selected_id()
        if not eid:
            warn(self, "请先选择一条考试计划。")
            return
        if ExamDialog(self.db, eid, self).exec():
            self.refresh()
            self.app.notify_changed()

    def _delete(self) -> None:
        eid = self._selected_id()
        if not eid:
            warn(self, "请先选择一条考试计划。")
            return
        if not confirm(self, "确定删除该考试计划？"):
            return
        self.db.delete_exam(eid)
        self.refresh()
        self.app.notify_changed()

    def _export(self) -> None:
        rows = self._rows
        if not rows:
            warn(self, "没有可导出的考试计划。")
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "导出考试计划表",
            str(paths.EXPORT_DIR / f"考试计划表_{_stamp()}.pdf"), "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            pdfexport.export_exam_plan(rows, Path(target))
        except Exception as exc:  # noqa: BLE001
            error(self, f"导出失败：{exc}")
            return
        if confirm(self, f"已导出到：\n{target}\n\n是否立即打开？"):
            open_path(target)


# =============================================================== 学习资料


class MaterialPage(Page):
    PAGE_TITLE = "学习资料"
    PAGE_SUB = "按科目整理教材、真题、网课与政策文件"

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        self.cat = ""
        self._rows: List[Dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_new = QPushButton("新增资料")
        self.btn_new.setObjectName("Primary")
        realize(self.btn_new, "plus", "#ffffff")
        self.btn_edit = QPushButton("编辑")
        realize(self.btn_edit, "edit", theme.TEXT_SUB)
        self.btn_del = QPushButton("删除")
        self.btn_del.setObjectName("Danger")
        realize(self.btn_del, "trash", theme.DANGER)
        self.btn_open = QPushButton("打开资料")
        self.btn_open.setObjectName("Gold")
        realize(self.btn_open, "open", "#3a2f07")
        bar.addWidget(self.btn_new)
        bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_del)
        bar.addSpacing(10)
        bar.addWidget(self.btn_open)
        bar.addStretch(1)
        self.search = SearchBox("搜索资料名称、备注…")
        bar.addWidget(self.search)
        root.addLayout(bar)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.chip_box = chips
        root.addLayout(chips)

        self.table = self._table(["资料名称", "分类", "类型", "地址 / 路径", "备注"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(4, 220)
        root.addWidget(self.table, 1)

        self.empty = EmptyState("还没有整理学习资料", "把教材、真题、网课链接集中在这里，考证更从容",
                                "book", "新增学习资料")
        self.empty.action_clicked.connect(self._new)
        # 同上：占满表格让出的空间，空态落在正中间
        root.addWidget(self.empty, 1)
        self.empty.hide()

        self.search.textChanged.connect(lambda _: self.refresh())
        self.btn_new.clicked.connect(self._new)
        self.btn_edit.clicked.connect(self._edit)
        self.btn_del.clicked.connect(self._delete)
        self.btn_open.clicked.connect(self._open)
        self.table.itemDoubleClicked.connect(lambda _: self._open())

    def _build_chips(self) -> None:
        cur = self.cat
        while self.chip_box.count():
            item = self.chip_box.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        for b in list(self.group.buttons()):
            self.group.removeButton(b)
        cats = [""] + [c for c in dbm.MATERIAL_CATEGORIES
                       if c in self.db.material_stats()]
        for c in cats:
            label = "全部" if not c else c
            btn = QPushButton(label)
            btn.setObjectName("FilterChip")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setChecked(c == cur)
            btn.clicked.connect(lambda _=False, k=c: self._set_cat(k))
            self.group.addButton(btn)
            self.chip_box.addWidget(btn)
        self.chip_box.addStretch(1)

    def _set_cat(self, key: str) -> None:
        self.cat = key
        self.refresh()

    def _selected_id(self) -> Optional[int]:
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            return None
        return self._rows[r]["id"]

    def refresh(self) -> None:
        self._build_chips()
        self._rows = self.db.materials(self.search.text().strip(), self.cat)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self._rows))
        kinds = {"link": ("网络链接", theme.PRIMARY), "file": ("本地文件", theme.SUCCESS),
                 "dir": ("本地文件夹", theme.GOLD)}
        for i, r in enumerate(self._rows):
            def item(text: str, color: str = theme.TEXT, bold_: bool = False):
                it = QTableWidgetItem(text)
                it.setForeground(QColor(color))
                if bold_:
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                return it
            it = item(r["title"], theme.TEXT, True)
            it.setIcon(QIcon(icons.pixmap("book", theme.PRIMARY, 16)))
            it.setToolTip(r["title"])
            self.table.setItem(i, 0, it)
            self.table.setItem(i, 1, item(r["category"], theme.GOLD, True))
            klabel, kcolor = kinds.get(r["kind"], ("其他", theme.MUTED))
            self.table.setItem(i, 2, item(klabel, kcolor))
            self.table.setItem(i, 3, item(r["target"] or "—", theme.TEXT_SUB))
            self.table.setItem(i, 4, item(r["note"] or "—", theme.MUTED))
        has = len(self._rows) > 0
        self.table.setVisible(has)
        self.empty.setVisible(not has)

    def _new(self) -> None:
        if MaterialDialog(self.db, None, self).exec():
            self.refresh()
            self.app.notify_changed()

    def _edit(self) -> None:
        mid = self._selected_id()
        if not mid:
            warn(self, "请先选择一条资料。")
            return
        if MaterialDialog(self.db, mid, self).exec():
            self.refresh()
            self.app.notify_changed()

    def _delete(self) -> None:
        mid = self._selected_id()
        if not mid:
            warn(self, "请先选择一条资料。")
            return
        if not confirm(self, "确定删除该学习资料条目？（不会删除本地文件）"):
            return
        self.db.delete_material(mid)
        self.refresh()
        self.app.notify_changed()

    def _open(self) -> None:
        mid = self._selected_id()
        if not mid:
            warn(self, "请先选择一条资料。")
            return
        row = [r for r in self._rows if r["id"] == mid][0]
        target = row["target"].strip()
        if not target:
            warn(self, "该条目没有填写地址。")
            return
        if row["kind"] == "link":
            if not open_url(target) and not open_path(target):
                error(self, "无法打开该链接。")
        else:
            if not Path(target).exists():
                error(self, f"文件或目录不存在：\n{target}")
                return
            if not open_path(target):
                error(self, "无法打开该文件。")


# =============================================================== 关于声明


def _tint(color: str, alpha: int = 30) -> str:
    """把品牌色压成淡底。Qt 样式表只认 ``rgba()`` 或 ``#AARRGGBB``。"""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {alpha / 255:.3f})"


class ContactRow(QWidget):
    """一行联系方式：徽标 + 平台名 + 地址，整行可点，右侧一个「复制」。

    ⚠️ QWidget 的 Python 子类**默认不绘制** QSS 的 background（只有 QFrame
    与少量内建控件会），所以这里必须自己打开 ``WA_StyledBackground``，
    否则 hover 的淡底完全不会出现 —— 顶栏的背景曾因此失效了整整四个版本。
    """

    def __init__(self, icon_name: str, color: str, title: str, addr: str,
                 target: str, toast, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._target = target
        self._toast = toast
        self.setObjectName("ContactRow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"打开 {target}")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 9, 10, 9)
        lay.setSpacing(12)

        badge = QLabel()
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, color, 19))
        badge.setStyleSheet(f"background:{_tint(color)}; border-radius:10px;")
        lay.addWidget(badge, 0, Qt.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"color:{theme.TEXT}; font-size:13px; font-weight:600;")
        col.addWidget(t)
        a = QLabel(addr)
        a.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        col.addWidget(a)
        lay.addLayout(col, 1)

        btn = QPushButton("复制")
        btn.setObjectName("Ghost")
        realize(btn, "doc", theme.TEXT_SUB, 15)
        btn.setFixedHeight(28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setToolTip("复制该地址")
        btn.clicked.connect(self._copy)
        lay.addWidget(btn, 0, Qt.AlignVCenter)

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self._target)
        self._toast("地址已复制到剪贴板")

    def mousePressEvent(self, e) -> None:  # noqa: N802
        # 按钮吃掉自己的点击，不会冒泡到这一层，所以这里只处理行内的空白与文字
        if e.button() == Qt.LeftButton and not open_url(self._target):
            error(self, "无法打开该链接，请手动复制地址。")
        super().mousePressEvent(e)


class AboutPage(Page):
    PAGE_TITLE = "关于与声明"
    PAGE_SUB = "版本信息、版权声明与免责条款"

    def __init__(self, app, parent: Optional[QWidget] = None) -> None:
        super().__init__(app, parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 20)
        root.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(14)

        # --- 品牌卡
        brand = Card(padding=22)
        top = QHBoxLayout()
        top.setSpacing(16)
        # 「视角跟随」徽标：鼠标移动时分层视差，做出 Live2D 式的转头感
        logo = GazeLogo(72)
        top.addWidget(logo)
        col = QVBoxLayout()
        col.setSpacing(4)
        name = QLabel(version.APP_NAME)
        name.setStyleSheet(f"font-size:22px; font-weight:700; color:{theme.TEXT};")
        col.addWidget(name)
        en = QLabel(f"{version.APP_NAME_EN} · {version.APP_SLOGAN}")
        en.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
        col.addWidget(en)
        ver = QLabel(f"版本 {version.FULL_VERSION}    ·    构建日期 {version.BUILD_DATE}")
        ver.setStyleSheet(f"color:{theme.PRIMARY}; font-size:12px;"
                          f" font-family:{theme.MONO_FAMILY};")
        col.addWidget(ver)
        col.addStretch(1)
        top.addLayout(col, 1)
        brand.add(top)

        badges = QHBoxLayout()
        badges.setSpacing(8)
        badges.addWidget(tag("开源软件", theme.SUCCESS))
        badges.addWidget(tag("100% 离线", theme.PRIMARY))
        badges.addWidget(tag("绿色单文件", theme.GOLD))
        badges.addWidget(tag("禁止未授权商用", theme.DANGER))
        badges.addStretch(1)
        brand.add(badges)
        v.addWidget(brand)

        # --- 版权
        cr = Card("版权信息")
        c1 = QLabel(version.COPYRIGHT)
        c1.setStyleSheet(f"font-size:15px; font-weight:700; color:{theme.TEXT};")
        cr.add(c1)
        c2 = QLabel(version.LICENSE_LINE)
        c2.setWordWrap(True)
        c2.setStyleSheet(f"color:{theme.DANGER}; font-size:13px; font-weight:600;")
        cr.add(c2)
        c3 = QLabel("本软件为开源软件，没有授权禁止用于商业用途。"
                    "在保留本声明与版权信息完整的前提下，允许个人免费使用、学习与研究。")
        c3.setWordWrap(True)
        c3.setObjectName("Muted")
        cr.add(c3)
        v.addWidget(cr)

        # --- 联系作者
        con = Card("联系作者")
        con.add(self._para("遇到问题、想提建议，或者希望合作 / 转载 / 二次分发，"
                           "都可以用下面任一方式找到我 —— 点整行直接打开，"
                           "右侧可一键复制地址。"))
        for icon_name, ct, addr, target, color in version.CONTACTS:
            con.add(ContactRow(icon_name, color, ct, addr, target, self.app.toast))
        v.addWidget(con)

        # --- 功能一览
        feat = Card("功能一览")
        for icon_name, title, desc in (
            ("bell", "证书有效期到期前自动提醒",
             "启动即扫描，按「已过期 / 紧急 / 即将到期」三级分色呈现；提醒阈值可自定义，"
             "跨日自动刷新，支持当天免打扰。"),
            ("pdf", "证书 PDF 预览与导出",
             "内置 PDF 阅读器可直接预览证书扫描件（翻页 / 缩放 / 适应宽度），"
             "并可导出台账 PDF、CSV 与单张证书信息单。"),
            ("folder", "证书分类归档",
             "自定义分类与配色，支持搜索、状态筛选，附件随库保存，随时检索。"),
            ("calendar", "考试计划管理",
             "登记考试日期、报名截止、考点与费用，自动计算倒计时，并支持导出计划表。"),
            ("book", "学习资料整理",
             "集中管理教材、真题、网课与政策文件，一键跳转或打开本地资料。"),
        ):
            row = QHBoxLayout()
            row.setSpacing(10)
            ic = QLabel()
            ic.setPixmap(icons.pixmap(icon_name, theme.PRIMARY, 20))
            ic.setFixedWidth(26)
            row.addWidget(ic)
            col2 = QVBoxLayout()
            col2.setSpacing(2)
            tt = QLabel(title)
            tt.setStyleSheet(f"color:{theme.TEXT}; font-weight:600; font-size:13px;")
            col2.addWidget(tt)
            dd = QLabel(desc)
            dd.setWordWrap(True)
            dd.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
            col2.addWidget(dd)
            row.addLayout(col2, 1)
            holder = QWidget()
            holder.setLayout(row)
            feat.add(holder)
        v.addWidget(feat)

        # --- 声明
        disc = Card("声明与免责条款")
        lines = version.DISCLAIMER.strip().split("\n")
        cur_lines: List[str] = []
        for ln in lines:
            if ln and (ln[0] in "一二三四五六" and ln[1:2] == "、"):
                if cur_lines:
                    disc.add(self._para("\n".join(cur_lines)))
                    cur_lines = []
                disc.add(bold(ln, 13, theme.PRIMARY))
            else:
                cur_lines.append(ln)
        if cur_lines:
            disc.add(self._para("\n".join(cur_lines)))
        v.addWidget(disc)

        # --- 数据与运行环境
        env = Card("运行环境与数据")
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        items = [("软件版本", version.FULL_VERSION),
                 ("内部构建号", version.BUILD),
                 ("运行模式", "单文件 exe（独立运行，不依赖浏览器）"),
                 ("数据目录", str(paths.DATA_DIR)),
                 ("数据库", str(paths.DB_PATH)),
                 ("附件目录", str(paths.FILES_DIR)),
                 ("导出目录", str(paths.EXPORT_DIR))]
        for i, (k, val) in enumerate(items):
            kl = QLabel(k)
            kl.setStyleSheet(f"color:{theme.MUTED}; font-size:12px;")
            vl = QLabel(val)
            vl.setWordWrap(True)
            vl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            vl.setStyleSheet(f"color:{theme.TEXT}; font-size:12px;")
            grid.addWidget(kl, i // 2, (i % 2) * 2)
            grid.addWidget(vl, i // 2, (i % 2) * 2 + 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        env.add(grid)
        arow = QHBoxLayout()
        b1 = QPushButton("打开数据目录")
        realize(b1, "folder", theme.TEXT_SUB)
        b1.clicked.connect(lambda: open_path(paths.DATA_DIR))
        b2 = QPushButton("打开导出目录")
        realize(b2, "export", theme.TEXT_SUB)
        b2.clicked.connect(lambda: open_path(paths.EXPORT_DIR))
        b3 = QPushButton("备份数据库")
        realize(b3, "database", theme.TEXT_SUB)
        b3.clicked.connect(self._backup)
        b4 = QPushButton("复制版本号")
        realize(b4, "doc", theme.TEXT_SUB)
        b4.clicked.connect(self._copy_version)
        for b in (b1, b2, b3, b4):
            arow.addWidget(b)
        arow.addStretch(1)
        holder2 = QWidget()
        holder2.setLayout(arow)
        env.add(holder2)
        v.addWidget(env)

        v.addStretch(1)
        scroll.setWidget(inner)
        root.addWidget(scroll)

    def _para(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px; line-height:150%;")
        return lbl

    def _backup(self) -> None:
        p = self.db.backup()
        if p:
            info(self, f"已备份到：\n{p}")
        else:
            error(self, "备份失败。")

    def _copy_version(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(f"{version.APP_NAME} {version.FULL_VERSION}")
        self.app.toast("版本号已复制到剪贴板")
