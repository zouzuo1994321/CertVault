# -*- coding: utf-8 -*-
"""主窗口：侧边栏导航 + 顶栏 + 页面栈 + 到期提醒调度。"""

from __future__ import annotations

import ctypes
import sys
from datetime import date
from typing import Dict, Optional

from PySide6.QtCore import (QDate, QEvent, QPoint, QRect, QPropertyAnimation,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QAction, QColor, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QMainWindow, QPushButton,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import db as dbm
from . import icons, paths, theme, version
from .dialogs import (CategoryDialog, ReminderDialog, SettingsDialog, confirm,
                      open_path)
from .floatwin import FloatWindow
from .pages import (AboutPage, CertificatePage, DashboardPage, ExamPage,
                    MaterialPage, ReminderPage)
from .tray import Tray
from .widgets import GazeLogo, IconButton

NAV = [
    ("dashboard", "首页总览", "dashboard"),
    ("certs", "证书管理", "cert"),
    ("reminders", "到期提醒", "bell"),
    ("exams", "考试计划", "calendar"),
    ("materials", "学习资料", "book"),
    ("about", "关于与声明", "info"),
]


class WinButton(QPushButton):
    """无边框窗口的系统按钮（最小化 / 最大化 / 还原 / 关闭）。

    图标随 hover 换色：普通按钮悬停转深色，关闭按钮悬停转白色（配红色底）。
    """

    def __init__(self, icon_name: str, tip: str, danger: bool = False,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("WinClose" if danger else "WinBtn")
        self.setToolTip(tip)
        self.setIconSize(QSize(16, 16))
        self.setFocusPolicy(Qt.NoFocus)
        self._icon_name = icon_name
        self._danger = danger
        self._apply()

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self._apply()

    def _apply(self) -> None:
        hover = self.underMouse() or self.isDown()
        if hover and self._danger:
            color = "#ffffff"
        elif hover:
            color = theme.TEXT
        else:
            color = theme.TEXT_SUB
        self.setIcon(icons.icon(self._icon_name, color, 16))

    def enterEvent(self, e):  # noqa: N802
        self._apply()
        super().enterEvent(e)

    def leaveEvent(self, e):  # noqa: N802
        self._apply()
        super().leaveEvent(e)


class TopBar(QWidget):
    """顶栏：无边框窗口里的「标题栏」，一块区域两种拖动通路。

    主通路在 ``MainWindow.nativeEvent()``：把 WM_NCHITTEST 判成 HTCAPTION，直接交给
    Windows 的原生移动循环，贴边分屏 / Win+方向键 / 双击最大化 / 右键系统菜单全部白送。

    这里加一条 Qt 层的兜底：万一某次命中测试没走到原生通路（例如窗口刚被搬到另一块
    屏、系统给的坐标与 Qt 自己的位置短暂不同步，或被某个子控件吃掉），鼠标仍然会以
    客户区消息的形式落到顶栏上。此时调 ``QWindow.startSystemMove()`` —— 它是 Qt 官方
    的「进入系统移动循环」入口，在 Windows 上等价于 SC_MOVE，同样保留贴边分屏能力。
    两条通路不会叠加：走原生通路时 Qt 根本收不到这次按下事件。
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        # ★ 必须显式打开 WA_StyledBackground：``QWidget`` 的**子类**默认不画样式表里的
        #   background / border（只有 QFrame 和少量内建控件会）。少了这一句，
        #   ``QWidget#TopBar {{ background: CARD; border-bottom }}`` 这条规则形同虚设 ——
        #   顶栏一直是透明的，直接露着内容区的灰底，下半部那条 1px 分隔线也从来没画出来，
        #   于是「白底 + 一道线」的顶栏与底部信息条对不上。症状极轻（只是灰一点），
        #   所以这个坑从无边框改造那版起一直没被发现。
        self.setAttribute(Qt.WA_StyledBackground, True)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            wh = self.window().windowHandle() if self.window() else None
            if wh is not None and wh.startSystemMove():
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):  # noqa: N802
        win = self.window()
        if e.button() == Qt.LeftButton and hasattr(win, "_toggle_max"):
            win._toggle_max()  # type: ignore[attr-defined]
            e.accept()
            return
        super().mouseDoubleClickEvent(e)


def nav_icon(name: str) -> QIcon:
    """侧边栏图标：未选中为灰蓝，选中为纯白。"""
    ic = QIcon()
    ic.addPixmap(icons.pixmap(name, theme.SIDEBAR_TEXT, 18),
                 QIcon.Normal, QIcon.Off)
    ic.addPixmap(icons.pixmap(name, "#ffffff", 18),
                 QIcon.Normal, QIcon.On)
    ic.addPixmap(icons.pixmap(name, "#ffffff", 18),
                 QIcon.Active, QIcon.Off)
    return ic


class MainWindow(QMainWindow):
    def __init__(self, database: dbm.Database) -> None:
        super().__init__()
        self.db = database
        self._last_date = date.today()
        self.setWindowTitle(f"{version.APP_NAME}  ·  {version.FULL_VERSION}")
        self.setWindowIcon(icons.app_icon())
        self.setStyleSheet(theme.QSS)
        # 无外框模式：不要系统标题栏与外框，窗口控制按钮并入顶栏右上角。
        # 缩放、拖动、贴边、双击最大化由 nativeEvent 里的 WM_NCHITTEST 交还给系统。
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.resize(1420, 880)
        self.setMinimumSize(1120, 700)
        self._native_style_fixed = False
        self._caption_exempt: set = set()
        self.floatwin: Optional[FloatWindow] = None
        self.tray: Optional[Tray] = None
        # 「真退出」的唯一闸门：托盘菜单的退出按钮把它置True，
        # 于是关窗口 / Alt+F4 只收进托盘，不会把进程一起带走。
        self._quitting = False
        # 收进托盘时用来提示一次的浮层（避免 toast 跟着窗口一起消失）
        self._tray_hint_shown = False

        central = QWidget()
        central.setObjectName("Root")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        root.addWidget(self._build_content(), 1)
        self.setCentralWidget(central)

        self._build_shortcuts()

        self.toast_lbl = QLabel(central)
        self.toast_lbl.setStyleSheet(
            f"background:#24384c; color:#eef4fa; border-radius:9px;"
            f" padding:9px 18px; font-size:13px;")
        self.toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._hide_toast)

        # 跨日刷新 + 启动提醒
        self._day_timer = QTimer(self)
        self._day_timer.setInterval(60 * 1000)
        self._day_timer.timeout.connect(self._check_day_change)
        self._day_timer.start()

        self.goto("dashboard")
        self.reload_all()
        QTimer.singleShot(800, self.maybe_startup_reminder)
        # 悬浮窗是「上次开着，这次就还开着」——延迟一点等主窗口落定再摆位置
        if self.db.get_setting("float_on", "0") == "1":
            QTimer.singleShot(400, self._restore_float)

    # ------------------------------------------------------------ 侧边栏
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(212)
        v = QVBoxLayout(side)
        v.setContentsMargins(14, 20, 14, 16)
        v.setSpacing(6)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        # 「视角跟随」徽标：鼠标在窗口内移动时会分层视差 + 轻微转头
        brand.addWidget(GazeLogo(38))
        col = QVBoxLayout()
        col.setSpacing(1)
        t = QLabel(version.APP_NAME)
        t.setObjectName("BrandTitle")
        col.addWidget(t)
        s = QLabel(version.APP_NAME_EN.upper())
        s.setObjectName("BrandSub")
        col.addWidget(s)
        brand.addLayout(col, 1)
        v.addLayout(brand)
        v.addSpacing(6)

        ver = QLabel(f"{version.APP_VERSION}  ·  {version.BUILD}")
        ver.setObjectName("BrandVer")
        v.addWidget(ver)
        v.addSpacing(6)

        line = QFrame()
        line.setObjectName("BrandLine")
        line.setFixedHeight(1)
        v.addWidget(line)
        v.addSpacing(10)

        self.nav_buttons: Dict[str, QPushButton] = {}
        for key, label, icon_name in NAV:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("NavBtn")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIcon(nav_icon(icon_name))
            btn.setIconSize(QSize(18, 18))
            btn.clicked.connect(lambda _=False, k=key: self.goto(k))
            self.nav_buttons[key] = btn
            v.addWidget(btn)

        v.addStretch(1)

        foot = QLabel(f"{version.COPYRIGHT}\n{version.LICENSE_LINE}")
        foot.setObjectName("SidebarFoot")
        foot.setWordWrap(True)
        v.addWidget(foot)
        return side

    # ------------------------------------------------------------ 主内容
    def _build_content(self) -> QWidget:
        wrap = QWidget()
        v = QVBoxLayout(wrap)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        top = TopBar()
        top.setObjectName("TopBar")
        top.setFixedHeight(72)
        self.topbar = top          # 无边框模式下它就是「标题栏」，用于命中测试
        h = QHBoxLayout(top)
        h.setContentsMargins(24, 10, 8, 10)
        h.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(2)
        self.lbl_title = QLabel("")
        self.lbl_title.setObjectName("PageTitle")
        col.addWidget(self.lbl_title)
        self.lbl_sub = QLabel("")
        self.lbl_sub.setObjectName("PageSub")
        col.addWidget(self.lbl_sub)
        h.addLayout(col, 1)

        # 悬浮窗开关：常驻桌面小面板。开着的时候图标转成主色，一眼看出状态。
        self.btn_float = IconButton("float", "窗口悬浮窗（Ctrl+Shift+F）",
                                    theme.TEXT_SUB, 20)
        self.btn_float.clicked.connect(self.toggle_float)

        self.btn_bell = IconButton("bell", "查看到期提醒", theme.TEXT_SUB, 20)
        self.badge = QLabel(self.btn_bell)
        self.badge.setObjectName("BellCount")
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setFixedSize(17, 15)
        self.badge.move(24, 1)
        self.badge.hide()
        self.btn_bell.clicked.connect(self.show_reminder)

        self.btn_settings = IconButton("settings", "设置", theme.TEXT_SUB, 20)
        self.btn_settings.clicked.connect(self.open_settings)
        h.addWidget(self.btn_float)
        h.addWidget(self.btn_bell)
        h.addWidget(self.btn_settings)

        # ---- 窗口控制按钮（无边框模式下的最小化 / 最大化 / 关闭）
        sep = QFrame()
        sep.setObjectName("TitleSep")
        sep.setFixedSize(1, 22)
        h.addSpacing(4)
        h.addWidget(sep)

        self.btn_min = WinButton("min", "最小化")
        self.btn_max = WinButton("max", "最大化")
        self.btn_close = WinButton("close", "关闭", danger=True)
        self.btn_min.clicked.connect(self.minimize_to_tray)
        self.btn_max.clicked.connect(self._toggle_max)
        self.btn_close.clicked.connect(self.close)
        self.win_btns = QWidget(top)
        wb = QHBoxLayout(self.win_btns)
        wb.setContentsMargins(0, 0, 0, 0)
        wb.setSpacing(2)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            wb.addWidget(b)
        h.addWidget(self.win_btns)

        # 命中测试白名单：落在这些控件上时不能当成标题栏，否则点不动
        self._caption_exempt = {self.btn_float, self.btn_bell, self.btn_settings,
                                self.win_btns}
        v.addWidget(top)

        self.stack = QStackedWidget()
        self.stack.setObjectName("Pages")
        self.pages: Dict[str, object] = {}
        for key, cls in (("dashboard", DashboardPage), ("certs", CertificatePage),
                         ("reminders", ReminderPage), ("exams", ExamPage),
                         ("materials", MaterialPage), ("about", AboutPage)):
            page = cls(self)
            self.pages[key] = page
            self.stack.addWidget(page)  # type: ignore[arg-type]
        self.pages["dashboard"].goto_page.connect(self.goto)  # type: ignore[attr-defined]
        v.addWidget(self.stack, 1)
        v.addWidget(self._build_infobar())
        return wrap

    def _build_infobar(self) -> QWidget:
        """底部信息条：并入主内容列的最后一格，而不是独立的状态栏。

        原来用 ``QStatusBar`` 挂在窗口上，它会横贯整个窗口宽度、压在深色侧边栏下面，
        底色与圆角都自成一套，看起来像外挂的条子。改成主布局里的一行之后，侧边栏
        可以一路通到底，信息条只跟着内容区走，视觉上与顶栏形成上下呼应。
        """
        bar = QFrame()
        bar.setObjectName("InfoBar")
        bar.setFixedHeight(34)
        self.infobar = bar
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 0, 18, 0)
        h.setSpacing(8)

        ico = QLabel()
        ico.setPixmap(icons.pixmap("folder", theme.MUTED, 14))
        ico.setFixedWidth(16)
        h.addWidget(ico)

        # 数据目录可点：直接调系统资源管理器打开，省得用户照着路径手翻。
        # 路径按字符数中间省略：极深的安装目录会把右侧统计信息挤出信息条。
        full = str(paths.DATA_DIR)
        shown = full if len(full) <= 64 else full[:24] + " … " + full[-37:]
        self.btn_dir = QPushButton(f"数据目录   {shown}")
        self.btn_dir.setObjectName("InfoLink")
        self.btn_dir.setCursor(Qt.PointingHandCursor)
        self.btn_dir.setToolTip(f"在资源管理器中打开：{full}")
        self.btn_dir.clicked.connect(lambda: open_path(paths.DATA_DIR))
        h.addWidget(self.btn_dir)
        h.addStretch(1)

        self.lbl_stat = QLabel("")
        self.lbl_stat.setObjectName("InfoStat")
        h.addWidget(self.lbl_stat)
        return bar

    def _build_shortcuts(self) -> None:
        acts = [
            ("F5", self.reload_all),
            ("Ctrl+N", lambda: self.goto("certs") or self.pages["certs"]._new()),
            ("Ctrl+R", self.show_reminder),
            ("Ctrl+,", self.open_settings),
            ("Ctrl+Shift+F", self.toggle_float),
            ("Ctrl+Q", self.close),
        ]
        for seq, fn in acts:
            a = QAction(self)
            a.setShortcut(QKeySequence(seq))
            a.triggered.connect(fn)  # type: ignore[arg-type]
            self.addAction(a)

    # -------------------------------------------- 无边框窗口的原生命中测试
    #
    # 思路：不用自己去模拟拖动和缩放，而是把 WM_NCHITTEST 的返回值改成窗口的
    # 对应区域，让 Windows 用原生方式处理。这样拖动走的是系统移动循环，
    # Aero Snap（贴边分屏）、Win+方向键、双击标题栏最大化、右键系统菜单
    # 全都自动可用，且行为与原生窗口完全一致。

    _WM_NCHITTEST = 0x0084
    _HT_CLIENT, _HT_CAPTION = 1, 2
    _RESIZE_BORDER = 6
    # 顶边单独留窄一点：顶栏（= 标题栏）紧贴窗口顶边，如果顶边也留 6px 缩放热区，
    # 用户「抓顶栏上沿」时拿到的是缩放箭头而不是移动，会以为顶栏拖不动。
    _RESIZE_TOP = 4

    def _in_caption(self, pos: QPoint) -> bool:
        """顶栏整条 + 侧边栏顶部品牌区都可以拖动窗口。"""
        top = getattr(self, "topbar", None)
        if top is not None:
            tl = top.mapTo(self, QPoint(0, 0))
            if QRect(tl, top.size()).contains(pos):
                return True
        side = getattr(self, "sidebar", None)
        return bool(side and pos.x() < side.width() and pos.y() < 88)

    def nativeEvent(self, event_type, message):  # noqa: N802
        if sys.platform != "win32":
            return super().nativeEvent(event_type, message)
        try:
            msg = ctypes.wintypes.MSG.from_address(int(message))
        except Exception:  # noqa: BLE001
            return super().nativeEvent(event_type, message)
        if msg.message != self._WM_NCHITTEST:
            return super().nativeEvent(event_type, message)

        # lParam 低 16 位是屏幕坐标 x，高 16 位是 y（均为有符号）
        gp = QPoint(ctypes.c_short(msg.lParam & 0xFFFF).value,
                    ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value)
        pos = self.mapFromGlobal(gp)

        # 1) 落在交互控件上 → 交回 Qt，别被当成标题栏拖走
        w = QApplication.widgetAt(gp)
        while w is not None:
            if w in self._caption_exempt:
                return True, self._HT_CLIENT
            w = w.parentWidget()

        # 2) 标题栏区 → 原生拖动 / 双击最大化 / 贴边分屏
        #
        # 注意顺序：标题栏判定必须压过顶边的缩放热区。整条顶栏就是标题栏，而它贴着
        # 窗口顶边，如果把缩放热区放在前面，顶栏最上面几像素就变成「不可拖动区」，
        # 用户随手一按很容易落在那里。左右与底边仍按原样交给缩放。
        if self._in_caption(pos):
            return True, self._HT_CAPTION

        # 3) 四边四角：缩放热区（最大化时不需要）
        if not self.isMaximized():
            b = self._RESIZE_BORDER
            r = self.rect()
            left, right = pos.x() < b, pos.x() >= r.width() - b
            top, bottom = pos.y() < self._RESIZE_TOP, pos.y() >= r.height() - b
            if top and left:
                return True, 13          # HTTOPLEFT
            if top and right:
                return True, 14          # HTTOPRIGHT
            if bottom and left:
                return True, 16          # HTBOTTOMLEFT
            if bottom and right:
                return True, 17          # HTBOTTOMRIGHT
            if left:
                return True, 10          # HTLEFT
            if right:
                return True, 11          # HTRIGHT
            if top:
                return True, 12          # HTTOP
            if bottom:
                return True, 15          # HTBOTTOM

        return super().nativeEvent(event_type, message)

    def _fix_native_style(self) -> None:
        """给无边框窗口补回 WS_THICKFRAME 等样式位。

        Qt 用 FramelessWindowHint 建出来的窗口是 WS_POPUP 风格，Windows 认为它
        「不可缩放」，于是贴边分屏、Win+方向键、双击最大化全部失效。把样式位补
        回来即可恢复；窗口外观仍由我们自己绘制，不会重新长出原生标题栏。
        """
        if sys.platform != "win32":
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            get = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            setl = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get.restype = ctypes.c_ssize_t
            get.argtypes = [ctypes.c_void_p, ctypes.c_int]
            setl.restype = ctypes.c_ssize_t
            setl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            GWL_STYLE = -16
            want = (0x00040000    # WS_THICKFRAME  可缩放 / 贴边
                    | 0x00010000  # WS_MAXIMIZEBOX
                    | 0x00020000  # WS_MINIMIZEBOX
                    | 0x00080000)  # WS_SYSMENU  标题栏右键菜单
            setl(hwnd, GWL_STYLE, get(hwnd, GWL_STYLE) | want)
            SWP_NOSIZE, SWP_NOMOVE, SWP_NOZORDER, SWP_FRAMECHANGED = 1, 2, 4, 0x20
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0,
                                SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER
                                | SWP_FRAMECHANGED)
        except Exception:  # noqa: BLE001
            pass

    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _update_max_icon(self) -> None:
        btn = getattr(self, "btn_max", None)
        if btn is None:
            return
        btn.set_icon_name("restore" if self.isMaximized() else "max")
        btn.setToolTip("向下还原" if self.isMaximized() else "最大化")

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        if not self._native_style_fixed:
            self._native_style_fixed = True
            self._fix_native_style()

    def changeEvent(self, e):  # noqa: N802
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:
            self._update_max_icon()

    # ------------------------------------------------------------ 导航
    def goto(self, key: str) -> None:
        if key not in self.pages:
            return
        page = self.pages[key]
        self.stack.setCurrentWidget(page)  # type: ignore[arg-type]
        btn = self.nav_buttons.get(key)
        if btn:
            btn.setChecked(True)
        self.lbl_title.setText(getattr(page, "PAGE_TITLE", ""))
        self.lbl_sub.setText(getattr(page, "PAGE_SUB", ""))
        try:
            page.refresh()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ 刷新
    def reload_all(self) -> None:
        for page in self.pages.values():
            try:
                page.refresh()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        self._refresh_badge()
        self._refresh_float()

    def notify_changed(self) -> None:
        self._refresh_badge()
        self._refresh_float()
        cur = self.stack.currentWidget()
        for key, page in self.pages.items():
            if page is cur:
                continue
            try:
                page.refresh()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass

    def _refresh_badge(self) -> None:
        rows = self.db.expiring()
        n = len(rows)
        st = self.db.certificate_stats()
        self.lbl_stat.setText(
            f"证书 {st['total']} 本  ·  待关注 {n} 本  ·  {version.FULL_VERSION}")
        btn = self.nav_buttons.get("reminders")
        if btn:
            btn.setText("  到期提醒" + (f"   {n}" if n else ""))
        if n:
            self.badge.setText(str(n) if n < 100 else "99+")
            self.badge.show()
        else:
            self.badge.hide()
        # 收进托盘后，任务栏上什么信息都没有了 —— 待关注数量要跟着托盘提示走
        if self.tray is not None:
            self.tray.set_count(n)

    # ------------------------------------------------------------ 悬浮窗
    #
    # 悬浮窗是一个独立的顶层小窗口（Qt.Tool：不进任务栏、不占 Alt-Tab）。
    # 这里只做三件事：懒创建、开关、跟随数据刷新。
    # 窗口自己负责位置记忆、靠边吸附、内容块切换，主窗口不插手 ——
    # 否则「右键菜单改了内容」和「设置面板改了内容」两条路径很容易打架。

    def _ensure_float(self) -> FloatWindow:
        if self.floatwin is None:
            # ★ parent 必须是 None，不能传self。
            #   传了parent，Qt 会把悬浮窗挂成主窗口的 transient child →
            #   Windows 层面它就是个 **owned window**（GetWindow(hwnd, GW_OWNER)
            #   能查到主窗口的 hwnd）→ 主窗口一showMinimized()，系统顺手把它
            #   一起藏掉。麻烦的是 **QWidget.isVisible() 这时仍返回 True**，
            #   代码里看「还是可见的」，屏幕上却已经没了 —— 极难查。
            #   实测（build/_minprobe2.py）：有 parent 时主窗口最小化后
            #   IsWindowVisible=False；无 parent 时True，稳稳留在桌面上。
            fw = FloatWindow(self.db, None)
            fw.open_main.connect(self._float_raise_main)
            fw.open_reminders.connect(self.show_reminder)
            fw.settings_requested.connect(self.open_settings)
            fw.visibility_changed.connect(self._sync_float_btn)
            self.floatwin = fw
        return self.floatwin

    def toggle_float(self) -> None:
        fw = self._ensure_float()
        if fw.isVisible():
            fw.hide_window()
            self.toast("已隐藏悬浮窗")
        else:
            fw.show_window()
            self.toast("悬浮窗已开启 · 拖动顶部可移动，靠边自动吸附")

    def _restore_float(self) -> None:
        """启动时恢复上次的悬浮窗状态（位置由窗口自己从设置里读）。"""
        fw = self._ensure_float()
        if not fw.isVisible():
            fw.show_window()

    def _sync_float_btn(self, visible: bool) -> None:
        btn = getattr(self, "btn_float", None)
        if btn is not None:
            btn.set_colored(theme.PRIMARY if visible else theme.TEXT_SUB)
            btn.setToolTip("关闭悬浮窗（Ctrl+Shift+F）" if visible
                           else "窗口悬浮窗（Ctrl+Shift+F）")
        if self.tray is not None:
            self.tray.set_float_on(visible)

    def _refresh_float(self) -> None:
        fw = self.floatwin
        if fw is not None and fw.isVisible():
            fw.refresh()

    def _float_raise_main(self) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()

    # ------------------------------------------------------------ 系统托盘
    #
    # 最小化 = 收进托盘，而不是缩到任务栏里等着被误关。
    # 三个必须记住的点：
    #   1. **要 hide() 不是 showMinimized()** —— 后者只把任务栏按钮换成最小化态，
    #      窗口还在任务栏上，用户想「收起来」却发现它还在那儿。
    #   2. **恢复必须先 showNormal()** —— 只调 show() 的话窗口保持最小化态，
    #      看起来就是「点了托盘没反应」。
    #   3. **关窗口不等于退出** —— 退出只走托盘菜单（self._quitting 闸门）。

    def _ensure_tray(self) -> Optional[Tray]:
        if self.tray is not None:
            return self.tray
        from PySide6.QtWidgets import QSystemTrayIcon
        if self.db.get_setting("tray_on", "1") != "1":
            return None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return None
        tray = Tray(self)
        tray.set_notify(self.db.get_setting("tray_notify", "1") == "1")
        tray.bind(
            show_main=self._raise_from_tray,
            goto_reminders=lambda: (self._raise_from_tray(), self.goto("reminders")),
            toggle_float=self.toggle_float,
            check_now=self._tray_check_now,
            quit_app=self.quit_app,
        )
        self.tray = tray
        tray.start()
        # 托盘是懒创建的（第一次最小化才建），而徽标数字在__init__ 的 reload_all
        # 里就刷过了 —— 那时 self.tray 还是 None。待关注数量必须补刷一次，
        # 否则托盘提示会永远停在「没有数量」的状态。
        self._refresh_badge()
        return tray

    def minimize_to_tray(self) -> None:
        """顶栏「最小化」与 Alt+F4 之外的收拢路径：隐藏窗口，托盘继续驻留。"""
        tray = self._ensure_tray()
        if tray is None:
            # 系统没有托盘（极老环境）→ 退回真的最小化，宁可留在任务栏也不能消失
            self.showMinimized()
            return
        # 悬浮窗是独立顶层窗口（owner=None），主窗口隐藏它照样留在桌面上。
        # 这里不用管它，Qt 也不会去动它 —— 但要说清这件事，否则读者会以为漏了。
        self.hide()
        if not self._tray_hint_shown and self.db.get_setting("tray_notify", "1") == "1":
            self._tray_hint_shown = True
            tray.notify(f"{version.APP_NAME} 已在托盘运行",
                        "点击托盘图标可恢复窗口，悬浮窗仍留在桌面上。")

    def _raise_from_tray(self) -> None:
        """从托盘恢复：先showNormal 解除最小化态，再置前。"""
        if self.isMinimized():
            self.showNormal()
        elif not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()

    def _tray_check_now(self) -> None:
        self._raise_from_tray()
        self.show_reminder()

    def quit_app(self) -> None:
        """真退出：托盘菜单的「退出」与退出事件都走这里。"""
        self._quitting = True
        self.close()

    # ------------------------------------------------------------ 提醒
    def show_reminder(self) -> None:
        dlg = ReminderDialog(self.db, self, startup=False)
        dlg.goto_certs.connect(lambda: self.goto("reminders"))
        dlg.exec()
        if dlg.muted_today:
            self.db.set_setting("last_popup_date", date.today().isoformat())

    def maybe_startup_reminder(self) -> None:
        if self.db.get_setting("popup_on_start", "1") != "1":
            return
        today = date.today().isoformat()
        if self.db.get_setting("last_popup_date", "") == today:
            return
        if not self.db.expiring():
            return
        dlg = ReminderDialog(self.db, self, startup=True)
        dlg.goto_certs.connect(lambda: self.goto("reminders"))
        dlg.exec()
        if dlg.muted_today:
            self.db.set_setting("last_popup_date", today)

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.db, self)
        dlg.changed.connect(self.reload_all)
        dlg.exec()
        self._apply_float_setting()

    def _apply_float_setting(self) -> None:
        """设置面板可能改了悬浮窗的开关或内容，关掉对话框后同步一次。

        只认数据库里的 ``float_on``：用户点了「取消」时该值没变，
        悬浮窗状态自然也不会被改坏。
        """
        if self.db.get_setting("float_on", "0") == "1":
            fw = self._ensure_float()
            fw.reload_settings()
            if not fw.isVisible():
                fw.show_window()
        elif self.floatwin is not None and self.floatwin.isVisible():
            self.floatwin.hide_window()

    def _check_day_change(self) -> None:
        today = date.today()
        if today != self._last_date:
            self._last_date = today
            self.reload_all()
            self.db.set_setting("last_popup_date", "")
            # 跨日后若人不在窗口前（收在托盘里），补一条到期气泡 ——
            # 启动弹窗这时早就过去了，跨天的新到期情况得靠这个告知。
            if self.tray is not None and not self.isVisible():
                self.tray.notify_expiring(len(self.db.expiring()))

    # ------------------------------------------------------------ 提示条
    def _place_toast(self) -> None:
        """把提示条摆到「内容区底部、信息条上方」，并横向居中于内容区。"""
        c = self.centralWidget()
        if c is None:
            return
        bar_h = self.infobar.height() if getattr(self, "infobar", None) else 0
        left = self.sidebar.width()
        x = left + (c.width() - left - self.toast_lbl.width()) // 2
        y = c.height() - bar_h - self.toast_lbl.height() - 18
        self.toast_lbl.move(max(10, x), max(10, y))

    def toast(self, message: str, ms: int = 2200) -> None:
        self.toast_lbl.setText(message)
        self.toast_lbl.adjustSize()
        self._place_toast()
        self.toast_lbl.show()
        self.toast_lbl.raise_()
        self._toast_timer.start(ms)

    def _hide_toast(self) -> None:
        self.toast_lbl.hide()

    def resizeEvent(self, e):  # noqa: N802
        super().resizeEvent(e)
        if self.toast_lbl.isVisible():
            self._place_toast()

    # ------------------------------------------------------------ 退出
    def closeEvent(self, e):  # noqa: N802
        # 关窗口 ≠ 退出：`close_to_tray` 开着时收进托盘，只有托盘菜单的「退出」才真结束。
        # ⚠️ 拦截前必须先确认托盘**真的能用** —— 不然窗口会「关不掉」：
        # 用户点了 × 没反应，任务栏里也没有，程序还在跑却找不回来，那是死局。
        # 所以条件是「托盘已就绪」而不是「设置里开着」。
        to_tray = (self.db.get_setting("close_to_tray", "1") == "1"
                   and self._ensure_tray() is not None)
        if not self._quitting and to_tray:
            e.ignore()
            self.minimize_to_tray()
            return

        # 真退出：托盘图标先收掉，否则会留下一个点了没用的孤儿图标
        if self.tray is not None:
            self.tray.stop()
        # 悬浮窗是独立顶层窗口（owner=None），系统不会替我们收它 ——
        # 必须显式关掉，否则会留下一个「没有主程序」的孤儿面板。
        fw = self.floatwin
        if fw is not None:
            try:
                fw.close()
            except Exception:  # noqa: BLE001
                pass
        try:
            self.db.close()
        except Exception:  # noqa: BLE001
            pass
        e.accept()
