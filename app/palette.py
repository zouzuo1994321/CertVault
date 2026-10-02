# -*- coding: utf-8 -*-
"""显式浅色调色板 —— 屏蔽 Windows 深色模式与系统强调色对 Qt 控件的污染。

背景（本机实测）：
    AppsUseLightTheme = 0               系统处于深色模式
    SystemUsesLightTheme = 0
    AccentColorMenu   = 0xff810068      系统强调色为紫红 #810068

Qt 启动时会把系统调色板灌进 QApplication，于是：

1. ``QPalette.Text`` / ``WindowText`` 变成浅色 —— 凡是 QSS 里没显式写
   ``color`` 的控件（下拉弹层列表项、日历单元格、星期表头…）就变成
   「白字白底」，一个字都看不见；
2. ``QPalette.Highlight`` 变成系统强调色 —— 下拉弹层的选中项/当前项指示条、
   日历的导航条统统被画成紫红色。

样式表只能覆盖它显式声明过的属性，覆盖不了「样式引擎自己去取调色板」的地方。
所以在 ``QApplication`` 创建之后、构建任何控件之前，把样式与调色板钉死成
我们自己的浅色档案风。

这里**故意不去调 ``app.setStyle(...)``**：保留系统默认样式（本机为 windows11），
下拉框的 chevron 箭头、控件圆角阴影都由原生样式绘制，观感最好；万一该样式插件
在打包时缺失，Qt 也会自动回退到内置的 Fusion，不会崩。真正需要钉死的只是调色板。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from . import theme


def apply_palette(app) -> None:
    """把调色板固定为浅色档案风，并挂载全局样式表。

    必须在创建任何 QWidget 之前调用，这样所有控件一诞生就拿到正确的调色板。
    """
    c_card = QColor(theme.CARD)
    c_text = QColor(theme.TEXT)
    c_primary = QColor(theme.PRIMARY)
    c_white = QColor("#ffffff")

    p = QPalette()
    # 不指定分组 = 同时写入 Active / Inactive / Disabled 三组
    p.setColor(QPalette.Window, QColor(theme.BG))
    p.setColor(QPalette.WindowText, c_text)
    p.setColor(QPalette.Base, c_card)
    p.setColor(QPalette.AlternateBase, QColor("#fafcfe"))
    p.setColor(QPalette.Text, c_text)
    p.setColor(QPalette.PlaceholderText, QColor(theme.MUTED))
    p.setColor(QPalette.Button, c_card)
    p.setColor(QPalette.ButtonText, c_text)
    p.setColor(QPalette.BrightText, c_white)
    p.setColor(QPalette.Link, c_primary)
    p.setColor(QPalette.LinkVisited, QColor("#6b4f9e"))
    p.setColor(QPalette.Highlight, c_primary)
    p.setColor(QPalette.HighlightedText, c_white)
    p.setColor(QPalette.ToolTipBase, QColor("#24384c"))
    p.setColor(QPalette.ToolTipText, QColor("#e8eef5"))
    p.setColor(QPalette.Light, c_white)
    p.setColor(QPalette.Midlight, QColor("#f0f3f8"))
    p.setColor(QPalette.Mid, QColor(theme.BORDER_STRONG))
    p.setColor(QPalette.Dark, QColor("#c2ccda"))
    p.setColor(QPalette.Shadow, QColor("#9fadbf"))

    # 禁用态统一压灰，避免「浅灰字 + 深色底」的糊字
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor("#b6c1cd"))

    app.setPalette(p)

    # 挂在 QApplication 上而不是单个窗口：顶层弹层（下拉列表、日历、菜单）
    # 也能稳定继承到样式，不会因为挂在某个窗口上而漏掉。
    app.setStyleSheet(theme.QSS)
