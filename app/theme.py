# -*- coding: utf-8 -*-
"""视觉主题：档案馆风格的浅色内容区 + 深色侧边栏，金色作为证书语义色。"""

from __future__ import annotations

# ---- 调色板 ---------------------------------------------------------------
BG = "#f3f5f9"
CARD = "#ffffff"
BORDER = "#e3e8f0"
BORDER_STRONG = "#cdd7e5"
TEXT = "#1f2937"
TEXT_SUB = "#5b6b7f"
MUTED = "#8a99ab"

PRIMARY = "#2e6f9e"
PRIMARY_DARK = "#245a80"
PRIMARY_SOFT = "#e8f1f8"

SIDEBAR = "#1b2a3a"
SIDEBAR_HOVER = "#26384c"
SIDEBAR_TEXT = "#b9c6d4"
SIDEBAR_ACTIVE = "#2e6f9e"

GOLD = "#c9a227"
GOLD_SOFT = "#fbf5e3"

DANGER = "#d64545"
DANGER_SOFT = "#fdecec"
WARN = "#e08b2c"
WARN_SOFT = "#fdf3e5"
SUCCESS = "#2f9e63"
SUCCESS_SOFT = "#e9f7f0"
INFO = "#2e6f9e"
INFO_SOFT = "#e8f1f8"
NEUTRAL_SOFT = "#eef2f7"

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", sans-serif'
MONO_FAMILY = '"Consolas", "Cascadia Mono", "Courier New", monospace'

# 有效期状态 → (语义键, 中文名, 主色, 浅底色)
STATUS_STYLE = {
    "expired": ("已过期", DANGER, DANGER_SOFT),
    "urgent": ("紧急", "#e0622c", "#fdeee6"),
    "soon": ("即将到期", WARN, WARN_SOFT),
    "valid": ("有效", SUCCESS, SUCCESS_SOFT),
    "permanent": ("长期有效", INFO, INFO_SOFT),
}


def status_color(key: str) -> str:
    return STATUS_STYLE.get(key, STATUS_STYLE["valid"])[1]


def status_label(key: str) -> str:
    return STATUS_STYLE.get(key, STATUS_STYLE["valid"])[0]


def status_bg(key: str) -> str:
    return STATUS_STYLE.get(key, STATUS_STYLE["valid"])[2]


