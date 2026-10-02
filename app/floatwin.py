# -*- coding: utf-8 -*-
"""窗口悬浮窗：常驻桌面的证书速览小面板。

版式参考「农历日历」那种密集浮窗 —— 一条窄头部（图标 + 名称 + 计数胶囊 + 图标按钮）、
若干带小标题的分区块、一行版权说明、底部一排动作按钮。配色沿用本项目的档案馆蓝金调，
不照搬参考图的朱红。

四条关键设计：

1. **自绘圆角面板**：窗口是 ``FramelessWindowHint`` + ``WA_TranslucentBackground``，
   QSS 的 ``border-radius`` 只能把四个角涂透明，真正圆角裁剪必须自己画路径。
   顺带解决「贴边收起」时把手柄画在哪。

2. **拖动自己实现**，不用 ``startSystemMove()``。原因有二：
   · 需要在拖动过程中**实时吸附**（系统移动循环里拿不到「松手」之外的时机）；
   · 还需要「贴边收起」这种探出 8px 的停靠态，系统循环完全不认。
   ⚠️ 代价是失去 Aero Snap / Win+方向键 —— 对一块随手放着的小面板来说无所谓。

3. **位置与选项全部落库**（``float_*`` 设置项）。悬浮窗的「记忆」是它的核心体验：
   重启之后必须还在原位置、还是那几块内容。

4. **内容块可自选**：7 个块各自是一个 ``Block`` 子类，``refresh()`` 时重建内容。
   右键菜单和设置面板都能改，两边共用 ``set_block()`` / ``set_option()`` 单一入口，
   不存在「菜单改了设置没改」这类不一致。

⚠️ 两个容易踩的点：
   · ``Qt.Tool`` 让窗口不进任务栏 / 不进 Alt-Tab（这正是悬浮窗该有的样子），但它在
     Windows 上会跟随父窗口最小化 —— 这是期望行为，别改成 ``Qt.Window``。
   · 顶层控件的 ``leaveEvent`` 在鼠标**移入子控件**时也会触发（Qt 有意如此），
     所以「贴边收起」绝不能直接用 leaveEvent 判定，必须延迟一拍再问
     「光标是否真的离开了窗口矩形」。
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import (QEasingCurve, QPoint, QPropertyAnimation, QRect,
                            QRectF, QSize, Qt, QTimer, Signal)
from PySide6.QtGui import (QColor, QCursor, QFontMetrics, QPainter, QPainterPath,
                           QPen)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMenu, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from . import db as dbm
from . import icons, theme, version
from .widgets import status_badge

# ------------------------------------------------------------------ 常量

FLOAT_W = 344           # 面板固定宽度（参考图那种窄长条）
SNAP_PX = 28            # 靠边吸附的触发距离（距屏幕边缘多少像素内就吸上去）
PEEK = 8                # 贴边收起后留在屏幕内的宽度
SCREEN_PAD = 14         # 首次出现时与屏幕边缘的留白
TITLE_H = 26            # 拖动手柄区（小圆点）尺寸

# 内容块登记表：顺序即面板里的纵向顺序
BLOCKS: List[Tuple[str, str]] = [
    ("clock", "日期时钟"),
    ("stats", "证书状态"),
    ("expiring", "最近到期"),
    ("exams", "近期考试"),
    ("categories", "分类分布"),
    ("materials", "学习资料"),
    ("tip", "今日提示"),
]
BLOCK_LABEL: Dict[str, str] = dict(BLOCKS)
DEFAULT_BLOCKS = "clock,stats,expiring,exams"

_EMPTY_BLOCKS_HINT = "未选择任何内容   ·   右键可切换"


# ------------------------------------------------------------------ 小工具


def _tint(color: str, alpha: int) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


def _elide(text: str, px: int) -> str:
    return QFontMetrics(QApplication.font()).elidedText(text, Qt.ElideRight, px)


def _empty(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("FloatEmpty")
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


def _show_deep(w: QWidget) -> None:
    """把新建的子控件树显式 show 出来（连同后代）。

    ★ 这是本模块最隐蔽的一个坑：``QLayout::addChildWidget()`` 对「刚 addWidget 进来的
      控件」只是发了一个 **queued** 的 ``_q_showIfNotHidden``，也就是说控件要等下一轮
      事件循环才真正可见。而 ``QWidgetItem::isEmpty()`` 会把「隐藏的控件」当空项跳过 ——
      于是在这一瞬间读尺寸提示，那些控件对布局的贡献是 **0**，而这个 0 会被
      ``QBoxLayout`` 当作结果缓存下来（dirty 已清）。表现就是：
      「第一次构造尺寸正常；之后每刷新一次内容，面板高度就塌成只剩标题」，
      刷新两次又对得上，看起来像随机跳。
      显式 show 一次就彻底断掉这条链 —— 同步、确定、不依赖事件循环。
    """
    w.show()
    for c in w.findChildren(QWidget):
        c.show()


def _clear_layout(lay) -> None:
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _rule() -> QFrame:
    f = QFrame()
    f.setObjectName("FloatRule")
    f.setFixedHeight(1)
    return f


def _dot(color: str) -> QLabel:
    d = QLabel()
    d.setFixedSize(6, 6)
    d.setStyleSheet(f"background:{color}; border-radius:3px;")
    return d


def _row(name: str, color: str, badge: Optional[QWidget], meta: str,
         meta_color: str = "", name_px: int = 118) -> QWidget:
    """列表行：状态点 + 名称 + 徽章 + 右侧数值。"""
    w = QWidget()
    h = QHBoxLayout(w)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    h.addWidget(_dot(color))
    lbl = QLabel(_elide(name, name_px))
    lbl.setObjectName("FloatRowName")
    h.addWidget(lbl, 1)
    if badge is not None:
        h.addWidget(badge)
    if meta:
        m = QLabel(meta)
        m.setObjectName("FloatRowMeta")
        if meta_color:
            m.setStyleSheet(f"color:{meta_color};")
        h.addWidget(m)
    return w


def _head_row(title: str) -> QWidget:
    """分区块的小标题行：主色竖条 + 标题 + 一条细横线。

    ★ 必须先把布局挂到容器控件上（``QHBoxLayout(holder)``），再往里 addWidget。
      反过来写（先建裸布局、加完控件、最后 ``addWidget(holder)`` 或 ``addLayout``）
      会让那些控件在加入时**没有父控件**，而「无父控件的 QWidget 就是一个顶层窗口」，
      于是 ``QWidgetItem::isEmpty()`` 判它为空 → 整行对布局的尺寸贡献为 0，
      表现为「块高度只剩标题 / 面板高度忽大忽小」。这个坑非常安静：
      目视一切正常，只有尺寸算错。
    """
    holder = QWidget()
    h = QHBoxLayout(holder)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    bar = QFrame()
    bar.setFixedSize(3, 11)
    bar.setStyleSheet(f"background:{theme.PRIMARY}; border-radius:1px;")
    h.addWidget(bar)
    lbl = QLabel(title)
    lbl.setObjectName("FloatBlockTitle")
    h.addWidget(lbl)
    h.addWidget(_rule(), 1)
    return holder


# ------------------------------------------------------------------ 拖动转发


class _DragArea:
    """把鼠标拖动 / 双击 / 右键转发给所属悬浮窗的混入。

    悬浮窗的头部、内容层都是独立控件，事件不会冒泡到顶层窗口，所以要显式转发。
    用混入而不是给每个类重复写一遍：``class FloatHeader(_DragArea, QFrame)``，
    这样 ``super()`` 会沿 MRO 落到 QFrame，原始实现照样跑。
    """

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and hasattr(self.window(), "begin_drag"):
            self.window().begin_drag(e.globalPosition().toPoint())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        w = self.window()
        if getattr(w, "_dragging", False):
            w.drag_to(e.globalPosition().toPoint())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        w = self.window()
        if getattr(w, "_dragging", False):
            w.end_drag()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and hasattr(self.window(), "toggle_roll"):
            self.window().toggle_roll()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):  # noqa: N802
        w = self.window()
        if hasattr(w, "popup_menu"):
            w.popup_menu(e.globalPos())
            e.accept()
            return
        super().contextMenuEvent(e)


# ------------------------------------------------------------------ 内容块


class Block(QFrame):
    """浮窗里的一块内容：小标题 + 内容区。内容每次 refresh 整体重建。

    之所以整块重建而不是「就地改文字」：块内行数随数据变化（0～N 行），
    就地改要处理增删行的分支，比重建更容易出错；重建的代价只是十几个小控件。
    """

    KEY = ""
    TITLE = ""

    def __init__(self, database: dbm.Database, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.setObjectName("FloatBlock")
        v = QVBoxLayout(self)
        v.setContentsMargins(9, 7, 9, 9)
        v.setSpacing(7)
        v.addWidget(_head_row(self.TITLE))

        self.body = QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(5)
        v.addLayout(self.body)
        self.refresh()

    def refresh(self) -> None:
        _clear_layout(self.body)
        try:
            self.fill()
        except Exception:  # noqa: BLE001
            self.body.addWidget(_empty("读取失败"))
        # 新建的控件此刻还是隐藏状态（Qt 的 show 是 queued 的），先显式 show 再量尺寸，
        # 否则本块对布局的贡献会被算成 0（详见 _show_deep 的说明）。
        for i in range(self.body.count()):
            it = self.body.itemAt(i)
            w = it.widget()
            if w is not None:
                _show_deep(w)
        self.layout().activate()

    def fill(self) -> None:  # pragma: no cover - 子类实现
        raise NotImplementedError

    def tick(self) -> None:
        """秒级刷新钩子：只有需要走时的块才覆写。"""


class ClockBlock(Block):
    """日期时钟：大字日期 + 星期 + 时钟。"""

    KEY, TITLE = "clock", "日期时钟"

    WEEK = "一二三四五六日"

    def fill(self) -> None:
        self._big = QLabel()
        self._big.setObjectName("FloatBigDate")
        self._week = QLabel()
        self._week.setObjectName("FloatWeek")
        self._time = QLabel()
        self._time.setObjectName("FloatTime")
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        rl.addWidget(self._week, 1)
        rl.addWidget(self._time)
        self.body.addWidget(self._big)
        self.body.addWidget(row)
        self.tick()

    def tick(self) -> None:
        big = getattr(self, "_big", None)
        if big is None:
            return
        now = datetime.now()
        big.setText(f"{now.year} 年 {now.month} 月 {now.day} 日")
        self._week.setText(f"星期{self.WEEK[now.weekday()]}")
        self._time.setText(now.strftime("%H:%M"))


class StatsBlock(Block):
    """证书状态四宫格。"""

    KEY, TITLE = "stats", "证书状态"

    CELLS = [("总数", "total", theme.PRIMARY),
             ("有效", "valid", theme.SUCCESS),
             ("即将到期", "soon", theme.WARN),
             ("已过期", "expired", theme.DANGER)]

    def fill(self) -> None:
        st = self.db.certificate_stats()
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (label, key, color) in enumerate(self.CELLS):
            cell = QFrame()
            cell.setObjectName("FloatStat")
            cell.setStyleSheet(
                f"#FloatStat {{ background:{_tint(color, 26)};"
                f" border:1px solid {_tint(color, 72)}; border-radius:9px; }}")
            cv = QVBoxLayout(cell)
            cv.setContentsMargins(6, 6, 6, 6)
            cv.setSpacing(0)
            num = QLabel(str(st.get(key, 0)))
            num.setObjectName("FloatStatNum")
            num.setStyleSheet(f"color:{color};")
            num.setAlignment(Qt.AlignCenter)
            cap = QLabel(label)
            cap.setObjectName("FloatStatLabel")
            cap.setAlignment(Qt.AlignCenter)
            cv.addWidget(num)
            cv.addWidget(cap)
            grid.addWidget(cell, i // 2, i % 2)
        self.body.addWidget(holder)


class ExpiringBlock(Block):
    """最近到期清单（条数由设置 float_max_rows 决定）。"""

    KEY, TITLE = "expiring", "最近到期"

    def fill(self) -> None:
        rows = self.db.expiring()
        limit = self.db.get_setting("float_max_rows", "5")
        try:
            limit = max(1, min(12, int(limit)))
        except (TypeError, ValueError):
            limit = 5
        if not rows:
            self.body.addWidget(_empty("暂无到期证书"))
            return
        for r in rows[:limit]:
            color = theme.status_color(r["status_key"])
            self.body.addWidget(_row(r["name"], color,
                                     status_badge(r["status_key"]),
                                     r["left_text"], color, name_px=148))
        if len(rows) > limit:
            more = QLabel(f"另有 {len(rows) - limit} 本待关注")
            more.setObjectName("FloatEmpty")
            self.body.addWidget(more)


class ExamBlock(Block):
    """近期考试倒计时。"""

    KEY, TITLE = "exams", "近期考试"

    def fill(self) -> None:
        limit = 4
        rows = self.db.upcoming_exams(limit)
        if not rows:
            self.body.addWidget(_empty("暂无近期考试"))
            return
        for r in rows:
            left = r.get("days_left")
            color = theme.DANGER if (left is not None and left <= 7) else theme.PRIMARY
            meta = "今天" if left == 0 else f"{left} 天"
            self.body.addWidget(_row(r["name"], color, None, meta, color,
                                     name_px=215))


class CategoryBlock(Block):
    """分类分布：迷你横条 + 计数。"""

    KEY, TITLE = "categories", "分类分布"

    def fill(self) -> None:
        rows = self.db.category_stats()[:5]
        if not rows:
            self.body.addWidget(_empty("暂无分类统计"))
            return
        top = max(r["total"] for r in rows) or 1
        for r in rows:
            line = QWidget()
            h = QHBoxLayout(line)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(7)
            name = QLabel(_elide(r["name"], 68))
            name.setObjectName("FloatRowName")
            name.setFixedWidth(68)
            h.addWidget(name)
            bar = QProgressBar()
            bar.setObjectName("FloatBar")
            bar.setTextVisible(False)
            bar.setFixedHeight(8)
            bar.setRange(0, top)
            bar.setValue(int(r["total"]))
            bar.setStyleSheet(
                f"QProgressBar#FloatBar {{ background:{theme.NEUTRAL_SOFT};"
                f" border:none; border-radius:4px; }}"
                f"QProgressBar#FloatBar::chunk {{ background:{r['color']};"
                f" border-radius:4px; }}")
            h.addWidget(bar, 1)
            num = QLabel(str(r["total"]))
            num.setObjectName("FloatRowMeta")
            h.addWidget(num)
            self.body.addWidget(line)


class MaterialBlock(Block):
    """学习资料：按分类排成小胶囊。"""

    KEY, TITLE = "materials", "学习资料"

    def fill(self) -> None:
        stats = self.db.material_stats()
        if not stats:
            self.body.addWidget(_empty("暂无学习资料"))
            return
        items = [("全部", sum(stats.values()))]
        items += sorted(stats.items(), key=lambda kv: (-kv[1], kv[0]))
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(5)
        grid.setContentsMargins(0, 0, 0, 0)
        for i, (name, n) in enumerate(items[:6]):
            chip = QLabel(f"{_elide(name, 62)}   {n}")
            chip.setObjectName("FloatChipCat")
            grid.addWidget(chip, i // 2, i % 2)
        self.body.addWidget(holder)


class TipBlock(Block):
    """今日提示：一句话说清「现在最该干什么」。"""

    KEY, TITLE = "tip", "今日提示"

    def fill(self) -> None:
        rows = self.db.expiring()
        if not rows:
            text = "全部证书均在有效期内，暂时没有需要处理的到期项。"
        else:
            top = rows[0]
            text = f"《{top['name']}》{top['left_text']}，建议优先处理。"
            rest = len(rows) - 1
            if rest > 0:
                text += f"另有 {rest} 本待关注。"
        lbl = QLabel(text)
        lbl.setObjectName("FloatTipText")
        lbl.setWordWrap(True)
        self.body.addWidget(lbl)


BLOCK_CLASSES: Dict[str, type] = {c.KEY: c for c in
                                  (ClockBlock, StatsBlock, ExpiringBlock,
                                   ExamBlock, CategoryBlock, MaterialBlock,
                                   TipBlock)}


# ------------------------------------------------------------------ 控件


class _FloatIconBtn(QPushButton):
    """浮窗里的图标按钮：悬停换色，关闭按钮悬停染红底白字。"""

    def __init__(self, icon_name: str, tip: str, color: str = theme.TEXT_SUB,
                 size: int = 15, danger: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("FloatClose" if danger else "FloatIcon")
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setIconSize(QSize(size, size))
        self.setToolTip(tip)
        self._name = icon_name
        self._color = color
        self._danger = danger
        self._size = size
        self._apply()

    def set_icon_name(self, name: str) -> None:
        self._name = name
        self._apply()

    def set_colored(self, color: str) -> None:
        self._color = color
        self._apply()

    def _apply(self) -> None:
        hover = self.underMouse() or self.isDown()
        if hover and self._danger:
            color = "#ffffff"
        elif hover:
            color = theme.TEXT
        else:
            color = self._color
        self.setIcon(icons.icon(self._name, color, self._size))

    def enterEvent(self, e):  # noqa: N802
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._apply()
        super().leaveEvent(e)


class FloatHeader(_DragArea, QFrame):
    """浮窗头部：既是标题栏（拖动 / 双击收起），又承载图标按钮。"""


class FloatInner(_DragArea, QWidget):
    """内容层：块之间的空白也能拖动窗口、也能弹右键菜单。"""


class FloatWindow(QWidget):
    """桌面常驻的证书速览悬浮窗。"""

    open_main = Signal()
    open_reminders = Signal()
    settings_requested = Signal()
    visibility_changed = Signal(bool)

    def __init__(self, database: dbm.Database,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.setObjectName("FloatRoot")
        self.setWindowTitle(f"{version.APP_NAME} · 悬浮窗")
        self.setWindowIcon(icons.app_icon())
        self.setStyleSheet(theme.QSS + theme.FLOAT_QSS)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint)
        # 半透明底：四个圆角外的区域交给桌面，圆角由 paintEvent 自绘
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 弹出来时不抢焦点（悬浮窗该有的脾气）
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedWidth(FLOAT_W)

        # 拖动 / 吸附状态
        self._dragging = False
        self._drag_off = QPoint()
        self._drag_pos = QPoint()
        self._rest = QPoint()
        self._docked: Optional[str] = None
        self._slid = False
        self._snap_preview: Optional[str] = None
        self._rolled = False

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._maybe_slide_out)

        self._clock_timer = QTimer(self)
        self._clock_timer.setInterval(15000)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start()

        self.blocks: List[str] = self._load_blocks()
        self.always_top = self.db.get_setting("float_top", "1") == "1"
        self.autohide = self.db.get_setting("float_autohide", "0") == "1"

        self._build()
        self._apply_blocks()
        self._icon_top()
        self._place_initial()
        self.refresh()

    # ------------------------------------------------------------ 构建
    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)   # 让出 1px 描边，别盖住
        root.setSpacing(0)
        root.addWidget(self._build_header())

        inner = FloatInner()
        inner.setObjectName("FloatInner")
        inner.setContextMenuPolicy(Qt.DefaultContextMenu)
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(10, 9, 10, 10)
        iv.setSpacing(8)
        self._block_widgets: Dict[str, Block] = {}
        for key, _label in BLOCKS:
            b = BLOCK_CLASSES[key](self.db)
            iv.addWidget(b)
            self._block_widgets[key] = b
        self._none = _empty(_EMPTY_BLOCKS_HINT)
        self._none.setContentsMargins(0, 18, 0, 18)
        iv.addWidget(self._none)
        iv.addStretch(1)

        self._scroll = QScrollArea()
        self._scroll.setObjectName("FloatBody")
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setWidget(inner)
        self._scroll.viewport().setStyleSheet("background: transparent;")
        root.addWidget(self._scroll, 1)
        root.addWidget(self._build_footer())
        self._sync_size()

    def _build_header(self) -> QWidget:
        head = FloatHeader()
        head.setObjectName("FloatHeader")
        h = QHBoxLayout(head)
        h.setContentsMargins(10, 7, 7, 7)
        h.setSpacing(8)

        logo = QLabel()
        logo.setPixmap(icons.logo_pixmap(26, 2.0))
        logo.setFixedSize(26, 26)
        h.addWidget(logo)

        col = QWidget()
        cl = QVBoxLayout(col)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self.lbl_name = QLabel(version.APP_NAME)
        self.lbl_name.setObjectName("FloatName")
        self.lbl_meta = QLabel(version.FULL_VERSION)
        self.lbl_meta.setObjectName("FloatMeta")
        cl.addWidget(self.lbl_name)
        cl.addWidget(self.lbl_meta)
        h.addWidget(col)
        h.addStretch(1)

        self.lbl_chip = QLabel("")
        self.lbl_chip.setObjectName("FloatChip")
        h.addWidget(self.lbl_chip)

        grip = QLabel()
        grip.setPixmap(icons.pixmap("grip", "#c3cede", 14))
        grip.setFixedSize(14, TITLE_H)
        grip.setToolTip("按住此处拖动面板")
        h.addWidget(grip)

        self.btn_top = _FloatIconBtn("ontop", "始终置顶")
        self.btn_roll = _FloatIconBtn("chevron-up", "收起内容")
        self.btn_close = _FloatIconBtn("close", "关闭悬浮窗", danger=True)
        self.btn_top.clicked.connect(self.toggle_top)
        self.btn_roll.clicked.connect(self.toggle_roll)
        self.btn_close.clicked.connect(self.hide_window)
        for b in (self.btn_top, self.btn_roll, self.btn_close):
            h.addWidget(b)
        return head

    def _build_footer(self) -> QWidget:
        foot = QFrame()
        foot.setObjectName("FloatFoot")
        v = QVBoxLayout(foot)
        v.setContentsMargins(10, 7, 10, 9)
        v.setSpacing(5)

        copy = QLabel(f"{version.COPYRIGHT}   {version.LICENSE_LINE}")
        copy.setObjectName("FloatCopy")
        copy.setWordWrap(True)
        copy.setAlignment(Qt.AlignCenter)
        v.addWidget(copy)

        hint = QLabel("拖动顶部移动  ·  靠边自动吸附  ·  右键切换内容")
        hint.setObjectName("FloatHint")
        hint.setAlignment(Qt.AlignCenter)
        v.addWidget(hint)

        self._btn_main = QPushButton("主窗口")
        self._btn_bell = QPushButton("到期提醒")
        self._btn_cfg = QPushButton("内容…")
        for b, ic in ((self._btn_main, "open"), (self._btn_bell, "bell"),
                      (self._btn_cfg, "settings")):
            b.setObjectName("FloatBtn")
            b.setCursor(Qt.PointingHandCursor)
            b.setIcon(icons.icon(ic, theme.TEXT_SUB, 14))
            b.setIconSize(QSize(14, 14))
        self._btn_main.clicked.connect(self.open_main.emit)
        self._btn_bell.clicked.connect(self.open_reminders.emit)
        self._btn_cfg.clicked.connect(self.settings_requested.emit)
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(6)
        for b in (self._btn_main, self._btn_bell, self._btn_cfg):
            rl.addWidget(b, 1)
        v.addWidget(row)
        return foot

    # ------------------------------------------------------------ 尺寸
    def _sync_size(self) -> None:
        """面板宽度固定，高度贴内容（上限为屏幕可用高度 - 80）。"""
        if self._rolled:
            self._scroll.setVisible(False)
            self._scroll.setFixedHeight(0)
        else:
            self._scroll.setVisible(True)
            inner = self._scroll.widget()
            # 先让内容层的布局落定再问它要尺寸提示。
            # 直接用 sizeHint() 会读到上一次的缓存值 —— 面板高度就会
            # 「改了两块内容，尺寸还是旧的」，甚至忽大忽小。
            lay = inner.layout()
            if lay is not None:
                lay.activate()
            need = inner.sizeHint().height() + 2
            avail = max(220, self._available().height() - 80)
            self._scroll.setFixedHeight(min(need, avail))
        self.layout().activate()
        self.setFixedSize(FLOAT_W, self.layout().sizeHint().height())
        # 固定尺寸后重新贴住停靠边，否则改高度会把面板顶进屏幕外
        if self._rest.isNull():
            self._place_initial()
        else:
            self._rest = self._clamp(self._rest.x(), self._rest.y())
            self.move(self._rest if not self._slid else self.pos())

    def _available(self) -> QRect:
        scr = self.screen() or QApplication.primaryScreen()
        return scr.availableGeometry()

    def _clamp(self, x: int, y: int) -> QPoint:
        g = self._available()
        x = max(g.left(), min(int(x), g.right() + 1 - self.width()))
        y = max(g.top(), min(int(y), g.bottom() + 1 - self.height()))
        return QPoint(x, y)

    def _visible_enough(self, p: QPoint) -> bool:
        r = QRect(p, self.size())
        for scr in QApplication.screens():
            if scr.availableGeometry().intersected(r).width() >= 60 \
                    and scr.availableGeometry().intersected(r).height() >= 60:
                return True
        return False

    def _place_initial(self) -> None:
        """恢复上次位置；没有记录或落到屏幕外，则贴屏幕右侧 1/5 处。"""
        x: Optional[int] = None
        y: Optional[int] = None
        try:
            sx = self.db.get_setting("float_x", "")
            sy = self.db.get_setting("float_y", "")
            if sx and sy:
                x, y = int(sx), int(sy)
        except (TypeError, ValueError):
            x = y = None
        if x is None or y is None or not self._visible_enough(QPoint(x, y)):
            g = self._available()
            x = g.right() + 1 - self.width() - SCREEN_PAD
            y = g.top() + max(60, int(g.height() * 0.18))
        self._rest = self._clamp(x, y)
        self.move(self._rest)

    # ------------------------------------------------------------ 拖动吸附
    def begin_drag(self, gp: QPoint) -> None:
        self._anim.stop()
        if self._slid:
            self._slide_in(instant=True)
        self._dragging = True
        self._drag_off = gp - self.pos()
        self._drag_pos = QPoint(self.pos())

    def drag_to(self, gp: QPoint) -> None:
        if not self._dragging:
            return
        self._drag_pos = gp - self._drag_off
        x, y = self._snapped(self._drag_pos.x(), self._drag_pos.y())
        self._snap_preview = self._edge_of(self._drag_pos.x(), self._drag_pos.y())
        self.move(x, y)
        self.update()

    def end_drag(self) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self._snap_preview = None
        x, y = self._snapped(self._drag_pos.x(), self._drag_pos.y())
        self._rest = QPoint(x, y)
        self.move(self._rest)
        self._docked = self._dock_side(x, y)
        self._save_pos()
        if self.autohide and self._docked:
            self._slide_out()
        else:
            self.update()

    def _snapped(self, x: int, y: int) -> Tuple[int, int]:
        """把坐标吸到屏幕边缘：进了吸附范围就完全贴边，否则只做边界夹取。"""
        g = self._available()
        w, h = self.width(), self.height()
        if x - g.left() <= SNAP_PX:
            x = g.left()
        elif (g.right() + 1) - (x + w) <= SNAP_PX:
            x = g.right() + 1 - w
        if y - g.top() <= SNAP_PX:
            y = g.top()
        elif (g.bottom() + 1) - (y + h) <= SNAP_PX:
            y = g.bottom() + 1 - h
        x = max(g.left(), min(x, g.right() + 1 - w))
        y = max(g.top(), min(y, g.bottom() + 1 - h))
        return x, y

    def _edge_of(self, x: int, y: int) -> Optional[str]:
        g = self._available()
        w = self.width()
        if x - g.left() <= SNAP_PX:
            return "left"
        if (g.right() + 1) - (x + w) <= SNAP_PX:
            return "right"
        return None

    def _dock_side(self, x: int, y: int) -> Optional[str]:
        g = self._available()
        w = self.width()
        if x <= g.left():
            return "left"
        if x + w >= g.right() + 1:
            return "right"
        return None

    def _save_pos(self) -> None:
        self.db.set_setting("float_x", str(self._rest.x()))
        self.db.set_setting("float_y", str(self._rest.y()))

    # ------------------------------------------------------------ 贴边收起
    def _slide_out(self) -> None:
        if not self._docked:
            return
        g = self._available()
        w = self.width()
        if self._docked == "left":
            target = QPoint(g.left() - w + PEEK, self._rest.y())
        else:
            target = QPoint(g.right() + 1 - PEEK, self._rest.y())
        self._slid = True
        self._animate(target)

    def _slide_in(self, instant: bool = False) -> None:
        self._slid = False
        if instant:
            self.move(self._rest)
            self.update()
            return
        self._animate(self._rest)

    def _animate(self, target: QPoint) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.start()
        self.update()

    def _maybe_slide_out(self) -> None:
        if not self.autohide or not self._docked or self._dragging:
            return
        if self.rect().contains(self.mapFromGlobal(QCursor.pos())):
            return          # 光标还在面板上（可能只是掠过了某个子控件）
        self._slide_out()

    # ------------------------------------------------------------ 事件
    def enterEvent(self, e):  # noqa: N802
        self._hide_timer.stop()
        if self._slid and self._docked:
            self._slide_in()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        super().leaveEvent(e)
        # ★ 顶层控件的 leaveEvent 在「移入子控件」时也会来一发，
        #   所以这里只起一个延迟判定，真正决定收起的是 _maybe_slide_out。
        if self.autohide and self._docked and not self._dragging:
            self._hide_timer.start(320)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.begin_drag(e.globalPosition().toPoint())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._dragging:
            self.drag_to(e.globalPosition().toPoint())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._dragging:
            self.end_drag()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            self.toggle_roll()
            e.accept()
            return
        super().mouseDoubleClickEvent(e)

    def contextMenuEvent(self, e):  # noqa: N802
        self.popup_menu(e.globalPos())
        e.accept()

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 13.0, 13.0)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.CARD))
        p.drawPath(path)
        pen = QPen(QColor(theme.BORDER_STRONG))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 13.0, 13.0)

        # 拖动中：把「会吸到哪条边」画出来（贴边处一道 3px 主色条）
        if self._snap_preview:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(_tint(theme.PRIMARY, 190)))
            if self._snap_preview == "left":
                p.drawRoundedRect(QRectF(r.x() + 0.5, r.y() + 8, 3.0, r.height() - 16),
                                  1.5, 1.5)
            else:
                p.drawRoundedRect(QRectF(r.right() - 3.5, r.y() + 8, 3.0,
                                          r.height() - 16), 1.5, 1.5)
        # 贴边收起态：在露出来的那条窄边上画一个把手，暗示「可以拉回来」
        if self._slid and self._docked:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#b7c3d2"))
            hx = 3.0 if self._docked == "right" else w - 6.0
            p.drawRoundedRect(QRectF(hx, h / 2 - 16, 3.0, 32.0), 1.5, 1.5)
        p.end()

    # ------------------------------------------------------------ 菜单与开关
    def popup_menu(self, gp: QPoint) -> None:
        m = QMenu(self)
        m.addAction("立即刷新").triggered.connect(self.refresh)
        m.addSeparator()
        for key, label in BLOCKS:
            act = m.addAction(label)
            act.setCheckable(True)
            act.setChecked(key in self.blocks)
            act.toggled.connect(lambda on, k=key: self.set_block(k, on))
        m.addSeparator()
        for label, attr in (("始终置顶", "always_top"), ("贴边自动收起", "autohide")):
            act = m.addAction(label)
            act.setCheckable(True)
            act.setChecked(bool(getattr(self, attr)))
            act.toggled.connect(lambda on, a=attr: self.set_option(a, on))
        m.addSeparator()
        m.addAction("内容设置…").triggered.connect(self.settings_requested.emit)
        m.addAction("隐藏悬浮窗").triggered.connect(self.hide_window)
        m.exec(gp)

    def _load_blocks(self) -> List[str]:
        raw = self.db.get_setting("float_blocks", DEFAULT_BLOCKS) or DEFAULT_BLOCKS
        chosen = {s.strip() for s in raw.split(",")}
        order = [k for k, _ in BLOCKS if k in chosen]
        return order or DEFAULT_BLOCKS.split(",")

    def set_block(self, key: str, on: bool) -> None:
        if key not in BLOCK_LABEL:
            return
        cur = set(self.blocks)
        cur.add(key) if on else cur.discard(key)
        self.blocks = [k for k, _ in BLOCKS if k in cur]
        self.db.set_setting("float_blocks", ",".join(self.blocks))
        self._apply_blocks()

    def _apply_blocks(self) -> None:
        prev = getattr(self, "_shown", set())
        for key, w in self._block_widgets.items():
            on = key in self.blocks
            # 从「关」变「开」时补一次刷新，否则会停在上次的数据上。
            # 用自己记的开关状态判断，不用 isVisible() —— 窗口整体隐藏时
            # 所有子控件的 isVisible() 都是 False，会白刷一轮。
            if on and key not in prev:
                w.refresh()
            w.setVisible(on)
        self._shown = set(self.blocks)
        self._none.setVisible(not self.blocks)
        self._sync_size()
        self._docked = self._dock_side(self._rest.x(), self._rest.y())
        if self._slid:
            self._slide_in(instant=True)

    def set_option(self, attr: str, on: bool) -> None:
        setattr(self, attr, bool(on))
        key = "float_top" if attr == "always_top" else "float_autohide"
        self.db.set_setting(key, "1" if on else "0")
        if attr == "always_top":
            self._apply_top()
        else:
            self._hide_timer.stop()
            if not on and self._slid:
                self._slide_in()
        self._icon_top()

    def toggle_top(self) -> None:
        self.set_option("always_top", not self.always_top)

    def _apply_top(self) -> None:
        flags = self.windowFlags()
        flags |= Qt.Tool | Qt.FramelessWindowHint
        if self.always_top:
            flags |= Qt.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowStaysOnTopHint
        was = self.isVisible()
        self.setWindowFlags(flags)   # 改 flags 会隐藏窗口，可见时得补一次 show
        if was:
            self.show()
            self.raise_()

    def _icon_top(self) -> None:
        self.btn_top.set_colored(theme.PRIMARY if self.always_top else theme.TEXT_SUB)
        self.btn_top.setToolTip("取消置顶" if self.always_top else "始终置顶")

    def toggle_roll(self) -> None:
        self._rolled = not self._rolled
        self.btn_roll.set_icon_name("chevron-down" if self._rolled else "chevron-up")
        self.btn_roll.setToolTip("展开内容" if self._rolled else "收起内容")
        self._sync_size()

    # ------------------------------------------------------------ 显隐
    def reload_settings(self) -> None:
        """从设置里重新读取全部悬浮窗选项并落到位（设置面板保存后调用）。

        设置面板与右键菜单是两条改配置的路径，但都只往数据库写，
        最终由这里统一读取生效 —— 只有一个「读」的入口，就不会出现两边不一致。
        """
        self.blocks = self._load_blocks()
        self.always_top = self.db.get_setting("float_top", "1") == "1"
        self.autohide = self.db.get_setting("float_autohide", "0") == "1"
        self._hide_timer.stop()
        if not self.autohide:
            self._slid = False
            self.move(self._rest)
        self._apply_top()
        self._icon_top()
        self._apply_blocks()
        self.refresh()

    def show_window(self) -> None:
        self.db.set_setting("float_on", "1")
        self._place_initial()
        self.refresh()
        self.show()
        self.raise_()
        self._docked = self._dock_side(self._rest.x(), self._rest.y())
        if self.autohide and self._docked:
            QTimer.singleShot(1200, self._slide_out)
        self.visibility_changed.emit(True)

    def hide_window(self) -> None:
        self.db.set_setting("float_on", "0")
        self._anim.stop()
        self._hide_timer.stop()
        self._slid = False
        self._save_pos()
        self.hide()
        self.visibility_changed.emit(False)

    def closeEvent(self, e):  # noqa: N802
        self._save_pos()
        e.accept()

    # ------------------------------------------------------------ 数据
    def refresh(self) -> None:
        try:
            st = self.db.certificate_stats()
            n = len(self.db.expiring())
        except Exception:  # noqa: BLE001
            return
        self.lbl_meta.setText(f"{version.FULL_VERSION}   证书 {st['total']} 本")
        if n:
            self.lbl_chip.setText(f"待关注 {n}")
            self.lbl_chip.setObjectName("FloatChipAlert")
        else:
            self.lbl_chip.setText("全部有效")
            self.lbl_chip.setObjectName("FloatChip")
        # 换了 objectName 必须重新 polish，否则样式表里那条规则不会重新匹配
        self.lbl_chip.style().unpolish(self.lbl_chip)
        self.lbl_chip.style().polish(self.lbl_chip)
        for key in self.blocks:
            w = self._block_widgets.get(key)
            if w is not None:
                w.refresh()
        self._sync_size()

    def _tick_clock(self) -> None:
        w = self._block_widgets.get("clock")
        if w is not None and w.isVisible():
            w.tick()
