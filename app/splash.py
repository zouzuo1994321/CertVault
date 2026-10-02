# -*- coding: utf-8 -*-
"""启动动画（ Splash ）—— 盖住 PyInstaller 解包 + 主窗口构造那段空窗期。

## 为什么需要

实测（v1.5.0，源码态）启动各阶段耗时：

| 阶段 | 耗时 |
| -- | ---- |
| `QApplication` 创建 | 0.165s |
| 建库 | 0.031s |
| 调色板 | 0.002s |
| **主窗口构造** | **1.369s** ← 占 75% |
| `show()` | 0.210s |
| 合计 | 1.817s |

冻结态还要再加 PyInstaller onefile **解包归档**的时间（60MB 归档，肉眼可见地更久）。所以双击 exe 之后到窗口出现之间有一段「点了没反应」的真空 —— 这就是启动动画要填的洞。

## 设计取舍

- **无边框 + 半透明圆角自绘**：`WA_TranslucentBackground` 下 QSS 的 `border-radius`
  只会把四角涂透明，真圆角必须 `QPainterPath.addRoundedRect` 自绘（同 floatwin）。
- **动画驱动用 `QElapsedTimer` 真实 dt**：`α = 1 − exp(−dt/τ)` 帧率无关，
  与项目里动效的缓动口径一致（见 `qt-gaze-parallax` 技能）。
- **不用 `QProgressBar` 的原生外观**：Win11 默认样式不吃圆角，和项目风格不搭，
  进度条同样自绘。
- **兜底必须有**：任何一步抛异常都要保证 `close()` 被调用，
  否则主窗口起不来时用户会被一个卡死的动画困住 —— 探针专门验这一条。
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import (QElapsedTimer, QPointF, QRect, QRectF, Qt, QTimer,
                            Signal)
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
                           QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import icons, theme

#几何常量（单位：逻辑像素）
SPLASH_W = 300
SPLASH_H = 268
RADIUS = 16
LOGO_SIZE = 76
LOGO_TOP = 34#徽标距顶
BAR_W = 168# 进度条宽
BAR_H = 4
BAR_TOP = 186# 进度条距顶
TEXT_TOP = 206# 文案距顶
FADE_OUT_MS = 260# 淡出时长
MIN_SHOW_MS = 900# # 最短展示时间（太快会闪一下更难受）

# 阶段文案：按索引依次显示，让等待有进度感
STAGES = ["正在准备工作库", "正在加载证书与分类", "正在计算到期提醒", "就绪"]


class Splash(QWidget):
    """启动动画窗口。无边框、不抢焦点、点击穿透。"""

    finished = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.SplashScreen | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnTopHint
                            | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        # ★ 必须显式定尺寸：QWidget 默认 640x480，不设的话卡面会画成一大块空白方框
        self.resize(SPLASH_W, SPLASH_H)
        self.setFixedSize(SPLASH_W, SPLASH_H)

        self._stage = 0
        self._alpha = 0.0          # 整体淡入透明度0→1
        self._outro = 0.0          # 淡出进度 0→1（>0 表示正在收尾）
        self._closing = False# 已经进入收尾，不再重复响应
        self._shown_ms = 0         # 已经展示的毫秒数（自己累加，不用 QElapsedTimer）
        self._clock = QElapsedTimer()
        self._t0 = 0.0

        # 16ms 定时器驱动全部动画，**不另开多个定时器**
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------ 生命周期
    def begin(self) -> None:
        """开始播放。调用方应在主窗口构造**之前**调用。"""
        self._clock.start()
        self._t0 = 0.0
        self._shown_ms = 0
        self._closing = False
        self._outro = 0.0
        self._alpha = 0.0
        self._timer.start()
        self.update()

    def advance(self) -> None:
        """主窗口每完成一个阶段就调一次，让文案往前走。"""
        if self._stage < len(STAGES) - 1:
            self._stage += 1
            self.update()

    def finish(self) -> None:
        """收尾：走完最短展示时间后淡出并关闭。**必须保证最终 close() 被调用**。

        无论调用方后续是否出异常，动画都不会把用户困住 ——
        这是探针 `startup_check.py` 的重点守卫之一。
        """
        if self._closing:
            return
        self._stage = len(STAGES) - 1
        # 只置标志，实际淡出交给 _tick —— 那里统一管「最短展示时间」，
        # 否则启动很快时动画会一闪而过，比不显示还难受。
        self._closing = True
        self.update()

    def shutdown(self) -> None:
        """强制立刻关闭（兜底：主窗口构建失败时调用）。"""
        self._timer.stop()
        self._closing = True
        self._outro = 0.0
        self.close()

    # ------------------------------------------------------------ 动画循环
    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        self._t0 += dt
        # ★ 自己累加展示时长。**不能**用 `self._clock.elapsed()`：
        #   上面每帧都 restart() 了，elapsed() 恒等于「距上一帧的时长」(~16ms)，
        #   拿它跟 MIN_SHOW_MS 比较永远不成立 ⇒ 自动退场兜底形同虚设。
        self._shown_ms += dt * 1000.0

        if self._outro > 0.0:
            # 淡出：线性推进，够快不拖沓
            self._outro = min(1.0, self._outro + dt * 1000.0 / FADE_OUT_MS)
            if self._outro >= 1.0:
                self._timer.stop()
                self.close()
                self.finished.emit()
                return
        else:
            # 淡入：帧率无关缓动，约 0.35s 到满
            if self._alpha < 1.0:
                self._alpha = min(1.0, 1.0 - math.exp(-dt / 0.12))
            # ★ 兜底：两种收尾请求（正常 finish() / 阶段走完的自动退场）
            #   都必须过最短展示时间这一关，绝不出现「一闪而过」。
            if (self._stage >= len(STAGES) - 1
                    and self._shown_ms >= MIN_SHOW_MS):
                self._closing = True
                self._outro = 0.0001

        self.update()

    def paintEvent(self, e) -> None:      # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        # 整体透明度 = 淡入 × (1 − 淡出)
        a = self._alpha * (1.0 - self._outro)
        if a <= 0.01:
            p.end()
            return

        w, h = self.width(), self.height()

        # --- 卡面：白底 + 1px 描边 + 圆角（自绘，半透明背景下QSS 无效）
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), RADIUS, RADIUS)
        p.setPen(QPen(QColor(theme.PRIMARY_SOFT), 1))
        p.setBrush(QBrush(QColor(255, 255, 255, int(252 * a))))
        p.drawPath(path)
        p.setBrush(Qt.NoBrush)

        # --- 顶部一条主色渐变细线，做一点「品牌感」
        grad = QRadialGradient(QPointF(w / 2, 0), w)
        grad.setColorAt(0.0, QColor(201, 162, 39, int(210 * a)))   # 证书金
        grad.setColorAt(1.0, QColor(46, 111, 158, int(120 * a)))   # 主色
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(QRectF(RADIUS * 0.5, 0.5, w - RADIUS, 3), 2, 2)

        # --- 徽标：呼吸缩放（复用项目现成的徽标绘制，风格统一）
        #     呼吸周期约 1.8s，用 sin 做出「活着」的感觉
        breath = 1.0 + 0.035 * math.sin(self._t0 * 2 * math.pi / 1.8)
        side = LOGO_SIZE * breath
        pm = icons.logo_pixmap(int(side), dpr=2.0)
        p.setOpacity(a)
        # ★ 必须给「目标矩形」重载，不能用 `drawPixmap(x, y, pm)` ——
        #   后者是 1:1 逻辑像素绘制，会把 dpr=2 的高分辨率图按原尺寸塞进去（放大一倍）。
        #   ⚠️ 目标矩形重载只收 **QRect**（QRectF 仅三参数版有），
        #   传 QRectF 会 TypeError 且异常被 Qt 吞掉 ⇒ 表现为「徽标凭空消失」。
        p.drawPixmap(QRect(int((w - side) / 2), LOGO_TOP,
                           int(side), int(side)), pm)
        p.setOpacity(1.0)

        # --- 应用名
        f = QFont(self.font())
        f.setPointSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.TEXT))
        p.drawText(QRectF(0, LOGO_TOP + LOGO_SIZE + 14, w, 22),
                   Qt.AlignHCenter | Qt.AlignVCenter, "证书管理库")

        # --- 副标题
        f2 = QFont(self.font())
        f2.setPointSize(8)
        p.setFont(f2)
        p.setPen(QColor(theme.MUTED))
        p.drawText(QRectF(0, LOGO_TOP + LOGO_SIZE + 34, w, 18),
                   Qt.AlignHCenter | Qt.AlignVCenter, "CertVault")

        # --- 进度条（自绘，避开 Win11 原生外观）
        bx = (w - BAR_W) / 2.0
        track = QRectF(bx, BAR_TOP, BAR_W, BAR_H)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.PRIMARY_SOFT))
        p.drawRoundedRect(track, BAR_H / 2, BAR_H / 2)
        # 进度按阶段推进：第 4 段（就绪）满格
        ratio = (self._stage + 1) / float(len(STAGES))
        ratio = max(0.08, min(1.0, ratio))
        fill = QRectF(track.x(), track.y(), track.width() * ratio, track.height())
        p.setBrush(QColor(theme.PRIMARY))
        p.drawRoundedRect(fill, BAR_H / 2, BAR_H / 2)
        # 末端小圆点，强调「在动」
        p.setBrush(QColor(theme.GOLD))
        p.drawEllipse(QPointF(fill.right() - BAR_H / 2, track.center().y()),
                      BAR_H * 0.9, BAR_H * 0.9)

        # --- 阶段文案
        p.setFont(f2)
        p.setPen(QColor(theme.TEXT_SUB))
        p.drawText(QRectF(0, TEXT_TOP, w, 18),
                   Qt.AlignHCenter | Qt.AlignVCenter, STAGES[self._stage])

        p.end()

    # 收尾时也要重绘（透明度变化靠 update 驱动）
    def showEvent(self, e) -> None:        # noqa: N802
        super().showEvent(e)
        self.update()
