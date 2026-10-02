# -*- coding: utf-8 -*-
"""系统托盘：主窗口最小化后在这里驻留，而不是缩到任务栏里等着被误关。

版式与交互
----------
- **托盘图标**用应用徽标（`icons.logo_pixmap`），跟窗口标题栏一个视觉。
- **单击 / 双击** → 显示并置前主窗口；从最小化恢复时还要`showNormal()`
  （只调 `show()` 的话，窗口会保持最小化态，看起来像「点了没反应」）。
- **右键** → 上下文菜单：显示主窗口 / 到期提醒 / 悬浮窗开关 / 立即检查 / 退出。
  「退出」是唯一的真退出路径，托盘图标与菜单自己不出现在菜单里。

为什么用 `QSystemTrayIcon` 而不是自绘一个贴在桌面的角标
----------------------------------------------------
Windows 的托盘是原生设施：用户在任务栏上就能看见、能右键、能用通知气泡，
这些行为完全由 shell 负责，我们不需要自己画也不应该自己画。

三个必须注意的点
----------------
1. **窗口最小化 ≠ 隐藏**。要真正「收进托盘」，必须 `hide()` 主窗口；
   `showMinimized()` 只是把任务栏按钮换成最小化态，窗口仍在任务栏上。
   反过来，恢复时必须先 `showNormal()` 再 `raise_()` + `activateWindow()`，
   否则从托盘恢复出来会是一个「怎么点都不动」的窗口。
2. **`setQuitOnLastWindowClosed(False)` 必须开**。主窗口 `hide()` 之后
   「最后一个窗口」已经不可见了，Qt 默认会认为该退出而直接 `qApp.quit()`，
   于是托盘图标闪一下就没了 —— 表现是「最小化一下软件就自己关掉了」。
   真退出要走托盘菜单里的「退出」。
3. **托盘菜单要能被主题接管**。`QMenu` 是顶层弹层，得挂到 `QApplication`
   上（`palette.apply_palette` 已经这么做了），并且单独覆盖几条规则：
   Windows 11 默认会给菜单项加内边距、不吃圆角，还带一圈灰底。

桌面通知
--------
`notify()` 用托盘气泡做「有证书要到期了」的被动提醒。它只在**主窗口不可见**
时发 —— 窗口开着的时候用户已经看得见，再弹气泡纯属打扰。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import icons, theme, version


class Tray(QObject):
    """系统托盘图标及其菜单。

    对外只暴露三个动作，具体逻辑交给主窗口回调 —— 托盘本身不该知道
    「主窗口有哪些页面」「悬浮窗怎么开关」，否则它会变成第二个 MainWindow。
    """

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._cb_show_main = None
        self._cb_goto_reminders = None
        self._cb_toggle_float = None
        self._cb_check_now = None
        self._cb_quit = None
        self._notify_on = True

        self.icon = QSystemTrayIcon(icons.app_icon(), self)
        self.icon.setToolTip(f"{version.APP_NAME} {version.APP_VERSION}")

        self.menu = QMenu()
        self.menu.setObjectName("TrayMenu")
        # 菜单是顶层弹层：不吃QSS 就退回系统灰底 + Win11 那套巨大内边距。
        self.menu.setStyleSheet(theme.QSS + theme.TRAY_QSS)

        self.act_show = QAction("显示主窗口", self)
        self.act_reminders = QAction("到期提醒", self)
        self.act_float = QAction("窗口悬浮窗", self)
        self.act_float.setCheckable(True)
        self.act_check = QAction("立即检查提醒", self)
        self.act_quit = QAction("退出" + version.APP_NAME, self)

        for act, name in ((self.act_show, "cert"), (self.act_reminders, "bell"),
                          (self.act_float, "float"), (self.act_check, "refresh"),
                          (self.act_quit, "close")):
            act.setIcon(icons.icon(name, theme.TEXT_SUB, 15))

        self.menu.addAction(self.act_show)
        self.menu.addAction(self.act_reminders)
        self.menu.addSeparator()
        self.menu.addAction(self.act_float)
        self.menu.addAction(self.act_check)
        self.menu.addSeparator()
        self.menu.addAction(self.act_quit)          # 唯一的真退出路径
        self.icon.setContextMenu(self.menu)

        #单击 / 双击都恢复主窗口。两者的区别只在「单击还要不要切换悬浮窗」，
        # 那属于增强行为，这里不做 —— 误触成本高、收益低。
        self.icon.activated.connect(self._on_activated)

        # 菜单动作统一在这里转发，回调由主窗口注入
        self.act_show.triggered.connect(lambda: self._fire("show_main"))
        self.act_reminders.triggered.connect(lambda: self._fire("reminders"))
        self.act_float.triggered.connect(lambda: self._fire("toggle_float"))
        self.act_check.triggered.connect(lambda: self._fire("check_now"))
        self.act_quit.triggered.connect(lambda: self._fire("quit"))

    # ------------------------------------------------------------ 接线
    def bind(self, *, show_main, goto_reminders, toggle_float, check_now, quit_app):
        self._cb_show_main = show_main
        self._cb_goto_reminders = goto_reminders
        self._cb_toggle_float = toggle_float
        self._cb_check_now = check_now
        self._cb_quit = quit_app

    def _fire(self, which: str) -> None:
        cb = {
            "show_main": self._cb_show_main,
            "reminders": self._cb_goto_reminders,
            "toggle_float": self._cb_toggle_float,
            "check_now": self._cb_check_now,
            "quit": self._cb_quit,
        }.get(which)
        if cb is not None:
            cb()

    def _on_activated(self, reason) -> None:
        # Trigger 单击在部分 Windows 环境下不触发（会被当成「单击即菜单」），
        # 所以单击和双击都接；两次触发对「显示主窗口」这个幂等动作无害。
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self._cb_show_main is not None:
                self._cb_show_main()

    # ------------------------------------------------------------ 状态
    def start(self) -> None:
        """显示托盘图标。系统不支持托盘（极老的环境）时静默跳过。"""
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.icon.show()

    def stop(self) -> None:
        self.icon.hide()

    def set_float_on(self, on: bool) -> None:
        """同步悬浮窗开关的勾选态（用户可能从顶栏或设置面板改的）。"""
        self.act_float.setChecked(bool(on))
        self.act_float.setText("隐藏窗口悬浮窗" if on else "窗口悬浮窗")

    def set_notify(self, on: bool) -> None:
        """气泡通知总开关（设置面板的「收进托盘后用气泡通知」）。"""
        self._notify_on = bool(on)

    def notify_expiring(self, n: int) -> None:
        """到期气泡。只在窗口不可见时发 —— 开着窗口还弹气泡纯属打扰。"""
        if not self._notify_on or n <= 0:
            return
        self.notify(f"有 {n} 本证书需要关注", "点击托盘图标查看明细，或在到期提醒页逐条处置。")

    def set_count(self, n: int) -> None:
        """在托盘气泡 / 提示里带上待关注数量 —— 收进托盘后这是唯一能看到的状态。"""
        if n > 0:
            self.icon.setToolTip(f"{version.APP_NAME} {version.APP_VERSION} · "
                                 f"{n} 本待关注")
        else:
            self.icon.setToolTip(f"{version.APP_NAME} {version.APP_VERSION}")

    def notify(self, title: str, text: str) -> None:
        """桌面气泡。仅在主窗口不可见时才真的发出去。

        ⚠️ PySide6 的 `showMessage` 只绑到 4 个参数 `(title, text, icon, msecs)`，
        **没有 C++ 那个 `QSystemTrayIcon::MessageIcon` 参数** —— 照Qt 文档写五个参数会
        直接 `TypeError: too many arguments`。图标类型只能由 `setIcon()` 那侧决定，
        所以这里传 `QSystemTrayIcon.Information` 是错的（那是枚举类不是 Icon）。
        """
        if not self.icon.isVisible() or not QSystemTrayIcon.supportsMessages():
            return
        self.icon.showMessage(title, text, icons.app_icon(), 6000)