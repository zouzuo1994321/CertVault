# -*- coding: utf-8 -*-
"""通用 UI 组件：卡片、统计块、状态徽章、空状态、条形分布图等。"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

import math

from PySide6.QtCore import (QElapsedTimer, QObject, QPointF, QRectF, QSize, Qt,
                            QTimer, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QPainter,
                           QPainterPath, QPen, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import (QComboBox, QDateEdit, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QSpinBox,
                               QStyle, QStyleOptionSpinBox, QVBoxLayout,
                               QWidget)

from . import icons, theme


# ------------------------------------------------------------------- 卡片
#
# --------------------------------------------- Live2D 式「视角跟随」（卡片版）
#
# 与 GazeLogo 同一套观感：归一化视线向量 + 缓动 + 待机回正，但做法不同 ——
# 徽标是可以随便平移绘制的图形，而卡片的内容由 QLayout 摆放，直接 ``move()``
# 子控件会被下一次布局 pass 覆盖回去。
#
# ★★ v1.1.9 起：动的是**整块模块**，不是模块里的文字。
#
# 上一版把位移做在「卡片内层布局的边距」上，于是白底 / 边框 / 圆角纹丝不动，
# 只有文字和图标在框里滑 —— 读起来是「框不动、字在滑」，不像模块在动。
#
# 现在给卡片开出一圈「走位余量」(inset)：宿主控件（= 布局项）的几何**永远不变**，
# 而卡面改为自绘，连同内容一起在这圈余量里平移：
#
#     可视卡面 = rect() 每边内缩 (inset_x + dx, inset_y + dy)
#     内容边距 = (inset_x + dx + pad, inset_y + dy + pad, inset_x - dx + pad, ...)
#
# 两者共用同一个 (dx, dy)，所以「白底 / 边框 / 圆角 / 文字 / 图标」是一个整体在动。
# 对面两条边距之和恒为 2·inset + 2·pad → sizeHint 分毫不变 → 父布局不可能重排。
# **零重排是结构上保证的**（不碰父布局、不碰任何 QWidget 几何），不再依赖
# 「一条边加、对边减」的算术巧合。
#
# 层次感仍靠嵌套布局各移一份：图标徽标在整卡位移之外**再**多走一份（= 离眼睛更近），
# 分布图条形用亚像素自绘再平移一份。
#
# 最像「玻璃反光」的那两层（卡面柔光 + 悬停描边）也走 paintEvent，一点几何都不碰，
# 只是现在必须跟着**可视卡面**走，而不是贴着控件矩形走。
#
# 开了余量的页要把布局边距 / 间距等量让出来（见 ``pages.DashboardPage``），
# 让完之后静止位形与改造前**逐像素一致**；没开余量的卡片 inset=(0,0)，行为与从前完全相同。
#
# 四层动效叠起来才「活」：
#   ① 视线视差  鼠标一动，各层按不同幅度滑移（布局边距 / 自绘平移）
#   ② 待机呼吸  鼠标停下后视线缓缓松开，改由一条 7s 正弦接管
#   ③ 入场编排  切回首页时各模块按索引依次上浮回弹，并带一层柔光脉冲
#   ④ 交互反馈  悬停的那张卡片跟随幅度放大到 1.85 倍 + 描边亮起，按下时下沉 1px
#
# 流畅性靠三件事，缺一个都会「一顿一顿的」：
#   · dt 驱动的帧率无关缓动（换 30fps / 60fps 手感一致，掉帧也不跳）
#   · 位移量化到整数像素 + 边距未变就早退 → 静止时几乎不触发重排
#   · 重绘按「量化后的关键点」节流 → 静态时每张卡每秒只刷几次，动起来才逐帧
#
# ⚠️ 抗抖三忌（v1.1.8 用 `tools/jitter_check.py` 量出来的，别再犯）：
#   ① 悬停**不要**放大位移幅度 —— 鼠标划过一排卡片时，每张卡轮流把位移拉大
#      85%，实测单帧跳变 7px，是「抖得厉害」的头号来源。
#   ② 量化**必须带死区 + 滞回** —— 裸 round() 在浮点值擦过 n.5 时会左右翻档。
#   ③ 入场**不要留 1px 的慢爬尾巴** —— 尾部「停 0.2s、跳 1px、再停」连在一起
#      就是「一跳一跳」，回摆（过冲）那 1px 更是纯粹添乱。

GAZE_CARD_PX = 6.0      # ★ 整块模块（白底 + 边框 + 圆角 + 内容）的位移幅度
GAZE_INSET_X = 6        # ★ 横向走位余量（整数像素）：可视卡面从宿主每边内缩这么多
GAZE_INSET_Y = 8        # ★ 纵向走位余量。视线位移与「入场上浮 8px」会叠加，
                        #   所以起底取入场幅度；`_fit_shift` 保证任何时刻都顶不出
                        #   余量（顶出去就会被宿主裁掉一条边）
GAZE_BADGE_PX = 6.0     # 图标徽标在整卡位移之上的**额外**位移，二者叠加成层次
GAZE_BADGE_BOX = 64     # 徽标容器边长（徽标本体 40）—— 每边留 12px 走位余量，
                        # 于是 ±12px 的总位移也顶不出容器被裁掉，全程只用非负边距
GAZE_CHART_PX = 3.0     # 分类分布图在整卡位移之外的额外视差
GAZE_TAU = 0.17         # 视线缓动时间常数（秒）—— 帧率无关
GAZE_FPS = 60           # 采样帧率
GAZE_HOVER_GAIN = 0.0   # 悬停**不**叠加位移幅度。曾经是 0.85（1.0 → 1.85 倍），
                        # 结果划过一排卡片时位移单帧猛跳 7px —— 典型的「抖」。
                        # 悬停的表达交给柔光提亮 + 双圈描边 + 按下下沉，都已够用。
GAZE_HOVER_TAU = 0.16   # 悬停进出缓动（秒）。原来硬编码 0.09s，太快，亮度与描边
                        # 像「闪」；放到和视线同量级才柔和。
GAZE_DEAD_ZONE = 0.36   # 位移死区（像素）：浮点位移比它还小就归零，
                        # 免得 0/1 两档在静止边缘反复翻（那是最刺眼的抖）
GAZE_HYST = 0.12        # 量化滞回（格）：新档位要比当前档多跨 0.12 格才切换
GAZE_SNAP = 0.0025      # 视线与目标差小于它就吸附（视线真正停住，不再无限逼近）
BREATH_PERIOD = 7.0     # 待机呼吸周期（秒）
IDLE_AFTER = 1.35       # 光标静止多久算「待机」（秒）
IDLE_TAU = 0.55         # 待机系数本身的缓动（秒）。★ 待机开关不能是硬切：
                        # 一次「松开 → 被手抖拉回」就是一次整页摆动，而
                        # 慢速拖动很容易被误判成禁止 → 反复开关就是「抖」。
                        # 把系数做成连续量，即使判定反复，画面也只是微微起伏。
IDLE_RELAX = 0.55       # 待机时视线松开多少（1.0 → 0.45 倍）
ENTER_LIFT = 8          # 入场时内容从下方多少像素浮上来（10 → 8，幅度小了台阶就少）
ENTER_DURATION = 0.68   # 单张卡的入场时长（秒）。0.52 → 0.68：台阶率降三分之一，
                        # 「一格一格」感明显减弱
ENTER_STAGGER = 0.055   # 相邻模块的入场错峰（秒）
ENTER_TAIL = 0.48       # 入场进度过此值且剩余 ≤1px → 直接吸附收尾（不留 1px 慢爬）
ROLL_DURATION = 0.62    # 统计数字滚动时长（秒）
GROW_DURATION = 0.55    # 单条分布条的生长时长（秒）
GROW_STAGGER = 0.05     # 相邻分布条的生长错峰（秒）


def _ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3


def _ease_out_quint(t: float) -> float:
    """更「先快后极慢」的缓出：85% 的距离在前 40% 的时间里走完。

    入场位移用它 —— 位移只剩最后一两个像素时速度已经极低，不会拖出一条
    「停 0.2s、跳 1px」的尾巴（那段尾巴连起来就是「一跳一跳」）。
    """
    return 1.0 - (1.0 - t) ** 5


# 入场**不再**用过冲（easeOutBack）：它会让内容冲过目标再回摆 1px，那 1px
# 回摆没有任何观感收益，却正好落在「读作抖动」的尺度上。实测确认后删掉。


class GazeScene(QObject):
    """整页「视角跟随」的编排器：一个定时器驱动视线、呼吸、悬停与入场。

    为什么做成一页一个而不是每张卡片各起一个定时器：一页十几张卡各跑 60fps
    纯属浪费，而且各自的缓动相位会错开、整页看起来是散的。一个场统一广播，
    所有卡片共享同一条视线，观感才统一。
    """

    gaze_changed = Signal(float, float, float, float)   # gx, gy, breath, hover
    tick = Signal(float)                                # dt（秒）——数值滚动/图表生长挂这里

    def __init__(self, host: QWidget, ref: float = 640.0, tau: float = GAZE_TAU,
                 fps: int = GAZE_FPS, parent: Optional[QObject] = None) -> None:
        super().__init__(parent if parent is not None else host)
        self._host = host
        self._ref = float(ref)      # 视线饱和距离：鼠标离页面中心这么远时位移打满
        self._tau = float(tau)
        self._targets: List[list] = []      # [widget, follow, hover, hover_cur]
        self._gx = self._gy = 0.0   # 当前视线（已缓动）
        self._breath = 0.0
        self._phase = 0.0
        self._idle = 0.0
        self._idle_f = 0.0          # 待机系数（0 = 跟手，1 = 完全待机），连续量
        self._mouse = QCursor.pos()
        self._enter_req: Optional[tuple] = None
        self._enter_elapsed = -1.0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)   # 别让系统把 60fps 抖成 40fps
        self._timer.setInterval(max(8, int(round(1000.0 / max(1, fps)))))
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ---------------------------------------------------------- 对外接口
    def add(self, widget, follow: bool = True, hover: bool = True) -> None:
        """登记一个跟随目标；widget 需实现 set_gaze / play_enter / tick_enter。"""
        self._targets.append([widget, bool(follow), bool(hover), 0.0])

    def play_enter(self, first_delay: float = 0.06, duration: float = ENTER_DURATION,
                   stagger: float = ENTER_STAGGER) -> None:
        """请求一次入场编排；真正开播会等宿主窗口可见，免得启动那一刻白演。"""
        self._enter_req = (float(first_delay), float(duration), float(stagger))

    def set_gaze(self, gx: float, gy: float) -> None:
        """绕过采样直接摆姿势（效果图工具 / 验收探针用，记得先 stop()）。"""
        self._gx, self._gy = float(gx), float(gy)
        self._breath = 0.0          # 一并归零，摆出来的姿势才可复现
        for rec in self._targets:
            rec[3] = 0.0
        self._broadcast()

    def settle(self) -> None:
        """把入场与所有附属动画一步推到终态，并把视线与呼吸归零。

        效果图 / 冒烟截图必须先调它：否则很可能抓到动画半途（内容还悬着、
        柔光脉冲正亮、数字正滚到一半），截图就不可复现了。

        ★ 视线与呼吸也要归零：柔光的**位置与强度**是它们的函数，不归零的话
        同一份代码两次截图能差出十来个 alpha —— 逐像素比对就没法用了。
        （GazeLogo 有自己的时钟，不受影响，比对时绕开它那块区域即可。）
        """
        self._enter_req = None
        self._enter_elapsed = -1.0
        self._gx = self._gy = 0.0
        self._breath = 0.0
        self._idle = 0.0
        self._idle_f = 0.0
        for rec in self._targets:
            rec[3] = 0.0                # 悬停分量一并归零
        self._broadcast()
        for rec in self._targets:
            rec[0].tick_enter(1e6)      # k 远超 1 → 直接收尾
            rec[0].finish_anim()
        self._gx = self._gy = 0.0
        self._breath = 0.0
        self._idle = 0.0
        self._idle_f = 0.0
        for rec in self._targets:
            rec[3] = 0.0
        self._broadcast()

    def stop(self) -> None:
        self._timer.stop()

    def start(self) -> None:
        if not self._timer.isActive():
            self._clock.restart()
            self._timer.start()

    @property
    def breath(self) -> float:
        return self._breath

    # ---------------------------------------------------------- 内部
    def _broadcast(self) -> None:
        for rec in self._targets:
            w, follow, _hover, hov = rec
            if follow:
                gain = 1.0 + GAZE_HOVER_GAIN * hov
                gx, gy = self._gx * gain, self._gy * gain
            else:
                gx = gy = 0.0
            w.set_gaze(gx, gy, self._breath, hov)

    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        if dt <= 0.0:
            return
        dt = min(dt, 0.05)          # 卡顿/休眠回来时别让缓动一步跳到位
        host = self._host
        win = host.window() if host is not None else None
        active = bool(host is not None and host.isVisible()
                      and (win is None or win.isActiveWindow()))
        gp = QCursor.pos() if active else None
        if active:
            # ★ 门槛用 >=2 而不是 >2：慢速拖动恰好是 2px/帧，用 >2 会把
            #   「正在缓慢移动鼠标」误判成待机 —— 1.35 秒后视线突然松开，
            #   再被下一次微动拉回，整页来回摆一下，看着就是抖。
            if abs(gp.x() - self._mouse.x()) + abs(gp.y() - self._mouse.y()) >= 2:
                self._mouse = gp
                self._idle = 0.0
            else:
                self._idle += dt
            c = host.mapToGlobal(host.rect().center())
            tx = max(-1.0, min(1.0, (gp.x() - c.x()) / self._ref))
            ty = max(-1.0, min(1.0, (gp.y() - c.y()) / self._ref))
        else:
            tx = ty = 0.0
            self._idle = 0.0

        # 待机系数做成连续量：判定即使反复，出来的也只是缓缓起伏，不是硬切
        ia = 1.0 - math.exp(-dt / IDLE_TAU)
        self._idle_f += ((1.0 if self._idle > IDLE_AFTER else 0.0) - self._idle_f) * ia
        relax = 1.0 - IDLE_RELAX * self._idle_f
        tx *= relax
        ty *= relax

        a = 1.0 - math.exp(-dt / self._tau)     # ★ 帧率无关的一阶缓动
        # 指数逼近永远「差一点点」，于是浮点位移会在某个量化边界附近长期游走。
        # 差得足够小就直接吸附 —— 视线真正停住，位移才可能彻底冻结。
        if abs(tx - self._gx) < GAZE_SNAP:
            self._gx = tx
        else:
            self._gx += (tx - self._gx) * a
        if abs(ty - self._gy) < GAZE_SNAP:
            self._gy = ty
        else:
            self._gy += (ty - self._gy) * a

        speed = 1.0 + 0.6 * self._idle_f        # 待机时呼吸更深一点
        self._phase = (self._phase + dt * speed / BREATH_PERIOD) % 1.0
        self._breath = math.sin(self._phase * math.tau)

        # 悬停缓动（原来 0.09s 太快：亮度与描边是「闪」而不是「亮起来」）
        ha = 1.0 - math.exp(-dt / GAZE_HOVER_TAU)
        for rec in self._targets:
            w, _f, hover, cur = rec
            goal = 0.0
            if hover and gp is not None and w.isVisible():
                if w.rect().contains(w.mapFromGlobal(gp)):
                    goal = 1.0
            rec[3] = cur + (goal - cur) * ha

        self._advance_enter(dt)
        self._broadcast()
        self.tick.emit(dt)

    def _advance_enter(self, dt: float) -> None:
        if self._enter_req is not None:
            host = self._host
            win = host.window() if host is not None else None
            if win is not None and win.isVisible() and win.isActiveWindow():
                first, dur, stagger = self._enter_req
                self._enter_req = None
                self._enter_elapsed = 0.0
                for i, rec in enumerate(self._targets):
                    rec[0].play_enter(first + i * stagger, dur)
        if self._enter_elapsed < 0.0:
            return
        self._enter_elapsed += dt
        alive = False
        for rec in self._targets:
            if rec[0].tick_enter(dt):
                alive = True
        if not alive:
            self._enter_elapsed = -1.0


class GazeCard:
    """给卡片加「视角跟随 + 待机呼吸 + 悬停反馈 + 入场编排」的混入。

    v1.1.9 起位移发生在**整块模块**上：宿主控件几何不动，卡面自绘并且和内容
    一起在「走位余量」里平移（见文件顶部说明）。柔光与描边走 paintEvent。
    刻意**不**旋转文字 —— 卡片一转，中文字就发虚；位移 + 反光两层已经足够
    表达「它在看你」，可读性还一点没丢。
    """

    GAZE_ENABLED = True
    GAZE_GLOW = True        # 是否画卡面柔光（大卡片可以关掉，省一次整卡重绘）
    GAZE_GLOW_Q = 1.5       # 柔光位置的量化步长（像素）：越大越省，视觉上看不出来
    CARD_RADIUS = 12.0      # 卡面圆角，须与 theme.py 的 `QFrame#Card` 保持一致
    CARD_BORDER = 1         # 卡面描边宽度。★ 这 1px 必须手工补进内容边距：
                            #   QSS 的 `border: 1px solid` 会占掉内容区 1px，
                            #   改成自绘后 QSS 不再介入，不补就会让整卡内容
                            #   左上偏 1px（截图逐像素比对一测就露）

    def gaze_setup(self, padding: int = 16, amp: float = GAZE_CARD_PX,
                   glow: bool = True, glow_q: float = 1.5) -> None:
        self._pad = int(padding)
        self._amp = float(amp)
        # 走位余量：0 = 不开，卡片行为与 v1.1.8 完全一致（位移为零）
        self._inset_x = 0
        self._inset_y = 0
        # 上一次真正落到画面上的位移（已量化、已夹紧）。自绘卡面与柔光都要靠它
        # 算出「可视卡面」矩形 —— 位移只此一份来源，不会出现两个通道各走各的。
        self._last_dx = 0
        self._last_dy = 0
        self._last_ex = 0
        self._gaze_on = False
        self._gx = self._gy = 0.0
        self._breath = 0.0
        self._hover = 0.0
        self._press_dy = 0
        self._enter_off = 0
        self._enter_t = 1.0
        self._enter_delay = 0.0
        self._enter_dur = ENTER_DURATION
        self._enter_clock = 0.0
        self._enter_playing = False
        self._margin_key: Optional[tuple] = None
        self._paint_key: Optional[tuple] = None
        # 各条位移通道上一次量化出的整数档（key → (x, y)），抗抖靠它做滞回
        self._qprev: Dict[str, tuple] = {}
        self.GAZE_GLOW = bool(glow)
        self.GAZE_GLOW_Q = float(glow_q)

    # ---------------------------------------------------------- 对外
    def set_move_room(self, ix: float, iy: float) -> None:
        """开出一圈「走位余量」：可视卡面从宿主控件每边内缩 (ix, iy)。

        ★ 这是「整块模块会动」的关键。宿主控件（= 父布局里的那个 item）几何
        永远不变；自绘卡面 + 内容一起在这圈余量里平移，于是白底、边框、圆角、
        文字、图标是同一个整体在动。位移完全不经过父布局 → 零重排是**结构上**
        保证的，不依赖任何算术巧合。

        代价：宿主比可视卡面大 2·(ix, iy)。承载它的页面要把布局边距与间距等量
        让出来，静止位形才不会变（见 ``pages.DashboardPage``）。
        """
        self._inset_x = int(round(ix))
        self._inset_y = int(round(iy))
        self._sync_move_room()
        self._margin_key = None
        self._apply_gaze()

    def _sync_move_room(self) -> None:
        """余量变化后同步宿主自身尺寸；默认无事可做。"""

    def set_gaze_enabled(self, on: bool = True) -> None:
        self._gaze_on = bool(on)
        if not on:
            self._gx = self._gy = self._breath = self._hover = 0.0
            self._qprev.clear()
            self._margin_key = None
            self._apply_gaze()
        self._paint_key = None
        self.update()

    def set_gaze(self, gx: float, gy: float, breath: float = 0.0,
                 hover: float = 0.0) -> None:
        if not self._gaze_on:
            return
        self._gx, self._gy = float(gx), float(gy)
        self._breath, self._hover = float(breath), float(hover)
        self._apply_gaze()
        self._maybe_repaint()

    def play_enter(self, delay: float = 0.0, duration: float = ENTER_DURATION) -> None:
        self._enter_delay = max(0.0, float(delay))
        self._enter_dur = max(0.10, float(duration))
        self._enter_clock = 0.0
        self._enter_t = 0.0
        self._enter_playing = True
        self._margin_key = None
        self._apply_gaze()
        self._paint_key = None
        self.update()

    def tick_enter(self, dt: float) -> bool:
        if not self._enter_playing:
            return False
        self._enter_clock += dt
        k = (self._enter_clock - self._enter_delay) / self._enter_dur
        if k < 0.0:
            return True
        if k >= 1.0:
            self._finish_enter()
            return False
        off = int(round((1.0 - _ease_out_quint(k)) * ENTER_LIFT))
        # 尾部吸附：进度过了 ENTER_TAIL、剩余只有 1px 时直接收尾。
        # 否则最后那 1px 会爬好几百毫秒 —— 「停一会、跳 1px、再停一会」
        # 连起来读就是一跳一跳的抖动，前面几十帧的顺滑全被它毁掉。
        if k >= ENTER_TAIL and off <= 1:
            self._finish_enter()
            return False
        self._enter_off = off
        self._enter_t = k
        self._margin_key = None
        self._apply_gaze()
        self._paint_key = None
        self.update()
        return True

    def finish_anim(self) -> None:
        """把附属动画（数字滚动 / 条形生长）推到终态；基类没有，留空。"""
        if self._enter_playing:
            self._finish_enter()

    # ---------------------------------------------------------- 内部
    def _finish_enter(self) -> None:
        self._enter_playing = False
        self._enter_t = 1.0
        self._enter_off = 0
        self._margin_key = None
        self._apply_gaze()
        self._paint_key = None
        self.update()
    def _offsets(self, amp: float, slot: str = "main") -> tuple:
        """把浮点位移量化成整数像素 —— 带**死区 + 滞回**。

        裸 `int(round(v))` 有两处会让画面「抖」：

        * **边界翻转**：浮点位移擦着 n.5 走时，`round` 会在 n / n+1 之间
          左右翻档，一帧一跳。加滞回 —— 新档位必须比当前档多跨 `GAZE_HYST`
          格才切，等于给每条通道装上一条「回差」。
        * **零附近抖动**：视线接近回中时浮点位移在 ±0.5 内游走，同样是翻档。
          加死区 —— 比 `GAZE_DEAD_ZONE` 小就直接归零。

        代价是最大约 0.5px 的量化误差，换掉整片抖动，非常划算。
        """
        prev = self._qprev.get(slot, (0, 0))
        qx = self._quant(self._gx * amp, prev[0])
        qy = self._quant(self._gy * amp, prev[1])
        self._qprev[slot] = (qx, qy)
        return qx, qy

    @staticmethod
    def _quant(v: float, prev: int) -> int:
        if abs(v) < GAZE_DEAD_ZONE:
            return 0
        target = int(round(v))
        if target == prev:
            return prev
        if abs(v - prev) < 0.5 + GAZE_HYST:     # 没跨过「半格 + 回差」就不换档
            return prev
        return target

    @staticmethod
    def _fit_shift(d: int, lo: int, hi: int) -> int:
        """把位移夹进「这对边距还撑得住」的范围。

        ★★ QLayout 的边距一旦有任何一个为负，`getContentsMargins()` 会**整组**
        退回 QStyle 默认值（Windows 上是 9）。于是左内边距从 -1 一帧之内变成 9，
        内容横移 10px —— 探针抓到的那个 9px 大跳变就是它。位移必须夹住，
        而且夹的是「用出去的那份」，`+d / -d` 仍成对，内外之和不变，
        所以父布局不会跟着重排。
        """
        return max(-lo, min(hi, d))

    def _dy_extra(self) -> int:
        """入场上浮 + 按下下沉，两者的纵向偏移合并进同一条边距通道。"""
        return self._enter_off + self._press_dy

    def _apply_gaze(self) -> None:
        raise NotImplementedError

    # ---------------------------------------------------- 可视卡面（整块模块）
    def _vis_rect(self) -> QRectF:
        """当前「可视卡面」矩形 —— 白底 / 边框 / 圆角就画在这里。

        = 宿主矩形每边内缩余量，再整体平移上一次真正落地的 (dx, dy + 入场上浮)。
        没开余量且静止时它正好收敛成 ``rect()`` 本身，与改造前逐像素一致。
        """
        ix, iy = self._inset_x, self._inset_y
        dx, dy = self._last_dx, self._last_dy + self._last_ex
        return QRectF(self.rect()).adjusted(ix + dx, iy + dy, -ix - dx, -iy - dy)

    def _paint_card_face(self, p: QPainter) -> None:
        """自绘卡面：白底 + 1px 描边 + 12px 圆角（参数与 QSS ``QFrame#Card`` 对齐）。

        为什么不用 QSS 画底：QSS 的底永远贴着控件矩形，控件不动它就不动 ——
        那正是「框不动、字在滑」的根因。改成自绘之后**整块卡面**才能随视线平移，
        而宿主控件（= 布局项）的几何分毫不动，于是没有任何重排风险。
        """
        r = self._vis_rect()
        rad = self.CARD_RADIUS
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(r, rad, rad)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.CARD))
        p.drawPath(path)
        pen = QPen(QColor(theme.BORDER))
        pen.setWidthF(1.0)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        # 内缩半像素：1px 描边才正好压在最外那一圈像素上（与 QSS 的观感一致）
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), rad - 0.5, rad - 0.5)

    def _glow_point(self, w: float, h: float) -> Tuple[float, float]:
        """柔光中心：视线主导 + 呼吸带来的缓慢漂移（漂移够慢，才敢大幅节流量化）。"""
        return (w * (0.5 + self._gx * 0.36 + self._breath * 0.05),
                h * (0.5 + self._gy * 0.42 + self._breath * 0.04))

    def _enter_pulse(self) -> float:
        """入场柔光脉冲：开播最亮、随进场幂次淡回 0 —— 给入场一个「亮起来」的读点。"""
        if not self._enter_playing:
            return 0.0
        return max(0.0, 1.0 - self._enter_t) ** 1.5

    def _paint_signature(self) -> tuple:
        q = max(0.05, self.GAZE_GLOW_Q)
        r = self._vis_rect()        # 柔光中心跟着**可视卡面**走，不跟控件矩形走
        gx, gy = self._glow_point(r.width(), r.height())
        return (int(round((r.x() + gx) / q)), int(round((r.y() + gy) / q)),
                int(round(self._hover * 10)),
                int(round((1.0 - self._enter_t) * 10)) if self._enter_playing else 0)

    def _maybe_repaint(self, force: bool = False) -> None:
        if not self.GAZE_GLOW and self._hover <= 0.004:
            return
        sig = self._paint_signature()
        if force or sig != self._paint_key:
            self._paint_key = sig
            self.update()

    def _paint_gaze(self, widget) -> None:
        """卡面柔光 + 悬停描边。两者都只碰画笔，不动任何几何，所以永远不抖。"""
        if not getattr(self, "_gaze_on", False):
            return
        hover = self._hover
        pulse = self._enter_pulse()
        if not self.GAZE_GLOW and hover <= 0.004 and pulse <= 0.002:
            return
        # ★ 一切以「可视卡面」为坐标系：卡面整体平移后，柔光与描边必须跟着走，
        #   否则会看到「卡片滑走了、反光还留在原地」。
        r = self._vis_rect()
        rad = self.CARD_RADIUS - 0.5
        w, h = float(r.width()), float(r.height())
        p = QPainter(widget)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self.GAZE_GLOW:
            # 柔光要裁进圆角，否则方形的渐变会糊到卡片外面
            p.save()
            path = QPainterPath()
            path.addRoundedRect(r.adjusted(1.0, 1.0, -1.0, -1.0), rad, rad)
            p.setClipPath(path)
            gx, gy = self._glow_point(w, h)
            cx, cy = r.x() + gx, r.y() + gy
            # 柔光强度：呼吸时轻轻起伏，悬停时明显提亮，入场时先「点一下」再回落
            hot = 30 + int(14 * max(0.0, self._breath)) + int(30 * hover)
            hot += int(40 * pulse)
            # 半径绑「可视卡面 + 走位余量」= 宿主尺寸：卡面在余量里平移时半径
            # 一分不变。若按可视矩形尺寸算，半径会恒小 2%，柔光落点整体偏移，
            # 静止位形就与上一版对不上了（截图逐像素比对能直接量出来）。
            gw = w + 2 * self._inset_x
            gh = h + 2 * self._inset_y
            g = QRadialGradient(QPointF(cx, cy), max(gw, gh) * 0.68)
            g.setColorAt(0.0, QColor(46, 111, 158, hot))
            g.setColorAt(0.45, QColor(46, 111, 158, max(4, hot // 3)))
            g.setColorAt(1.0, QColor(46, 111, 158, 0))
            p.setPen(Qt.NoPen)
            p.setBrush(g)
            p.drawRect(r)
            p.restore()
        if hover > 0.004:
            # 描边**不能**跟着柔光一起做内缩裁剪：它就是画在贴边那一圈上的，
            # 被裁掉 1px 后基本什么都不剩（这里踩过）。改为独立绘制。
            # 两圈：贴边一圈把原来的浅灰描边染成主色，再用更宽更淡的一圈做出
            # 「边缘发光」的过渡，免得只是一根硬线。
            p.setBrush(Qt.NoBrush)
            pen = QPen(QColor(46, 111, 158, int(46 * hover)))
            pen.setWidthF(2.6)
            p.setPen(pen)
            p.drawRoundedRect(r.adjusted(2.6, 2.6, -2.6, -2.6), rad - 1.3, rad - 1.3)
            pen = QPen(QColor(46, 111, 158, int(150 * hover)))
            pen.setWidthF(1.5)
            p.setPen(pen)
            p.drawRoundedRect(r.adjusted(1.0, 1.0, -1.0, -1.0), rad, rad)
        p.end()


class Card(QFrame, GazeCard):
    """圆角白卡片，可带标题与右上角操作区。

    ``room`` 是「走位余量」：大于 0 时这张卡片会**整块**（白底 + 边框 + 圆角 +
    文字 + 图标）跟着视线平移。承载它的页面必须把布局边距与间距等量让出来，
    静止位形才不会比别人胖一圈（见 ``pages.DashboardPage``）。
    """

    def __init__(self, title: str = "", hint: str = "", parent: Optional[QWidget] = None,
                 padding: int = 16, glow: bool = True, glow_q: float = 1.5,
                 room: Tuple[float, float] = (0, 0)) -> None:
        super().__init__(parent)
        # ★ 卡面不再交给 QSS 画。`QFrame#Card` 的底永远贴着**控件矩形**，控件不动
        #   它就不动 —— 那正是「框不动、字在滑」。这里换个 objectName 让 QSS 让位，
        #   底与描边改由 `_paint_card_face` 自绘，整块卡面才能跟着视线平移。
        self.setObjectName("CardBox")
        self.setFrameShape(QFrame.NoFrame)
        # glow=False 的卡片省掉整卡重绘，代价是失去「玻璃反光」—— 大卡片用得上
        self.gaze_setup(padding, glow=glow, glow_q=glow_q)
        self._v = QVBoxLayout(self)
        # +CARD_BORDER：自绘卡面后 QSS 不再占那 1px，得自己补回来
        self._v.setContentsMargins(padding + self.CARD_BORDER,
                                   padding + self.CARD_BORDER,
                                   padding + self.CARD_BORDER,
                                   padding + self.CARD_BORDER)
        self._v.setSpacing(12)
        self.head = QHBoxLayout()
        self.head.setSpacing(8)
        if title:
            self.title = QLabel(title)
            self.title.setObjectName("CardTitle")
            self.head.addWidget(self.title)
            if hint:
                self.hint = QLabel(hint)
                self.hint.setObjectName("CardHint")
                self.head.addWidget(self.hint)
            self.head.addStretch(1)
            self._v.addLayout(self.head)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self._v.addLayout(self.body, 1)
        self.set_move_room(*room)       # 布局搭好之后再开余量（_apply_gaze 要改 _v）

    def _apply_gaze(self) -> None:
        ix, iy = self._inset_x, self._inset_y
        pad = self._pad
        gdx, gdy = self._offsets(self._amp, "main")
        # 位移夹进走位余量：夹住后仍成对加/减，内外之和不变 → sizeHint 不变
        dx = self._fit_shift(gdx, ix, ix)
        dy = self._fit_shift(gdy, iy, iy)
        # 入场上浮 / 按下下沉叠加在同一条纵向通道上，同样不许顶出余量
        ex = self._fit_shift(self._dy_extra(), iy + dy, iy - dy)
        self._last_dx, self._last_dy, self._last_ex = dx, dy, ex
        bp = pad + self.CARD_BORDER      # 描边那 1px 要算进内容偏移（见 CARD_BORDER）
        m = (ix + dx + bp, iy + dy + ex + bp, ix - dx + bp, iy - dy - ex + bp)
        if m == self._margin_key:
            return
        self._margin_key = m
        self._v.setContentsMargins(*m)
        self.update()       # ★ 卡面是自绘的：位移变了必须显式请求重绘

    def paintEvent(self, event) -> None:  # noqa: N802
        # ★ 不调 super()：QSS 的卡面已让位（objectName 换掉了），
        #   底与描边全部自绘 —— 这样整块卡面才能跟着视线一起平移。
        p = QPainter(self)
        self._paint_card_face(p)
        p.end()
        self._paint_gaze(self)

    def add(self, w) -> None:
        if isinstance(w, QWidget):
            self.body.addWidget(w)
        else:
            self.body.addLayout(w)

    def add_head_widget(self, w: QWidget) -> None:
        self.head.addWidget(w)

    # 这里原本有个 shadow()，用 QGraphicsDropShadowEffect 做投影 —— v1.1.9 删掉了。
    # 图形特效会把**整个控件**（含走位余量）渲染进离屏缓冲再整体偏移：既贵
    # （每帧一次离屏合成），卡面又会跟着控件矩形走 —— 位移一开就和卡片脱节。
    # 要做投影得在 `_paint_card_face` 里自绘（且只能落在走位余量之内）。


class StatCard(QFrame, GazeCard):
    """统计数据块：左侧色条 + 大数字 + 说明。数字支持滚动到位。"""

    clicked = Signal()

    _L, _T, _R, _B = 4, 14, 16, 14     # 布局基线，_apply_gaze 在此基础上加减

    def __init__(self, label: str, value: str, color: str, icon_name: str = "",
                 unit: str = "本", parent: Optional[QWidget] = None,
                 room: Tuple[float, float] = (0, 0)) -> None:
        super().__init__(parent)
        # 卡面自绘（同 Card，理由见那里）
        self.setObjectName("CardBox")
        self.setFrameShape(QFrame.NoFrame)
        # 固定高度：统计卡横排所在的 QHBoxLayout 没有纵向伸缩项，一旦同页的
        # 表格被隐藏（例如考试计划为空、只显示空态），多余高度就会平分到这几张
        # 卡上，把 96px 的卡片抻成两百多像素的大色块。这里直接钉死高度。
        # （开了走位余量后宿主比可视卡面高 2·inset_y，set_move_room 会补上。）
        self._base_h = 96          # 可视卡面的高度
        self.setFixedHeight(self._base_h)
        self.setCursor(Qt.PointingHandCursor)
        self.gaze_setup(0, glow=True, glow_q=0.8)
        bw = self.CARD_BORDER        # 自绘卡面后 QSS 不再占那 1px，得自己补回来
        lay = QHBoxLayout(self)
        # 左边距 1(描边) + 4 + 徽标容器 64 + 间距 0
        #   == 原来的 1(边框) + 8 + 56 + 4，且徽标在容器内居中（每边 12）后
        #   视觉左边距 17、徽标到文字间距 12 也全部对得上 →
        #   静止位形与改造前**逐像素一致**，多出来的只是走位余量。
        lay.setContentsMargins(self._L + bw, self._T + bw,
                               self._R + bw, self._B + bw)
        lay.setSpacing(0)
        self._lay = lay

        # 徽标单独装一层「比它大一圈」的盒子：盒子里多出来的 24px 是走位余量，
        # 使徽标能在正文位移之外**再**多移一点（近处动得多），做出视差层次。
        # 全程只改嵌套布局的边距，不碰 move()，也就不会跟 QLayout 抢几何；
        # 容器大一圈保证位移不会被父控件裁掉。
        self._badge_box = QWidget(self)
        self._badge_box.setFixedSize(GAZE_BADGE_BOX, GAZE_BADGE_BOX)
        bb = QHBoxLayout(self._badge_box)
        self._badge_base = (GAZE_BADGE_BOX - 40) // 2          # = 12
        bb.setContentsMargins(self._badge_base, self._badge_base,
                              self._badge_base, self._badge_base)
        self._badge_lay = bb

        badge = QLabel()
        badge.setFixedSize(40, 40)
        badge.setPixmap(icons.pixmap(icon_name or "cert", color, 22))
        badge.setStyleSheet(
            f"background:{_tint(color)}; border-radius:10px; padding:9px;")
        badge.setAlignment(Qt.AlignCenter)
        bb.addWidget(badge)
        self.badge = badge
        lay.addWidget(self._badge_box)

        # ★ 单位必须紧跟在数字后面，不能单独右对齐到卡片另一端。
        #   曾经的写法是 `lay.addWidget(unit_lbl)` + `AlignRight|AlignBottom`：
        #   单位被推到卡片最右侧，离数字有一整个卡片的宽度；而 AlignBottom 让它
        #   贴着内容区底边 —— 于是「本」比标签还低 7px，读起来就是
        #   **数字和文字错位**（宽卡尤其明显：404px 的卡里数字在 x=69、单位在 x=375）。
        #   现在把单位并进数字那一行、改用「基线对齐」（见 _align_unit）。
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addStretch(1)               # 上下各一条弹性 → 数字+标签整组在卡内居中

        self._value_row = QHBoxLayout()
        self._value_row.setContentsMargins(0, 0, 0, 0)
        self._value_row.setSpacing(7)   # 数字与单位之间留一个字的呼吸
        self.value_lbl = QLabel(value)
        self.value_lbl.setObjectName("BigNum")
        self.value_lbl.setStyleSheet(f"color:{color};")
        self._value_row.addWidget(self.value_lbl)

        self.unit_lbl = QLabel(unit)
        self.unit_lbl.setObjectName("Muted")
        self.unit_lbl.setAlignment(Qt.AlignLeft | Qt.AlignBottom)
        self._value_row.addWidget(self.unit_lbl)
        self._value_row.addStretch(1)
        col.addLayout(self._value_row)

        self.label_lbl = QLabel(label)
        self.label_lbl.setObjectName("StatLabel")
        col.addWidget(self.label_lbl)
        col.addStretch(1)
        lay.addLayout(col, 1)

        self._unit_pad = -1             # 单位基线补偿量，showEvent 里按真实字体算
        self._roll_t: Optional[float] = None
        self._roll_from = self._roll_to = 0
        self.set_move_room(*room)       # 布局搭好之后再开余量（_apply_gaze 要改 _lay）

    # -------------------------------------------------------------- 基线对齐
    def _align_unit(self) -> None:
        """把单位「本」压到与数字同一条基线上。

        `AlignBottom` 只对齐行盒底边，而 28px 数字与 12px 单位的下沉量（descent）
        不同，底边对齐会让单位整体低 1~2px。这里按实际字体度量把那点差补成下边距。
        必须在字体被 QSS 刷过之后再算，所以挂在 showEvent 上。
        """
        if not self.unit_lbl.text():
            return
        vfm = QFontMetrics(self.value_lbl.font())
        ufm = QFontMetrics(self.unit_lbl.font())
        d = max(0, vfm.descent() - ufm.descent())
        if d != self._unit_pad:
            self._unit_pad = d
            self.unit_lbl.setContentsMargins(0, 0, 0, d)

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self._align_unit()

    def _sync_move_room(self) -> None:
        # 宿主高度 = 可视卡面高度 + 上下两条走位余量
        self.setFixedHeight(self._base_h + 2 * self._inset_y)

    def _apply_gaze(self) -> None:
        ix, iy = self._inset_x, self._inset_y
        # 整卡位移（整数像素，带死区 + 滞回），夹到走位余量之内
        gdx, gdy = self._offsets(self._amp, "main")
        dx = self._fit_shift(gdx, ix, ix)
        dy = self._fit_shift(gdy, iy, iy)
        ex = self._fit_shift(self._dy_extra(), iy + dy, iy - dy)
        self._last_dx, self._last_dy, self._last_ex = dx, dy, ex
        bw = self.CARD_BORDER            # 描边那 1px 要算进内容偏移（见 CARD_BORDER）
        m1 = (ix + dx + self._L + bw, iy + dy + ex + self._T + bw,
              ix - dx + self._R + bw, iy - dy - ex + self._B + bw)

        # 徽标在整卡位移**之外**再多走一份 → 与文字形成视差。
        # ★ 徽标走「一次量化到位」：先算浮点总位移、再量化，最后减掉整卡那
        #   一份得到「额外量」。若两个通道各自 round 再相减，会引入 ±1px 的
        #   双重量化误差（2×round(3.5)=8，而 round(7.0)=7），徽标会比正文多
        #   跳一格 —— 单独看就是「徽标在抖」。
        tbx, tby = self._offsets(self._amp + GAZE_BADGE_PX, "badge")
        b = self._badge_base
        bx = self._fit_shift(tbx - dx, b, b)
        by = self._fit_shift(tby - dy, b, b)
        m2 = (b + bx, b + by, b - bx, b - by)
        key = (m1, m2)
        if key == self._margin_key:
            return
        self._margin_key = key
        self._lay.setContentsMargins(*m1)
        self._badge_lay.setContentsMargins(*m2)
        self.update()       # ★ 卡面是自绘的：位移变了必须显式请求重绘

    def paintEvent(self, event) -> None:  # noqa: N802
        # ★ 不调 super()：QSS 的卡面已让位，底与描边全部自绘
        p = QPainter(self)
        self._paint_card_face(p)
        p.end()
        self._paint_gaze(self)

    # ---------------------------------------------------------- 数字滚动
    def set_value(self, value: str, animate: bool = False) -> None:
        """`animate=True` 时从当前显示值滚到新值（只认纯整数，其余直接落位）。"""
        try:
            target = int(str(value).strip())
        except (TypeError, ValueError):
            self._roll_t = None
            self.value_lbl.setText(str(value))
            return
        try:
            cur = int(self.value_lbl.text().strip())
        except ValueError:
            cur = None
        if not animate or cur is None or cur == target:
            self._roll_t = None
            self.value_lbl.setText(str(target))
            return
        self._roll_from, self._roll_to = cur, target
        self._roll_t = 0.0

    def tick_anim(self, dt: float) -> bool:
        if self._roll_t is None:
            return False
        self._roll_t += dt
        k = self._roll_t / ROLL_DURATION
        if k >= 1.0:
            self._roll_t = None
            self.value_lbl.setText(str(self._roll_to))
            return False
        e = _ease_out_cubic(k)
        v = self._roll_from + (self._roll_to - self._roll_from) * e
        self.value_lbl.setText(str(int(round(v))))
        return True

    def finish_anim(self) -> None:
        if self._roll_t is not None:
            self._roll_t = None
            self.value_lbl.setText(str(self._roll_to))
        super().finish_anim()

    # ---------------------------------------------------------- 交互反馈
    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton and not self._press_dy:
            self._press_dy = 1              # 按下时内容下沉 1px
            self._margin_key = None
            self._apply_gaze()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):  # noqa: N802
        if self._press_dy:
            self._press_dy = 0
            self._margin_key = None
            self._apply_gaze()
        if e.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(e)


# ----------------------------------------------------- 下拉 / 微调按钮统一外观
#
# Windows 11 原生样式会在下拉按钮右侧画一道深灰色的 L 形分隔装饰，它不跟随样式表
# 的圆角边框，渲染出来像右下角掉了一块；微调框的上下按钮同样带着一对方框边框。
# 要消掉它们，唯一的办法是在样式表里接管 ``::drop-down`` / ``::up-button`` 等子控件，
# 但 Qt 一旦被接管该子控件，原生箭头就**同时**不再绘制，而 Qt 样式表又不支持用
# 纯 CSS 三角形补一个箭头（会画成一条横杠）。
#
# 结论：箭头一律自绘。下面这个函数是 ComboBox / DateEdit / SpinBox 共用的画笔，
# 保证三种控件的箭头形状、线宽、颜色完全一致。仍然是「手绘矢量、零图片资源」。

DROPDOWN_W = 26.0      # 下拉区宽度，需与 theme.py 里 ::drop-down 的 width 保持一致
SPINBTN_W = 24.0       # 微调按钮宽度，需与 theme.py 里 ::up-button 的 width 保持一致


def _border_widget_color(widget) -> str:
    return theme.TEXT_SUB if widget.isEnabled() else "#b6c1cd"


def _draw_chevron(p: QPainter, cx: float, cy: float, half: float, drop: float,
                  color: str) -> None:
    """在 (cx, cy) 画一个 chevron；drop 为正朝下、为负朝上。"""
    pen = QPen(QColor(color))
    pen.setWidthF(1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPolyline(QPolygonF([
        QPointF(cx - half, cy - drop),
        QPointF(cx, cy + drop),
        QPointF(cx + half, cy - drop),
    ]))


class ComboBox(QComboBox):
    """QComboBox + 自绘 chevron 箭头（理由见上方说明）。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _draw_chevron(p, self.width() - DROPDOWN_W / 2.0, self.height() / 2.0,
                      4.0, 2.0, _border_widget_color(self))
        p.end()


