# -*- coding: utf-8 -*-
"""首页总览「视角跟随」抖动诊断探针 —— 把「抖」量成数字。

`anim_check.py` 管的是「动画在不在、帧率够不够」；这个管的是**位移本身顺不顺**：
位移序列里如果出现「方向反复反转」「孤立的 1px 跳」或「单帧大跳变」，
肉眼就读作抖动。三类症状对应的成因不同，所以分开测：

  S1 静止不动    —— 鼠标完全静止时，位移应彻底冻结（不能有边界反复翻档）
  S2 手抖鼠标    —— 鼠标 ±2px 微动时，位移必须纹丝不动（死区 + 滞回）
  S3 慢速横扫    —— 慢扫时的台阶必须少而均匀（台阶多 = 「一格一格」感）
  S4 悬停划过    —— 划过一排卡片时的单帧最大跳变（悬停放大位移 = 抖的主犯）
  S5 入场尾部    —— 入场收尾阶段不能拖一条「1px 慢爬 + 过冲回摆」的尾巴
  S6 真实帧间隔  —— 真实定时器下的交付间隔分布

另有一条贯穿全程的硬约束（每一步都查）：
  · 布局边距绝不出现负数（QLayout 一个边距为负 → 整组退回 QStyle 默认值 9）
  · 可视卡面绝不顶出宿主控件（顶出去会被裁掉一条边，肉眼极难发现）

全部驱动都是确定性的：假光标 + 假时钟，直接调 `scene._tick()`，
所以同一份代码每次跑出的数字完全一致，适合当回归门禁。

用法：
    <venv>/Scripts/python.exe tools/jitter_check.py
退出码 0 = 通过。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication

import app.widgets as W                     # noqa: E402  —— 要替换模块级 QCursor
from app import theme                       # noqa: F401,E402
from app.db import Database                 # noqa: E402
from app.main_window import MainWindow      # noqa: E402
from app.palette import apply_palette       # noqa: E402
from app.sampledata import load_samples     # noqa: E402
from app.widgets import ENTER_LIFT, GAZE_CARD_PX  # noqa: E402

FRAME_MS = 1000.0 / 60.0


class FakeCursor:
    """替换 widgets.QCursor，把光标位置变成可控变量。"""

    px = 0
    py = 0

    @classmethod
    def pos(cls) -> QPoint:
        return QPoint(int(cls.px), int(cls.py))


class FakeClock:
    """替换 scene._clock，让 dt 恒为 1/60 秒 —— 探针才可复现。"""

    def __init__(self, ms: float = FRAME_MS) -> None:
        self.ms = ms

    def restart(self) -> float:
        return self.ms


def analyze(track: list) -> dict:
    """一串位移值 → 抖动指标。

    reversals 方向反转次数（平滑运动只该有 0~1 次）
    max_jump  相邻帧最大跳变（像素）
    stalls    长度 ≥ 8 帧的「纹丝不动」段数（多说明是「一格一格」）
    """
    d = [track[i + 1] - track[i] for i in range(len(track) - 1)]
    nz = [x for x in d if x != 0]
    rev = 0
    last_sign = 0
    for x in nz:
        s = 1 if x > 0 else -1
        if last_sign and s != last_sign:
            rev += 1
        last_sign = s
    stalls = 0
    run = 1
    for x in d:
        if x == 0:
            run += 1
        else:
            if run >= 8:
                stalls += 1
            run = 1
    if run >= 8:
        stalls += 1
    return {"reversals": rev, "max_jump": max((abs(x) for x in d), default=0),
            "stalls": stalls, "changes": len(nz)}


def main() -> int:  # noqa: C901
    app = QApplication(sys.argv)
    apply_palette(app)

    db_path = ROOT / "data" / "_jitter.db"
    db_path.unlink(missing_ok=True)
    database = Database(db_path)
    load_samples(database)
    database.set_setting("popup_on_start", "0")

    win = MainWindow(database)
    win.setAttribute(Qt.WA_DontShowOnScreen, True)
    win.show()
    win.resize(1440, 900)
    for _ in range(3):
        app.processEvents()
    win.goto("dashboard")
    for _ in range(4):
        app.processEvents()

    # 让 _tick 里的 active 判定成立（离屏窗口默认不算活动窗口）
    try:
        win.isActiveWindow = lambda: True           # type: ignore[assignment]
    except (AttributeError, TypeError):
        pass

    dash = win.pages["dashboard"]
    scene = dash._scene
    scene.stop()
    scene.settle()

    W.QCursor = FakeCursor                          # ★ 换成假光标
    scene._clock = FakeClock()                      # ★ 换成假时钟

    sc = dash.c_total
    base_L, base_T = sc._L, sc._T

    def body_x(w) -> int:
        """整块模块的横向位移（从布局边距反推，扣掉走位余量与描边）。"""
        return (w._lay.contentsMargins().left() - w._L
                - w.CARD_BORDER - w._inset_x)

    def badge_x(w) -> int:
        return w._badge_lay.contentsMargins().left() - w._badge_base

    def step(n: int = 1) -> None:
        for _ in range(n):
            scene._tick()
            check_margins("tick")

    ok = True

    def bad(msg: str) -> None:
        nonlocal ok
        ok = False
        print(f"  ✗ {msg}")

    # ★ 全局硬约束：任何一步都不许出现负的布局边距。
    #   QLayout 只要有一个边距为负，getContentsMargins() 就整组退回 QStyle
    #   默认值（Windows = 9）→ 内容一帧横移 10px，是最隐蔽的一类「抖」。
    neg_violations: list = []
    # ★ v1.1.9 新增：卡面改为自绘 + 走位余量后，多了一条同等级的硬约束 ——
    #   可视卡面（白底 / 边框 / 圆角所在的那个矩形）must 完整落在宿主控件之内。
    #   顶出去不会报错，只会被宿主裁掉一条边，而且只在某些视线角度才出现，
    #   肉眼极难发现 —— 正好交给探针守。
    clip_violations: list = []

    def check_margins(tag: str) -> None:
        # ★ 注意 scene._targets 里的元素是记录表 [widget, follow, hover, hover_cur]，
        #   控件在 rec[0]。早先这里直接遍历 _targets，getattr 全落空 →
        #   这条硬约束形同虚设（探针本身也会骗人，改探针时同步核对）。
        for rec in scene._targets:
            w = rec[0]
            for lay in (getattr(w, "_v", None), getattr(w, "_lay", None),
                        getattr(w, "_badge_lay", None)):
                if lay is None:
                    continue
                m = lay.contentsMargins()
                if min(m.left(), m.top(), m.right(), m.bottom()) < 0:
                    neg_violations.append((tag, type(w).__name__, str(m)))
                    return
            vr = w._vis_rect()
            if (vr.x() < -0.01 or vr.y() < -0.01
                    or vr.right() > w.width() + 0.01
                    or vr.bottom() > w.height() + 0.01):
                clip_violations.append(
                    (tag, type(w).__name__,
                     f"卡面({vr.x():.1f},{vr.y():.1f}) {vr.width():.0f}x"
                     f"{vr.height():.0f} / 宿主 {w.width()}x{w.height()}"))
                return

    c = win.mapToGlobal(win.rect().center())
    print(f"窗口中心（全局）=({c.x()},{c.y()})  视线参考距离 ref={scene._ref:.0f}px "
          f"整卡幅度 ±{GAZE_CARD_PX:.0f}px  走位余量 "
          f"±({sc._inset_x},{sc._inset_y})px")

    # ============================================================ S1
    print("=== S1 静止不动：位移必须彻底冻结 ===")
    FakeCursor.px, FakeCursor.py = c.x() + 210, c.y() + 40
    step(40)                                        # 先收敛（并越过 1.1s 待机切换）
    t_rest = [body_x(sc) for _ in range(180)]
    r1 = analyze(t_rest)
    print(f"  收敛后 180 帧：变化 {r1['changes']} 次，反转 {r1['reversals']} 次，"
          f"最大跳变 {r1['max_jump']}px")
    if r1["changes"] > 2 or r1["reversals"] > 1:
        bad("静止时位移仍在翻档（边界反复翻转 ↔ 肉眼就是「抖」）")
    else:
        print("  ✓ 静止时位移冻结")

    # ============================================================ S2
    print("=== S2 手抖鼠标（±2px 随机游走 240 帧）：位移必须纹丝不动 ===")
    seed = 12345
    t_h = []
    for _ in range(240):
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        jx = (seed % 5) - 2                          # -2..+2
        seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
        jy = (seed % 5) - 2
        FakeCursor.px, FakeCursor.py = c.x() + 210 + jx, c.y() + 40 + jy
        step()
        t_h.append(body_x(sc))
    r2 = analyze(t_h)
    print(f"  变化 {r2['changes']} 次，反转 {r2['reversals']} 次，最大跳变 {r2['max_jump']}px")
    if r2["reversals"] > 1 or r2["max_jump"] > 1:
        bad("手抖引起位移抖（缺死区 / 滞回）")
    else:
        print("  ✓ 手抖不牵动位移")

    # ============================================================ S3
    print("=== S3 慢速横扫（2px/帧，共 300 帧）===")
    FakeCursor.px, FakeCursor.py = c.x() - 320, c.y() + 40
    step(50)
    t_s = []
    for _ in range(300):
        FakeCursor.px += 2
        step()
        t_s.append(body_x(sc))
    r3 = analyze(t_s)
    span = max(t_s) - min(t_s)
    # QWidget 的几何只能是整数像素 → 1px 台阶是物理下限，不可能归零。
    # 能做的是把台阶「排密」：台阶间隔 = ref / 幅度（鼠标像素/档）。
    density = scene._ref / GAZE_CARD_PX
    print(f"  位移跨度 {span}px，变化 {r3['changes']} 次，反转 {r3['reversals']} 次，"
          f"最大跳变 {r3['max_jump']}px，长静止段 {r3['stalls']} 个")
    print(f"  台阶密度：每 {density:.0f} 鼠标像素跨 1px（ref={scene._ref:.0f} / "
          f"幅度 {GAZE_CARD_PX:.0f}）—— 这一项是整数像素的物理下限")
    if r3["reversals"] > 0:
        bad("慢扫时位移来回摆（不是单调推进）")
    elif r3["max_jump"] > 1:
        bad(f"慢扫时出现 {r3['max_jump']}px 的大跳变（跨档不该超过 1px）")
    elif density > 95:
        bad(f"台阶密度太低（每 {density:.0f} 鼠标像素才跳 1px），会「一格一格」")
    else:
        print("  ✓ 慢扫单调推进、无来回摆、台阶密度已排密")

    # ============================================================ S3b
    print("=== S3b 慢速拖动不得被误判成「待机」===")
    FakeCursor.px, FakeCursor.py = c.x() - 200, c.y() + 40
    step(40)
    idle_max = 0.0
    for _ in range(240):                         # 4 秒慢拖（2px/帧 = 120px/s）
        FakeCursor.px += 2
        step()
        idle_max = max(idle_max, scene._idle_f)
    print(f"  4 秒慢拖期间 待机系数峰值 = {idle_max:.3f}（0 = 完全跟手）")
    if idle_max > 0.05:
        bad("慢速拖动被判成待机 —— 视线会在拖动中途突然松开，看成一次摆动")
    else:
        print("  ✓ 慢速拖动全程保持跟手")

    # ============================================================ S4
    print("=== S4 悬停：同视线下位移必须完全不变 ===")
    # 纯逻辑测法：固定视线，只切悬停分量。悬停一旦参与位移幅度，
    # 鼠标划过一排卡片时每张卡就会轮流把位移拉大 —— 那是「抖」的头号来源。
    scene._gx, scene._gy, scene._breath = 0.8, 0.0, 0.0
    seen = []
    for hov in (0.0, 1.0, 0.0, 1.0):
        for rec in scene._targets:
            rec[3] = hov
        scene._broadcast()
        check_margins("hover")
        seen.append((body_x(sc), badge_x(sc)))
    b = [s[0] for s in seen]
    g = [s[1] for s in seen]
    print(f"  悬停 0→1→0→1 时 正文 x={b}  徽标 x={g}")
    if max(b) != min(b) or max(g) != min(g):
        bad(f"悬停改变了位移（正文跨度 {max(b)-min(b)}px、徽标跨度 {max(g)-min(g)}px）")
    else:
        print("  ✓ 悬停完全不动位移")

    # 真机路径：鼠标沿一排统计卡缓缓划过，看单帧最大跳变（应只来自视线本身）
    FakeCursor.px, FakeCursor.py = c.x() - 420, c.y() + 30
    step(40)
    worst = 0
    prev = body_x(sc)
    for i in range(240):
        FakeCursor.px += 3
        step()
        cur = body_x(sc)
        worst = max(worst, abs(cur - prev))
        prev = cur
    print(f"  缓缓划过一排卡片：单帧最大跳变 {worst}px（1px 量化台阶的上限）")
    if worst > 2:
        bad("划过卡片时位移跳变过大")
    else:
        print("  ✓ 划过卡片没有额外跳变")

    # ============================================================ S5
    print("=== S5 入场收尾：不得有过冲回摆，也不得拖 1px 慢爬尾巴 ===")
    scene.set_gaze(0.0, 0.0)
    step(5)
    dur = 0.52
    sc.play_enter(0.0, dur)
    offs = []
    for _ in range(int(dur * 60) + 12):
        sc.tick_enter(1 / 60.0)
        offs.append(sc._enter_off)
    first_zero = next((i for i, v in enumerate(offs) if v == 0), None)
    bounce = [v for v in offs[first_zero:] if v != 0] if first_zero is not None else []
    print(f"  轨迹={offs[:18]} …")
    print(f"  起始 {max(offs)}px，最低 {min(offs)}px，"
          f"第 {first_zero} 帧归零（整段 {int(dur*60)} 帧）")
    if min(offs) < 0:
        bad(f"出现过冲回摆（最低 {min(offs)}px）")
    elif first_zero is None:
        bad("始终没有归零")
    elif first_zero > int(dur * 60) * 0.62:
        bad(f"归零太晚（第 {first_zero} 帧），尾部会拖出「停一下跳 1px」的慢爬")
    elif bounce:
        bad(f"归零后又弹回（{bounce[:6]}）")
    elif max(offs) < ENTER_LIFT - 2:
        bad(f"入场幅度过小（{max(offs)}px）")
    else:
        print("  ✓ 入场无过冲、收尾干净（1px 慢爬段已被吸附截掉）")

    # ============================================================ S6
    print("=== 全程序列汇总：布局边距非负 + 可视卡面不越界（硬约束）===")
    if neg_violations:
        bad(f"出现 {len(neg_violations)} 次负边距，例如 {neg_violations[0]}")
    elif clip_violations:
        bad(f"出现 {len(clip_violations)} 次卡面顶出宿主（会被裁掉一条边），"
            f"例如 {clip_violations[0]}")
    else:
        print("  ✓ 全部帧未出现负的布局边距，可视卡面也从未顶出宿主"
              "（QLayout 一个边距为负就会整组退回 QStyle 默认值 9）")

    print("=== S6 真实定时器帧间隔（60fps PreciseTimer + 真实负载）===")
    import time as _time
    scene._clock = W.QElapsedTimer()                # 换回真时钟
    scene._clock.start()
    stamps: list = []
    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.setInterval(16)

    def on_tick() -> None:
        k = len(stamps)
        FakeCursor.px = c.x() + int(300 * __import__("math").sin(k * 0.08))
        FakeCursor.py = c.y() + int(120 * __import__("math").cos(k * 0.06))
        scene._tick()
        app.processEvents()
        stamps.append(_time.perf_counter())

    timer.timeout.connect(on_tick)
    timer.start()
    deadline = _time.perf_counter() + 6.0
    while len(stamps) < 140 and _time.perf_counter() < deadline:
        app.processEvents()
    timer.stop()
    gaps = sorted((stamps[i + 1] - stamps[i]) * 1000.0 for i in range(len(stamps) - 1))
    if gaps:
        med = gaps[len(gaps) // 2]
        p95 = gaps[int(len(gaps) * 0.95)]
        print(f"  样本 {len(gaps)}  中位={med:.2f}ms  p95={p95:.2f}ms  最差={gaps[-1]:.2f}ms")
        if med > 18.0 or p95 > 26.0:
            bad("帧间隔不稳")
        else:
            print("  ✓ 帧间隔稳定在 60fps 附近")

    win.hide()
    app.processEvents()
    try:
        db_path.unlink(missing_ok=True)
    except OSError:
        print(f"  （临时库未能自动清理，可手动删除 {db_path.name}）")
    print("[jitter] 结论：", "全部通过" if ok else "存在失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
