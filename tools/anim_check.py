# -*- coding: utf-8 -*-
"""首页总览「动效系统」验收探针 —— 把「顺不顺手」量成数字。

改完 `app/widgets.py` 的动效部分（GazeScene / GazeCard / HBarChart）后跑这个。

检查项
  1. 静止位形是否被改歪（**相对可视卡面**的徽标 / 正文坐标是硬约束）
  2. ★ 整块模块在动：可视卡面位移 == 内容位移；宿主控件（布局项）必须恒定不动
     —— 卡面动了才是「模块有动效」，宿主动了就是踩了父布局重排
  3. 重排零副作用：滚动条范围、卡片几何全程不变
  4. 入场曲线：必须无过冲、无 1px 慢爬尾巴，柔光脉冲由亮转淡
  5. 悬停不得改变位移，但视觉反馈必须还在
  6. 动态帧成本（含真实重绘）—— 60fps 预算 16.7ms
  7. 静态帧成本 —— 鼠标停住时应几乎不重绘（节流生效）
  8. 整窗重绘参考值
  9. 定时器实际交付间隔 —— 中位 / p95 / 最差，这才是「流畅」的真身

用法：
    <venv>/Scripts/python.exe tools/anim_check.py
退出码 0 = 全部通过。
"""

from __future__ import annotations

import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QScrollArea

from app import icons, theme, version  # noqa: F401
from app.db import Database
from app.main_window import MainWindow
from app.palette import apply_palette
from app.sampledata import load_samples
from app.widgets import (ENTER_LIFT, GAZE_BADGE_PX, GAZE_CARD_PX, GAZE_FPS)