class DateEdit(QDateEdit):
    """日期框：默认开启日历弹层，下拉区外观与 ComboBox 完全一致。"""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.setCalendarPopup(True)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        _draw_chevron(p, self.width() - DROPDOWN_W / 2.0, self.height() / 2.0,
                      4.0, 2.0, _border_widget_color(self))
        p.end()


class SpinBox(QSpinBox):
    """微调框：上下箭头与下拉 chevron 同笔画，去掉原生那对带边框的小方块。"""

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        hot_up = hot_down = False
        try:  # activeSubControls 能告诉我们鼠标正压在哪半边，用于高亮
            opt = QStyleOptionSpinBox()
            self.initStyleOption(opt)
            hot_up = bool(opt.activeSubControls & QStyle.SubControl.SC_SpinBoxUp)
            hot_down = bool(opt.activeSubControls & QStyle.SubControl.SC_SpinBoxDown)
        except Exception:  # noqa: BLE001
            pass
        base = _border_widget_color(self)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() - SPINBTN_W / 2.0
        h = self.height()
        _draw_chevron(p, cx, h * 0.28, 3.6, -2.0,
                      theme.PRIMARY if hot_up else base)
        _draw_chevron(p, cx, h * 0.72, 3.6, 2.0,
                      theme.PRIMARY if hot_down else base)
        p.end()