QSS = f"""
* {{
    font-family: {FONT_FAMILY};
    font-size: 13px;
    outline: none;
}}

QWidget#Root, QStackedWidget#Pages, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {BG};
}}

/* ---------------------------------------------------------------- 侧边栏 */
QWidget#Sidebar {{
    background: {SIDEBAR};
    border: none;
}}
QLabel#BrandTitle {{
    color: #ffffff;
    font-size: 17px;
    font-weight: 700;
    letter-spacing: 1px;
}}
QLabel#BrandSub {{
    color: #7d8fa3;
    font-size: 10px;
    letter-spacing: 2px;
}}
QLabel#BrandVer {{
    color: #6c7f94;
    font-size: 11px;
    font-family: {MONO_FAMILY};
}}
QFrame#BrandLine {{
    background: #2c3f54;
    max-height: 1px;
    border: none;
}}
QPushButton#NavBtn {{
    color: {SIDEBAR_TEXT};
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 0 12px;
    text-align: left;
    font-size: 14px;
    min-height: 42px;
}}
QPushButton#NavBtn:hover {{
    background: {SIDEBAR_HOVER};
    color: #ffffff;
}}
QPushButton#NavBtn:checked {{
    background: {SIDEBAR_ACTIVE};
    color: #ffffff;
    font-weight: 600;
}}
QLabel#SidebarFoot {{
    color: #5d6f83;
    font-size: 10px;
}}

/* ------------------------------------------------------------------ 顶栏 */
QWidget#TopBar {{
    background: {CARD};
    border-bottom: 1px solid {BORDER};
}}
QFrame#TitleSep {{
    background: {BORDER};
    border: none;
}}
QLabel#PageTitle {{
    font-size: 20px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#PageSub {{
    font-size: 12px;
    color: {MUTED};
}}
/* 无边框窗口的系统按钮（最小化 / 最大化 / 关闭），并入顶栏右上角 */
QPushButton#WinBtn {{
    background: transparent;
    border: none;
    border-radius: 7px;
    padding: 0;
    min-width: 34px;  max-width: 34px;
    min-height: 30px; max-height: 30px;
}}
QPushButton#WinBtn:hover {{ background: #e8eef5; }}
QPushButton#WinBtn:pressed {{ background: #dae3ee; }}
QPushButton#WinClose:hover {{ background: {DANGER}; }}
QPushButton#WinClose:pressed {{ background: #b93a3a; }}
QLabel#BellCount {{
    background: {DANGER};
    color: #ffffff;
    border-radius: 9px;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 5px;
}}

/* ------------------------------------------------------------- 通用控件 */
QFrame#Card {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#CardTitle {{
    font-size: 14px;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#CardHint {{
    font-size: 12px;
    color: {MUTED};
}}
QLabel#Field {{
    color: {TEXT};
    font-size: 13px;
}}
QLabel#Muted {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#BigNum {{
    font-size: 28px;
    font-weight: 700;
}}
QLabel#StatLabel {{
    color: {TEXT_SUB};
    font-size: 12px;
}}
QLabel#SectionLabel {{
    color: {TEXT};
    font-size: 14px;
    font-weight: 700;
}}
QLabel#EmptyTitle {{
    color: {TEXT_SUB};
    font-size: 15px;
    font-weight: 600;
}}
QLabel#EmptyHint {{
    color: {MUTED};
    font-size: 12px;
}}

/* -------------------------------------------------------------- 按钮体系 */
QPushButton {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 6px 14px;
    min-height: 22px;
}}
QPushButton:hover {{
    border-color: {PRIMARY};
    color: {PRIMARY};
}}
QPushButton:pressed {{
    background: {PRIMARY_SOFT};
}}
QPushButton:disabled {{
    color: #b6c1cd;
    border-color: {BORDER};
    background: #f7f9fc;
}}
QPushButton#Primary {{
    background: {PRIMARY};
    color: #ffffff;
    border: 1px solid {PRIMARY};
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {PRIMARY_DARK};
    border-color: {PRIMARY_DARK};
    color: #ffffff;
}}
QPushButton#Gold {{
    background: {GOLD};
    color: #3a2f07;
    border: 1px solid {GOLD};
    font-weight: 600;
}}
QPushButton#Gold:hover {{
    background: #d8b23c;
    border-color: #d8b23c;
    color: #3a2f07;
}}
QPushButton#Danger {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #f3c9c9;
}}
QPushButton#Danger:hover {{
    background: {DANGER};
    color: #ffffff;
    border-color: {DANGER};
}}
QPushButton#Ghost {{
    background: transparent;
    border: none;
    color: {TEXT_SUB};
    padding: 4px 8px;
}}
QPushButton#Ghost:hover {{
    color: {PRIMARY};
    background: {PRIMARY_SOFT};
    border-radius: 6px;
}}
QPushButton#IconBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 4px;
    min-width: 32px;
    min-height: 32px;
}}
QPushButton#IconBtn:hover {{
    background: {PRIMARY_SOFT};
}}
QPushButton#FilterChip {{
    background: {NEUTRAL_SOFT};
    border: 1px solid transparent;
    border-radius: 13px;
    padding: 3px 13px;
    color: {TEXT_SUB};
    font-size: 12px;
    min-height: 20px;
}}
QPushButton#FilterChip:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
QPushButton#FilterChip:checked {{
    background: {PRIMARY};
    color: #ffffff;
    font-weight: 600;
}}

/* ------------------------------------------------------------ 输入类控件 */
QLineEdit, QPlainTextEdit, QTextEdit, QDateEdit, QSpinBox, QDoubleSpinBox {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 6px 10px;
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border: 1px solid {PRIMARY};
}}
QLineEdit:disabled, QPlainTextEdit:disabled, QDateEdit:disabled {{
    background: #f5f7fa;
    color: {MUTED};
}}
QComboBox {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 6px 10px;
    color: {TEXT};
    min-width: 90px;
}}
QComboBox:focus, QComboBox:hover {{ border-color: {PRIMARY}; }}
/* 接管 ::drop-down 只为「清空」：Windows 11 原生样式会在下拉按钮右侧画一道
   深灰色 L 形分隔装饰，它不吃样式表的圆角边框，渲染出来像右下角掉了一块。
   代价是原生 chevron 也不画了，因此箭头由 widgets.ComboBox 在 paintEvent
   里自绘（样式表不支持用纯 CSS 三角形补箭头，会变成一条横杠）。 */
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    background: transparent;
    border: none;
}}
QComboBox QAbstractItemView {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 4px;
    color: {TEXT};
    outline: none;
    /* 选中态一律由下面的 ::item 规则接管，不用调色板里的 Highlight，
       否则系统强调色（本机为紫红 #810068）会漏进来。 */
    selection-background-color: transparent;
    selection-color: {TEXT};
}}
/* 弹层每一项都必须显式写 color：系统深色模式下 Qt 默认调色板的 Text 是浅色，
   而这里若只写 background 就会变成「白字白底」，一个字都看不见。 */
QComboBox QAbstractItemView::item {{
    min-height: 26px;
    padding: 4px 10px;
    border-radius: 6px;
    background: transparent;
    color: {TEXT};
}}
QComboBox QAbstractItemView::item:hover {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
}}
QComboBox QAbstractItemView::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
}}
/* 日期框的日历按钮与下拉框同源：同样先清空原生装饰，箭头由 widgets.DateEdit 自绘。
   （width 必须与 widgets.DROPDOWN_W 一致） */
QDateEdit::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 26px;
    background: transparent;
    border: none;
}}
/* 微调框的上下按钮：清掉原生那对带边框的小方块，箭头由 widgets.SpinBox 自绘。
   （width 必须与 widgets.SPINBTN_W 一致）
   ⚠️ 千万不要在这里写 height —— Qt 样式表不认 `50%`（会当成 50px），
   两个按钮会各占 50px、互相重叠，下半区点下去反而在「加」。
   不写 height 时 Qt 会按控件高度自动对半分，实测 32px 高的框得到两个 16px 按钮。 */
QSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 24px;
    background: transparent;
    border: none;
    border-top-right-radius: 6px;
}}
QSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 24px;
    background: transparent;
    border: none;
    border-bottom-right-radius: 6px;
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background: {PRIMARY_SOFT};
}}
QCheckBox, QRadioButton {{ color: {TEXT}; spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 15px; height: 15px;
    border: 1px solid {BORDER_STRONG};
    border-radius: 4px;
    background: {CARD};
}}
QCheckBox::indicator:checked {{
    background: {PRIMARY};
    border-color: {PRIMARY};
}}
QCheckBox::indicator:hover {{ border-color: {PRIMARY}; }}
/* 日历弹层：整块接管。两个坑——
   (1) 导航条背景取的是系统强调色，深色模式下会整条变成紫红 #810068；
   (2) 全局那条 `QTableView::item {{ padding: 9px 8px }}` 会连带命中日历内部的
       日期视图（QCalendarView 是 QTableView 的子类），7 列被各吃掉 16px 后
       两位数日期、以及「周一」这种两字星期名统统被省略成「…」。
   所以这里必须把导航条、星期表头、日期单元格逐层覆盖，并把内边距归零。 */
QCalendarWidget {{
    background: {CARD};
    min-width: 300px;
    min-height: 250px;
}}
QCalendarWidget QWidget#qt_calendar_navigationbar {{
    background: {CARD};
    border: none;
    min-height: 36px;
}}
QCalendarWidget QToolButton {{
    background: transparent;
    color: {TEXT};
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    font-size: 13px;
    font-weight: 600;
}}
QCalendarWidget QToolButton:hover {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
}}
QCalendarWidget QToolButton:pressed {{ background: #dbe9f5; }}
QCalendarWidget QMenu {{ background: {CARD}; color: {TEXT}; }}
QCalendarWidget QSpinBox {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 1px 4px;
}}
/* 星期表头（周一…周日）：默认 section 内边距太宽会把两个字挤成「…」 */
QCalendarWidget QHeaderView::section {{
    background: {CARD};
    color: {TEXT_SUB};
    border: none;
    padding: 2px 0;
    font-size: 11px;
    font-weight: 600;
}}
QCalendarWidget QTableView,
QCalendarWidget QAbstractItemView {{
    background: {CARD};
    alternate-background-color: {CARD};
    border: none;
    outline: none;
    color: {TEXT};
    selection-background-color: {PRIMARY};
    selection-color: #ffffff;
    font-size: 12px;
}}
QCalendarWidget QTableView::item,
QCalendarWidget QAbstractItemView::item {{
    padding: 0;
    margin: 0;
    border: none;
    min-width: 26px;
    min-height: 22px;
    color: {TEXT};
}}
QCalendarWidget QTableView::item:selected,
QCalendarWidget QAbstractItemView::item:selected {{
    background: {PRIMARY};
    color: #ffffff;
}}
QCalendarWidget QTableView::item:disabled,
QCalendarWidget QAbstractItemView::item:disabled {{ color: #c3ccd8; }}

/* -------------------------------------------------------------- 表格视图 */
QTableWidget, QTableView {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    gridline-color: transparent;
    color: {TEXT};
    selection-background-color: {PRIMARY_SOFT};
    selection-color: {TEXT};
    alternate-background-color: #fafcfe;
}}
QTableWidget::item, QTableView::item {{
    padding: 9px 8px;
    border-bottom: 1px solid #eef2f7;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background: {PRIMARY_SOFT};
    color: {TEXT};
}}
QHeaderView::section {{
    background: #f7f9fc;
    color: {TEXT_SUB};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 9px 8px;
    font-weight: 600;
    font-size: 12px;
}}
QHeaderView::section:first {{ border-top-left-radius: 10px; }}
QHeaderView::section:last {{ border-top-right-radius: 10px; }}
QTableCornerButton::section {{ background: #f7f9fc; border: none; }}

/* ------------------------------------------------------------ 列表与标签 */
QListWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 4px;
    color: {TEXT};
    outline: none;
}}
QListWidget::item {{
    padding: 8px 10px;
    border-radius: 7px;
    color: {TEXT};
}}
QListWidget::item:hover {{ background: #f4f8fb; }}
QListWidget::item:selected {{ background: {PRIMARY_SOFT}; color: {PRIMARY}; }}

QLabel#Badge {{
    border-radius: 9px;
    padding: 2px 9px;
    font-size: 11px;
    font-weight: 600;
}}

/* -------------------------------------------------------------- 选项卡等 */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: 10px;
    background: {CARD};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SUB};
    padding: 7px 16px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    font-size: 13px;
}}
QTabBar::tab:hover {{ color: {PRIMARY}; }}
QTabBar::tab:selected {{
    background: {CARD};
    color: {PRIMARY};
    font-weight: 700;
    border: 1px solid {BORDER};
    border-bottom-color: {CARD};
}}

QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c8d3e0; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {PRIMARY}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: #c8d3e0; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {PRIMARY}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QSplitter::handle {{ background: transparent; }}

/* 底部信息条：并入主内容列（不是 QStatusBar），所以只跟内容区走、不横贯侧边栏。
   顶栏是「上边界」，它是「下边界」，上下各一道 1px 分隔线把内容区框起来。 */
QFrame#InfoBar {{
    background: {CARD};
    border: none;
    border-top: 1px solid {BORDER};
}}
QPushButton#InfoLink {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 3px 8px;
    color: {MUTED};
    font-size: 11px;
    text-align: left;
    min-height: 18px;
}}
QPushButton#InfoLink:hover {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
}}
QLabel#InfoStat {{
    color: {MUTED};
    font-size: 11px;
    font-family: {MONO_FAMILY};
}}

QToolTip {{
    background: #24384c;
    color: #e8eef5;
    border: 1px solid #2e4a66;
    border-radius: 6px;
    padding: 5px 8px;
}}

QDialog {{ background: {BG}; }}
QMessageBox {{ background: {CARD}; }}
QMessageBox QLabel {{ color: {TEXT}; }}
QMenu {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 8px;
    padding: 5px;
    color: {TEXT};
}}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {PRIMARY_SOFT}; color: {PRIMARY}; }}
QMenu::separator {{ height: 1px; background: {BORDER}; margin: 4px 8px; }}

QProgressBar {{
    background: {NEUTRAL_SOFT};
    border: none;
    border-radius: 6px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {PRIMARY}; border-radius: 6px; }}

/* -------------------------------------------------- 关于页 · 联系作者行 */
/* ⚠️ QWidget 的 Python 子类默认**不绘制** QSS 的 background，必须由代码侧
   setAttribute(Qt.WA_StyledBackground, True) 打开（见 pages._ContactRow）。 */
QWidget#ContactRow {{
    border-radius: 10px;
    border: 1px solid transparent;
}}
QWidget#ContactRow:hover {{
    background: {PRIMARY_SOFT};
    border-color: #d5e6f2;
}}
"""