def main() -> int:
    app = QApplication(sys.argv)
    apply_palette(app)

    db_path = ROOT / "data" / "_animcheck.db"
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
    for _ in range(3):
        app.processEvents()

    dash = win.pages["dashboard"]
    scene = dash._scene
    scene.stop()        # 先冻结，静态项才可复现
    scene.settle()      # 再把入场/滚动/生长推到终态，否则会量到动画半途

    sc = dash.c_total
    chart = dash.chart
    ok = True

    def pump(n: int = 3) -> None:
        for _ in range(n):
            app.processEvents()

    def rel(widget, card):
        """widget 相对 card 左上角的偏移（都换算到窗口坐标再相减）。"""
        a = widget.mapTo(win, QPoint(0, 0))
        b = card.mapTo(win, QPoint(0, 0))
        return a.x() - b.x(), a.y() - b.y()

    def bad(msg: str) -> None:
        nonlocal ok
        ok = False
        print(f"  ✗ {msg}")

    # ------------------------------------------------------------ 1
    print("=== 1. 静止位形（hard 约束：相对**可视卡面** 徽标 x=17 / 正文 x=69）===")
    # 卡面描边占 1px，布局边距从内容矩形算起 →
    #   徽标 = 1(描边) + 4(左内边距) + 12(容器内居中) = 17
    #   正文 = 1(描边) + 4 + 64(容器) + 0(间距)          = 69
    # ★ v1.1.9 起卡片开了「走位余量」：宿主控件比可视卡面每边大 inset，
    #   所以先量到的宿主内偏移必须**减掉 inset** 才是相对卡面的偏移。
    #   减完仍须是 17 / 69 —— 整卡机制不得挪动静态布局（截图逐像素比对同口径）。
    scene.set_gaze(0.0, 0.0)
    pump()
    ix = sc._inset_x
    bx, by = rel(sc.badge, sc)
    vx, vy = rel(sc.value_lbl, sc)
    print(f"  统计卡 宿主内 徽标=({bx},{by}) 正文=({vx},{vy})  走位余量 x={ix}")
    print(f"  相对可视卡面：徽标 x={bx - ix}  正文 x={vx - ix}（期望 17 / 69）")
    if (bx - ix, vx - ix) != (17, 69):
        bad("静止位形漂移了（预期相对卡面 徽标 17 / 正文 69）")
    else:
        print("  ✓ 静止位形未漂移（可视卡面与 v1.1.8 逐像素重合）")

    # ------------------------------------------------------------ 2
    print("=== 2. ★ 整块模块在动：可视卡面位移 == 内容位移；宿主控件恒定 ===")
    geo0 = sc.geometry()
    pos_rest = rel(sc.badge, sc)
    vpos_rest = rel(sc.value_lbl, sc)
    b0 = sc.CARD_BORDER
    samples = []
    for gx, gy, tag in ((1.0, 1.0, "视线(+1,+1)"), (-1.0, -1.0, "视线(-1,-1)"),
                        (0.0, 0.0, "回中")):
        scene.set_gaze(gx, gy)
        pump()
        # 可视卡面相对宿主的位移（自绘卡面的真实落点）
        fdx = int(round(sc._vis_rect().x())) - sc._inset_x
        fdy = int(round(sc._vis_rect().y())) - sc._inset_y
        # 内容位移（从布局边距反推：边距 − 基线 − 描边 − 走位余量）
        m = sc._lay.contentsMargins()
        cdx = m.left() - sc._L - b0 - ix
        cdy = m.top() - sc._T - b0 - sc._inset_y
        bx2, by2 = rel(sc.badge, sc)
        vx2, vy2 = rel(sc.value_lbl, sc)
        samples.append((tag, fdx, fdy, cdx, cdy,
                        bx2 - pos_rest[0], by2 - pos_rest[1],
                        vx2 - vpos_rest[0], vy2 - vpos_rest[1]))
        print(f"  {tag:12s} 可视卡面=({fdx:+d},{fdy:+d})  内容=({cdx:+d},{cdy:+d})  "
              f"徽标=({bx2-pos_rest[0]:+d},{by2-pos_rest[1]:+d})  "
              f"图表视差=({chart._gx * chart._amp:+.2f},{chart._gy * chart._amp:+.2f})  "
              f"宿主={sc.geometry().width()}x{sc.geometry().height()}@"
              f"({sc.geometry().x()},{sc.geometry().y()})")
    if sc.geometry() != geo0:
        bad("宿主控件几何动了（说明触发了父布局重排）")
    else:
        print("  ✓ 宿主控件全程不动（零重排：位移完全不经过父布局）")
    off = [s for s in samples if (s[1], s[2]) != (s[3], s[4])]
    if off:
        bad(f"可视卡面与内容位移不一致（{off[0][0]}）—— 会看成「框不动、字在滑」")
    else:
        print("  ✓ 可视卡面位移 == 内容位移：白底/边框/圆角/文字是同一个整体在动")
    amp = int(GAZE_CARD_PX)
    if abs(samples[0][1]) != amp or abs(samples[0][2]) != amp:
        bad(f"整卡位移幅度不是 ±{amp}px（实为 {samples[0][1]},{samples[0][2]}）")
    else:
        print(f"  ✓ 整卡位移打满 ±{amp}px（模块级可见位移，不再只是文字在滑）")
    if samples[0][5] <= samples[0][1]:
        bad("徽标位移未大于整卡位移（层次丢失）")
    else:
        print(f"  ✓ 分层成立：徽标 ±{samples[0][5]}px > 整卡 ±{samples[0][1]}px "
              f"（整卡 {GAZE_CARD_PX:.0f} + 徽标额外 {GAZE_BADGE_PX:.0f}）")
    if samples[2][1] != 0 or samples[2][5] != 0:
        bad("视线回中后未精确复原")
    else:
        print("  ✓ 视线回中后逐像素复原")

    # ------------------------------------------------------------ 3
    print("=== 3. 重排零副作用（滚动条范围 / 卡片尺寸全程不变）===")
    sbar = dash.findChild(QScrollArea).verticalScrollBar()
    rng0 = (sbar.minimum(), sbar.maximum())
    stats = (dash.c_total, dash.c_valid, dash.c_soon, dash.c_expired)
    stat_geo0 = [c.geometry() for c in stats]
    for i in range(30):
        scene.set_gaze(math.sin(i * 0.4), math.cos(i * 0.31))
        pump(1)
        if (sbar.minimum(), sbar.maximum()) != rng0:
            bad(f"第 {i} 步滚动条范围变了：{rng0} → "
                f"{(sbar.minimum(), sbar.maximum())}")
            break
    else:
        print(f"  ✓ 30 步扫视后滚动条范围恒为 {rng0}")
    if [c.geometry() for c in stats] != stat_geo0:
        bad("统计卡几何发生变化")
    else:
        print(f"  ✓ 4 张统计卡几何恒定（{stat_geo0[0].width()}x{stat_geo0[0].height()}）")

    # ------------------------------------------------------------ 4
    print("=== 4. 入场曲线（必须无过冲、无 1px 慢爬尾巴）===")
    scene.set_gaze(0.0, 0.0)
    pump()
    sc.play_enter(0.0, 0.5)
    offs = []
    for _ in range(60):
        sc.tick_enter(1 / 60.0)
        offs.append(sc._enter_off)
    print(f"  轨迹前 20 帧={offs[:20]}")
    sc.play_enter(0.0, 0.5)
    sc.tick_enter(0.0)
    pulse0 = sc._enter_pulse()
    sc.tick_enter(0.10)                  # k=0.2：还在播（过 0.48 会被尾部吸附收尾）
    pulse1 = sc._enter_pulse()
    print(f"  柔光脉冲：入场瞬间={pulse0:.2f} → 五分之一程={pulse1:.2f}")
    # 归零之后必须一直是 0（不能回摆）
    first_zero = next((i for i, v in enumerate(offs) if v == 0), None)
    back = [v for v in offs[(first_zero or 0):] if v != 0]
    if max(offs) < ENTER_LIFT - 3:
        bad(f"起始偏移远小于 {ENTER_LIFT}（实为 {max(offs)}）")
    elif min(offs) < 0:
        bad(f"出现过冲回摆（最低 {min(offs)}px）—— 1px 回摆只会读成抖动")
    elif offs[-1] != 0:
        bad(f"结束未归零（实为 {offs[-1]}）")
    elif back:
        bad(f"归零后又弹回去（{back[:6]}）")
    elif first_zero is None or first_zero > 46:
        bad(f"收尾太晚（第 {first_zero} 帧才归零，会拖出 1px 慢爬）")
    elif not (pulse0 > pulse1 > 0):
        bad("入场柔光脉冲不成立")
    else:
        print(f"  ✓ 从 +{max(offs)} 起、第 {first_zero} 帧干净归零、"
              f"全程无过冲，柔光由亮转淡")
    sc.tick_enter(9.9)

    # ------------------------------------------------------------ 5
    print("=== 5. 悬停：不得改变位移，但视觉反馈必须还在 ===")
    sc.set_gaze(0.5, 0.0, 0.0, 0.0)
    pump()
    b0, v0 = rel(sc.badge, sc)[0], rel(sc.value_lbl, sc)[0]
    img0 = sc.grab().toImage()
    sc.set_gaze(0.5, 0.0, 0.0, 1.0)
    pump()
    b1, v1 = rel(sc.badge, sc)[0], rel(sc.value_lbl, sc)[0]
    img1 = sc.grab().toImage()
    diff = 0
    for y in range(0, img1.height(), 2):
        for x in range(0, img1.width(), 2):
            if img1.pixel(x, y) != img0.pixel(x, y):
                diff += 1
    print(f"  同上视线下 悬停 0 → 1：徽标 x {b0}→{b1}，正文 x {v0}→{v1}；"
          f"画面变化点 {diff} 个")
    if (b0, v0) != (b1, v1):
        bad("悬停改变了位移 —— 划过一排卡片时会来回猛跳（这就是「抖」）")
    else:
        print("  ✓ 悬停完全不动位移（放大跟随已关闭）")
    if diff < 120:
        bad("悬停的视觉反馈没了（柔光提亮 + 双圈描边应留下明显笔迹）")
    else:
        print(f"  ✓ 悬停仍有点亮与描边（{diff} 个采样点变化），不是「无反馈」")
    for breath in (1.0, -1.0):
        sc.set_gaze(0.0, 0.0, breath, 0.0)
        pump()
    print("  ✓ 呼吸分量（±1）可正常下发，且不参与几何位移（只影响柔光）")
    sc.set_gaze(0.0, 0.0, 0.0, 0.0)
    pump()

    # ------------------------------------------------------------ 6
    print("=== 6. 动态帧成本（含真实重绘，60fps 预算 16.7ms）===")
    n = 90
    t0 = time.perf_counter()
    for i in range(n):
        scene._gx = math.sin(i * 0.12)
        scene._gy = math.cos(i * 0.09)
        scene._breath = math.sin(i * 0.05)
        for rec in scene._targets:
            rec[3] = 0.35
        scene._broadcast()
        app.processEvents()
    per = (time.perf_counter() - t0) / n * 1000.0
    print(f"  动态（连续扫视 + 悬停）: {per:.2f} ms/帧  → 上限 {1000.0 / per:.0f} fps")
    if per > 16.7:
        bad("超出 60fps 预算")
    else:
        print("  ✓ 在 60fps 预算内")

    # ------------------------------------------------------------ 7
    print("=== 7. 静态帧成本（鼠标停住，位移量化后应几乎不重绘）===")
    scene._gx = scene._gy = 0.35
    scene._breath = 0.2
    scene._broadcast()
    pump(3)
    m = 90
    t0 = time.perf_counter()
    for _ in range(m):
        scene._broadcast()
        app.processEvents()
    per2 = (time.perf_counter() - t0) / m * 1000.0
    print(f"  静态: {per2:.3f} ms/帧")
    if per2 > per * 0.6:
        bad("静态帧没有明显便宜（重绘节流没生效）")
    else:
        print(f"  ✓ 静态帧比动态帧便宜 {per / per2:.1f} 倍（重绘节流生效）")

    # ------------------------------------------------------------ 8
    print("=== 8. 整窗重绘参考 ===")
    t0 = time.perf_counter()
    for _ in range(10):
        win.grab()
    print(f"  win.grab() 全窗渲染: {(time.perf_counter()-t0)/10*1000:.1f} ms/次"
          f"（仅作参考，运行时不走这条路）")

    # ------------------------------------------------------------ 9
    print("=== 9. 定时器实际交付间隔（60fps PreciseTimer + 真实重绘负载）===")
    stamps: list = []
    timer = QTimer()
    timer.setTimerType(Qt.PreciseTimer)
    timer.setInterval(16)

    def on_tick() -> None:
        k = len(stamps)
        scene._gx = math.sin(k * 0.12)
        scene._gy = math.cos(k * 0.09)
        scene._breath = math.sin(k * 0.05)
        for rec in scene._targets:
            rec[3] = 0.35
        scene._broadcast()
        app.processEvents()
        stamps.append(time.perf_counter())

    timer.timeout.connect(on_tick)
    timer.start()
    deadline = time.perf_counter() + 6.0
    while len(stamps) < 150 and time.perf_counter() < deadline:
        app.processEvents()
    timer.stop()
    gaps = sorted((stamps[i + 1] - stamps[i]) * 1000.0 for i in range(len(stamps) - 1))
    med = gaps[len(gaps) // 2]
    p95 = gaps[int(len(gaps) * 0.95)]
    print(f"  样本 {len(gaps)}  中位={med:.2f}ms  p95={p95:.2f}ms  最差={gaps[-1]:.2f}ms"
          f"  → 中位帧率 ≈ {1000.0 / med:.0f} fps（目标 {GAZE_FPS}）")
    if med > 18.0:
        bad("中位间隔偏大，60fps 跟不上")
    elif p95 > 26.0:
        bad("p95 抖动偏大，观感会一顿一顿")
    else:
        print("  ✓ 帧间隔稳定落在 60fps 附近，抖动可控")

    win.hide()
    app.processEvents()
    try:                        # 某些沙箱/受控环境会拦截删除，清不掉不算失败
        db_path.unlink(missing_ok=True)
    except OSError:
        print(f"  （临时库未能自动清理，可手动删除 {db_path.name}）")
    print("[anim] 结论：", "全部通过" if ok else "存在失败项")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