# ------------------------------------------------------- Live2D 式「视角跟随」

class GazeLogo(QWidget):
    """会「看向鼠标」的应用徽标。

    Live2D 那种转头感的本质是分层视差：近处的图层动得多、远处的动得少。
    ``icons.paint_logo_gaze()`` 把徽标拆成 5 层按不同幅度位移，这里负责：

    * 60fps 采样鼠标相对徽标中心的方向，归一化成 -1 ~ 1 的视线向量；
    * 按真实 dt 做帧率无关缓动，跟随有「惯性」而不是硬跟，掉帧也不跳；
    * 整体叠一个极小的旋转与缩放，做出转头 + 呼吸的活性；
    * 窗口失焦 / 不可见时自动回正并停表，不空转 CPU。
    """

    _REF = 480.0        # 视线饱和距离（像素）：鼠标离徽标这么远时位移达到最大
    _TAU = 0.13         # 缓动时间常数（秒），越小跟得越紧

    def __init__(self, size: int = 44, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setFixedSize(int(size), int(size))
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._gx = self._gy = 0.0    # 当前视线（已缓动）
        self._tx = self._ty = 0.0    # 目标视线
        self._phase = 0.0
        self._clock = QElapsedTimer()
        self._clock.start()
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    # -- 供外部（或效果图工具）直接摆姿势 --
    def set_gaze(self, gx: float, gy: float) -> None:
        self._tx, self._ty = gx, gy
        self._gx, self._gy = gx, gy
        self.update()

    def showEvent(self, e):  # noqa: N802
        super().showEvent(e)
        self._clock.restart()
        self._timer.start()

    def hideEvent(self, e):  # noqa: N802
        super().hideEvent(e)
        self._timer.stop()

    def _tick(self) -> None:
        dt = self._clock.restart() / 1000.0
        if dt <= 0.0:
            return
        dt = min(dt, 0.05)
        win = self.window()
        if win is not None and win.isVisible() and win.isActiveWindow():
            gp = QCursor.pos()
            c = self.mapToGlobal(self.rect().center())
            self._tx = max(-1.0, min(1.0, (gp.x() - c.x()) / self._REF))
            self._ty = max(-1.0, min(1.0, (gp.y() - c.y()) / self._REF))
        else:
            self._tx = self._ty = 0.0
        a = 1.0 - math.exp(-dt / self._TAU)
        self._gx += (self._tx - self._gx) * a
        self._gy += (self._ty - self._gy) * a
        self._phase = (self._phase + dt * math.tau / BREATH_PERIOD) % 1.0
        if self.isVisible():
            self.update()

    def paintEvent(self, e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        s = float(min(self.width(), self.height()))
        breathe = math.sin(self._phase) * 0.012
        p.translate(self.width() / 2.0, self.height() / 2.0)
        p.rotate(self._gx * 5.5)
        p.scale(1.0 + breathe, 1.0 + breathe)
        p.translate(-s / 2.0, -s / 2.0)
        icons.paint_logo_gaze(p, s, self._gx, self._gy)
        p.end()


def _tint(color: str, alpha: int = 26) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{alpha})"


class Badge(QLabel):
    """彩色胶囊徽章。"""

    def __init__(self, text: str, fg: str, bg: str,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("Badge")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"#Badge {{ background:{bg}; color:{fg}; border-radius:9px;"
            f" padding:2px 9px; font-size:11px; font-weight:600; }}")
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


def status_badge(key: str) -> Badge:
    label = theme.status_label(key)
    return Badge(label, theme.status_color(key), theme.status_bg(key))


def tag(text: str, color: str) -> Badge:
    return Badge(text, color, _tint(color, 30))


class IconButton(QPushButton):
    def __init__(self, icon_name: str, tooltip: str = "", color: str = theme.TEXT_SUB,
                 size: int = 20, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("IconBtn")
        self._name = icon_name
        self._color = color
        self._size = size
        self.setIcon(icons.icon(icon_name, color, size))
        self.setToolTip(tooltip)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size + 18, size + 18)

    def set_colored(self, color: str) -> None:
        self._color = color
        self.setIcon(icons.icon(self._name, color, self._size))


def realize(btn: QPushButton, icon_name: str, color: str, size: int = 17) -> QPushButton:
    btn.setIcon(icons.icon(icon_name, color, size))
    btn.setCursor(Qt.PointingHandCursor)
    return btn


class SearchBox(QLineEdit):
    def __init__(self, placeholder: str = "搜索…", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(200)
        self.addAction(icons.icon("search", theme.MUTED, 16),
                       QLineEdit.LeadingPosition)


class EmptyState(QWidget):
    """空数据占位，可选一个主行动按钮。"""

    action_clicked = Signal()

    def __init__(self, title: str, hint: str = "", icon_name: str = "cert",
                 action_text: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(icon_name, "#c3cede", 56))
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        t = QLabel(title)
        t.setObjectName("EmptyTitle")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        if hint:
            h = QLabel(hint)
            h.setObjectName("EmptyHint")
            h.setAlignment(Qt.AlignCenter)
            h.setWordWrap(True)
            lay.addWidget(h)
        if action_text:
            btn = QPushButton(action_text)
            btn.setObjectName("Primary")
            realize(btn, "plus", "#ffffff")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedWidth(160)
            btn.clicked.connect(self.action_clicked.emit)
            row = QHBoxLayout()
            row.addStretch(1)
            row.addWidget(btn)
            row.addStretch(1)
            lay.addLayout(row)


class HBarChart(QWidget, GazeCard):
    """横向条形分布图（纯 QPainter 绘制，无第三方图表依赖）。

    也支持「视角跟随」：整张图随视线做一点视差位移，条形之上再叠一道随视线
    游走的高光。因为是自绘控件，这里直接平移画笔 —— 而且能吃**亚像素**，
    比改布局边距的 1px 台阶更顺。

    数据更新时走 ``set_data(..., animate=True)``，各条按索引错峰从 0 长出来。
    """

    def __init__(self, parent: Optional[QWidget] = None, bar_height: int = 16) -> None:
        super().__init__(parent)
        self._data: List[Tuple[str, int, str]] = []
        self._bar = bar_height
        self.gaze_setup(0, amp=GAZE_CHART_PX, glow=False)
        self._grow_t: Optional[float] = None
        self.setMinimumHeight(60)

    # -- 自绘控件：位移直接进画笔，不碰布局 --
    def _apply_gaze(self) -> None:
        pass

    def _maybe_repaint(self, force: bool = False) -> None:
        # 自绘控件不画柔光，但视差本身就是「要画的东西」，不能像卡片那样按柔光节流
        sig = self._paint_signature()
        if force or sig != self._paint_key:
            self._paint_key = sig
            self.update()

    def _paint_signature(self) -> tuple:
        # 自绘控件可以吃亚像素，量化步长取小；再叠上生长进度
        q = 0.30
        return (int(round(self._gx * self._amp / q)),
                int(round(self._gy * self._amp / q)),
                int(round(self._hover * 10)),
                int(round(self._grow_step() * 24)))

    def _bar_progress(self, i: int) -> float:
        if self._grow_t is None:
            return 1.0
        k = (self._grow_t - i * GROW_STAGGER) / GROW_DURATION
        return _ease_out_cubic(max(0.0, min(1.0, k)))

    def _grow_step(self) -> float:
        if self._grow_t is None:
            return 1.0
        return max([self._bar_progress(i) for i in range(len(self._data))] or [1.0])

    def tick_anim(self, dt: float) -> bool:
        """生长推进（挂在 GazeScene.tick 上，不额外开定时器）。"""
        if self._grow_t is None:
            return False
        self._grow_t += dt
        span = max(0, len(self._data) - 1) * GROW_STAGGER + GROW_DURATION
        if self._grow_t >= span:
            self._grow_t = None
            self._paint_key = None
            self.update()
            return False
        self._maybe_repaint()
        return True

    def finish_anim(self) -> None:
        if self._grow_t is not None:
            self._grow_t = None
            self._paint_key = None
            self.update()
        super().finish_anim()

    def set_data(self, data: Sequence[Tuple[str, int, str]],
                 animate: bool = False) -> None:
        rows = [tuple(d) for d in data]
        # 只在数据**真的变了**时才重播生长：每次切回首页都把同样的条形再长一遍
        # 就成了杂耍，而且会让「动效」失去「有东西变了」这层意思。
        animate = bool(animate) and rows != [tuple(d) for d in self._data]
        self._data = rows
        self.setMinimumHeight(max(60, len(self._data) * (self._bar + 12) + 8))
        self._grow_t = 0.0 if animate else None
        self._paint_key = None
        self.update()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if not self._data:
            p.setPen(QPen(QColor(theme.MUTED)))
            p.drawText(self.rect(), Qt.AlignCenter, "暂无数据")
            return
        p.save()
        # 亚像素视差：上半部分整图平移，比布局边距的分辨率高得多
        p.translate(self._gx * self._amp, self._gy * self._amp * 0.72)
        fm = p.fontMetrics()
        label_w = max([fm.horizontalAdvance(d[0]) for d in self._data] + [60]) + 10
        value_w = 46
        total = sum(d[1] for d in self._data) or 1
        maxv = max(d[1] for d in self._data) or 1
        avail = max(40, self.width() - label_w - value_w - 12)
        y = 4
        for i, (name, value, color) in enumerate(self._data):
            prog = self._bar_progress(i)
            p.setPen(QPen(QColor(theme.TEXT_SUB)))
            p.drawText(QRectF(0, y, label_w - 8, self._bar + 4),
                       Qt.AlignRight | Qt.AlignVCenter, name)
            w = max(6.0, avail * (value / maxv)) * prog
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.NEUTRAL_SOFT))
            p.drawRoundedRect(QRectF(label_w, y + 1, avail, self._bar), 4, 4)
            p.setBrush(QColor(color))
            p.drawRoundedRect(QRectF(label_w, y + 1, max(0.0, w), self._bar), 4, 4)
            p.setPen(QPen(QColor(theme.TEXT_SUB)))
            p.drawText(QRectF(label_w + avail + 6, y, value_w, self._bar + 4),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       f"{value}  {value * 100 // total}%")
            y += self._bar + 12
        p.restore()