# --------------------------------------------------------------- 悬浮窗样式
#
# 桌面常驻的小面板，版式参考「农历日历」那种密集浮窗：一条窄头部（图标 + 名称 +
# 小胶囊计数 + 图标按钮）、若干带小标题的分区块、一行版权说明、底部一排动作按钮。
#
# ⚠️ 三条踩过的坑：
#   1. 面板底与圆角**不由 QSS 画**，而是 FloatRoot.paintEvent 自绘 —— 窗口是
#      WA_TranslucentBackground，QSS 的 border-radius 只能让四个角变透明，
#      真正的圆角裁剪得自己画路径（也顺带能画「贴边收起」时的把手）。
#   2. 主 QSS 里 `QScrollArea > QWidget > QWidget {{ background: BG }}` 会命中
#      滚动区的内容层，把面板刷成灰底。这里必须用 id 选择器覆盖回透明。
#   3. 分区块一律用 QFrame —— 普通 QWidget 不认样式表的 background / border，
#      要额外 setAttribute(WA_StyledBackground) 才行，用 QFrame 免掉这个坑。
FLOAT_QSS = f"""
QWidget#FloatRoot, QWidget#FloatInner {{
    background: transparent;
}}

QFrame#FloatHeader {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {BORDER};
}}
QLabel#FloatName {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 700;
}}
QLabel#FloatMeta {{
    color: {MUTED};
    font-size: 10px;
}}
QLabel#FloatChip, QLabel#FloatChipAlert {{
    border-radius: 8px;
    padding: 1px 7px;
    font-size: 10px;
    font-weight: 700;
}}
QLabel#FloatChip {{ background: {SUCCESS_SOFT}; color: {SUCCESS}; }}
QLabel#FloatChipAlert {{ background: {DANGER_SOFT}; color: {DANGER}; }}

QScrollArea#FloatBody {{ background: transparent; border: none; }}
QScrollArea#FloatBody > QWidget {{ background: transparent; }}

QFrame#FloatBlock {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#FloatBlockTitle {{
    color: {TEXT_SUB};
    font-size: 11px;
    font-weight: 700;
}}
QFrame#FloatRule {{
    background: {BORDER};
    border: none;
    max-height: 1px;
}}
QLabel#FloatRowName {{ color: {TEXT}; font-size: 12px; }}
QLabel#FloatRowMeta {{ color: {MUTED}; font-size: 11px; font-family: {MONO_FAMILY}; }}
QLabel#FloatEmpty {{ color: {MUTED}; font-size: 11px; }}

QLabel#FloatStatNum {{ font-size: 19px; font-weight: 700; }}
QLabel#FloatStatLabel {{ color: {TEXT_SUB}; font-size: 10px; }}

QLabel#FloatBigDate {{ color: {TEXT}; font-size: 19px; font-weight: 700; }}
QLabel#FloatWeek {{ color: {PRIMARY}; font-size: 12px; font-weight: 700; }}
QLabel#FloatTime {{
    color: {TEXT};
    font-size: 21px;
    font-weight: 700;
    font-family: {MONO_FAMILY};
}}
QLabel#FloatTipText {{
    background: {GOLD_SOFT};
    border: 1px solid #efe0b6;
    border-radius: 8px;
    padding: 6px 8px;
    color: #6b5410;
    font-size: 11px;
}}
QLabel#FloatChipCat {{
    background: {NEUTRAL_SOFT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 4px 8px;
    color: {TEXT_SUB};
    font-size: 11px;
}}

QFrame#FloatFoot {{
    background: transparent;
    border: none;
    border-top: 1px solid {BORDER};
}}
QLabel#FloatCopy {{ color: {MUTED}; font-size: 10px; }}
QLabel#FloatHint {{ color: #a7b3c2; font-size: 10px; }}

QPushButton#FloatBtn {{
    background: {CARD};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 5px 8px;
    color: {TEXT};
    font-size: 12px;
    min-height: 20px;
}}
QPushButton#FloatBtn:hover {{ border-color: {PRIMARY}; color: {PRIMARY}; }}
QPushButton#FloatBtn:pressed {{ background: {PRIMARY_SOFT}; }}

QPushButton#FloatIcon, QPushButton#FloatClose {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 0;
    min-width: 24px;  max-width: 24px;
    min-height: 24px; max-height: 24px;
}}
QPushButton#FloatIcon:hover {{ background: {PRIMARY_SOFT}; }}
QPushButton#FloatClose:hover {{ background: {DANGER}; }}
"""

# -------------------------------------------------- 系统托盘（tray.py）
# QMenu 是顶层弹层：不接管的话会退回 Win11 默认那套巨大内边距 + 灰底方角，
# 和软件里其它弹层完全不是一路。这里只覆写菜单该管的几条。
TRAY_QSS = f"""
QMenu#TrayMenu {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QMenu#TrayMenu::item {{
    background: transparent;
    color: {TEXT};
    padding: 7px 26px 7px 14px;
    border-radius: 7px;
    font-size: 13px;
    min-width: 132px;
}}
QMenu#TrayMenu::item:selected {{
    background: {PRIMARY_SOFT};
    color: {PRIMARY};
}}
QMenu#TrayMenu::item:disabled {{ color: {MUTED}; }}
QMenu#TrayMenu::icon {{ padding-left: 8px; }}
QMenu#TrayMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
"""