class InfoRow(QWidget):
    """详情页的「标签 / 取值」两列行。"""

    def __init__(self, label: str, value: str = "—", parent: Optional[QWidget] = None,
                 value_color: str = theme.TEXT, wrap: bool = False) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        t = QLabel(label)
        t.setObjectName("Muted")
        lay.addWidget(t)
        self.value = QLabel(value or "—")
        self.value.setWordWrap(wrap)
        self.value.setStyleSheet(f"color:{value_color}; font-size:13px;")
        self.value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.value)

    def set_value(self, value: str) -> None:
        self.value.setText(value or "—")


class FlowRow(QWidget):
    """一行横向排布的多个 InfoRow（自动均分宽度）。"""

    def __init__(self, items: Sequence[Tuple[str, str]], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(18)
        self.rows: List[InfoRow] = []
        for label, value in items:
            r = InfoRow(label, value)
            self.rows.append(r)
            lay.addWidget(r, 1)


class SectionTitle(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setObjectName("SectionLabel")


class ElidedLabel(QLabel):
    """单行省略标签：宽度不够时尾部加「…」，**而不是换行把行高撑开**。

    列表行里的证书名、编号这类长短不定的文本必须用它 —— 换行会让同一组的
    行高参差不齐，看起来就是「排版没对齐」。

    ★ 横向策略给的是 ``Ignored``：布局问不到有意义的 sizeHint，于是空间不够时
    压缩它自己，而不是把整行撑宽把右侧的按钮挤出去。
    """

    def __init__(self, text: str = "", mode=Qt.ElideRight,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._full = text
        self._mode = mode
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setToolTip(text)

    def full_text(self) -> str:
        return self._full

    def setText(self, text: str) -> None:  # noqa: N802
        self._full = text
        self.setToolTip(text)
        self._apply()

    def _apply(self) -> None:
        w = max(0, self.width() - 2)
        out = QFontMetrics(self.font()).elidedText(self._full, self._mode, w) \
            if w > 0 else self._full
        if out != super().text():
            super().setText(out)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._apply()

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        s = super().minimumSizeHint()
        return QSize(0, s.height())


def hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color:{theme.BORDER}; background:{theme.BORDER}; max-height:1px;")
    return f


def mono_label(text: str, color: str = theme.MUTED, size: int = 11) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color:{color}; font-size:{size}px;"
                      f" font-family:{theme.MONO_FAMILY};")
    return lbl


def bold(text: str, size: int = 13, color: str = theme.TEXT) -> QLabel:
    lbl = QLabel(text)
    f = QFont()
    f.setPointSize(size)
    f.setBold(True)
    lbl.setFont(f)
    lbl.setStyleSheet(f"color:{color};")
    return lbl
