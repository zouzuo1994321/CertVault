# -*- coding: utf-8 -*-
"""启动体验回归探针（v1.6.0 新增）。

验两件事：
  A. **静默运行** —— `tasklist` / `taskkill` 这类控制台程序在无控制台的GUI 程序里
     会被 Windows 自动分配新控制台 ⇒双击 exe 先闪一个黑 cmd 窗口。
     本项目 v1.5.0 引入了开机自启（内含 tasklist/taskkill），把这个老毛病带出来了。
     守卫：所有子进程调用都必须带 `CREATE_NO_WINDOW`。
  B. **启动动画不会把用户困住** —— 主窗口构造失败时动画必须被收掉；
     且动画自己也要有「到点自动退场」的兜底。

用法：<venv>/Scripts/python.exe tools/startup_check.py
"""
from __future__ import annotations

import io
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt                      # noqa: E402
from PySide6.QtWidgets import QApplication           # noqa: E402

TEST_VALUE = "证书管理库 CertVault __STARTUPTEST__"


def main() -> int:
    fails = []
    ok = 0

    def check(cond, label):
        nonlocal ok
        if cond:
            ok += 1
            print(f"   OK  {label}")
        else:
            fails.append(label)
            print(f"   FAIL {label}")

    print("[startup] ① 静默运行标志")
    from app import procutil
    flags = procutil.silent_flags()
    no_window = getattr(procutil, "_NO_WINDOW", 0)
    check(no_window == 0x08000000,
          f"CREATE_NO_WINDOW = 0x{no_window:08X}（0x08000000，不给子进程分配控制台）")
    check(flags & no_window == no_window, "silent_flags() 含 CREATE_NO_WINDOW")
    check(flags & procutil._SW_HIDE == procutil._SW_HIDE,
          "silent_flags() 含 SW_HIDE")
    # ★★ 反向守卫：STARTF_USESHOWWINDOW 会让 tasklist **永久挂死**。
    #   最初以为「三个标志一起给才彻底静默」，实测 8 种组合后确认它是有害的
    #   （冻结态症状：双击 exe 什么都不发生、进程还在但没窗口）。
    check(getattr(procutil, "_STARTF_USESHOWWINDOW", 0) == 0,
          "silent_flags() **不含** STARTF_USESHOWWINDOW（与 capture_output 组合会挂死）")
    check(not (flags & 0x00000001),
          f"实际标志位 0x{flags:08X} 里没有 STARTF_USESHOWWINDOW(0x1)")

    # ★ 真调一次 tasklist 验不挂死（带超时，挂了就是 FAIL 而不是把探针卡死）
    import subprocess as _sp
    t0 = time.time()
    try:
        r = _sp.run(["tasklist", "/FI", "IMAGENAME eq 证书管理库.exe",
                     "/FO", "CSV", "/NH"],
                    capture_output=True, timeout=15,
                    creationflags=flags, stdin=_sp.DEVNULL)
        dur = time.time() - t0
        check(dur < 8.0 and len(r.stdout) > 0,
              f"静默调用 tasklist 正常返回（{dur:.2f}s，{len(r.stdout)} 字节）")
    except Exception as exc:  # noqa: BLE001
        check(False, f"静默调用 tasklist 异常：{exc!r}")

    print("[startup] ② 真实调用 tasklist 不弹窗（用测试值名，不碰用户启动项）")
    import winreg
    from app import autostart
    orig = autostart.VALUE_NAME
    autostart.VALUE_NAME = TEST_VALUE
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                            0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, TEST_VALUE)
            except FileNotFoundError:
                pass
        # 走 singleton 的同一条路径（它内部用 procutil.run_silent）
        from app.singleton import kill_previous_instances
        killed = kill_previous_instances(lambda m: None)
        check(isinstance(killed, list), f"kill_previous_instances 正常返回 {killed}")
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, TEST_VALUE, 0, winreg.REG_SZ, r'"C:\x\a.exe"')
        check(autostart.is_enabled() is True, "临时启动项可读回")
        err = autostart.sync(False)
        check(err is None, f"sync(False) 静默清理成功（err={err}）")
        check(autostart.is_enabled() is False, "临时启动项已删除")
    finally:
        autostart.VALUE_NAME = orig
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, TEST_VALUE)
        except FileNotFoundError:
            pass

    print("[startup] ③ 业务代码不得再直接用裸 subprocess")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    offenders = []
    # procutil.py 就是那个封装实现本身，是唯一允许出现 subprocess 的地方
    for fn in os.listdir(os.path.join(root, "app")):
        if not fn.endswith(".py") or fn == "procutil.py":
            continue
        p = os.path.join(root, "app", fn)
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                s = line.strip()
                if s.startswith("#") or "procutil" in s:
                    continue
                if "subprocess.run(" in s or "subprocess.Popen(" in s:
                    offenders.append(f"app/{fn}:{i}")
    check(not offenders,
          f"app/ 下没有裸subprocess 调用（发现 {len(offenders)} 处）"
          + (f"：{offenders}" if offenders else "，procutil.py 除外"))

    app = QApplication.instance() or QApplication(sys.argv)
    from app import palette
    palette.apply_palette(app)

    print("[startup] ④ 启动动画：几何与自绘")
    from app import splash as sp

    # ★ Qt 会把 paintEvent 里的 Python 异常吞掉（只往 stderr 打、不影响任何返回值），
    #   所以这里把 stderr 重定向到缓冲，最后统一断言「一个异常都不许有」。
    #   否则会出现「探针全绿、实际界面某个元素凭空消失」的假绿。
    err_buf = io.StringIO()
    real_stderr = sys.stderr
    sys.stderr = err_buf
    try:
        s = sp.Splash()
        s.show()
        s.begin()
        # ★ 必须先等淡入跑完再抓图：α=0 时 paintEvent 直接 return 什么都不画，
        #   此时抓到的整张图都是全透明像素（`name()` 仍不等于 "#ffffff"，
        #   所以「画面非纯白」这种弱断言照样能过 —— 必须显式等 α 涨起来）。
        t0 = time.time()
        while s._alpha < 0.98 and time.time() - t0 < 3.0:
            app.processEvents()
            time.sleep(0.012)
        img = s.grab().toImage()
    finally:
        sys.stderr = real_stderr
    check(not err_buf.getvalue().strip(),
          "paintEvent 全程无异常"
          + (f"（Qt 内部报错：{err_buf.getvalue().strip().splitlines()[0][:120]}）"
             if err_buf.getvalue().strip() else ""))
    check(s._alpha > 0.98, f"淡入已到满（α={s._alpha:.2f}）")
    check(s.width() == sp.SPLASH_W and s.height() == sp.SPLASH_H,
          f"尺寸 {s.width()}x{s.height()}")
    check(bool(s.windowFlags() & Qt.FramelessWindowHint), "无边框")
    check(bool(s.windowFlags() & Qt.SplashScreen), "SplashScreen 标志（不进任务栏）")
    check(bool(s.windowFlags() & Qt.WindowStaysOnTopHint), "置顶")
    check(s.testAttribute(Qt.WA_TranslucentBackground), "半透明背景（真圆角自绘）")
    check(s.testAttribute(Qt.WA_ShowWithoutActivating), "不抢焦点")
    check(len(sp.STAGES) >= 3, f"阶段文案 {len(sp.STAGES)} 段：{sp.STAGES}")
    check(not img.isNull() and img.width() > 0,
          f"能渲染出画面（{img.width()}x{img.height()}）")
    # 不该是全白（说明真画了东西）。**必须同时看 alpha** ——
    # 全透明像素的 name() 也不是 "#ffffff"，只看颜色会把空图判成有内容。
    non_white = sum(1 for y in range(0, img.height(), 4)
                    for x in range(0, img.width(), 4)
                    if img.pixelColor(x, y).alpha() > 0
                    and img.pixelColor(x, y).name() != "#ffffff")
    check(non_white > 20, f"画面确有绘制（不透明且非白，采样命中 {non_white}）")
    # ★★ 徽标区域必须有内容。教训：paintEvent 里一个 TypeError 会被 Qt 吞掉
    #（只往 stderr 打、不影响返回码），画面照样「非纯白」（卡面白底就能过），
    # 但徽标其实一个像素都没画出来。只验整体非白是抓不到这种错的。
    logo_hits = sum(1 for y in range(sp.LOGO_TOP, sp.LOGO_TOP + sp.LOGO_SIZE, 2)
                    for x in range(0, s.width(), 2)
                    if img.pixelColor(x, y).alpha() > 0
                    and img.pixelColor(x, y).name() != "#ffffff")
    check(logo_hits > 30,
          f"徽标区域确有绘制（采样命中 {logo_hits}，为 0 说明徽标没画出来）")

    print("[startup] ⑤ 阶段推进与淡入")
    # 用独立实例：④ 那个 α 已经涨满，再验「淡入推进」没意义
    s1 = sp.Splash()
    s1.show()
    s1.begin()
    app.processEvents()
    a0 = s1._alpha
    s1.advance()
    check(s1._stage == 1, f"advance() 推进阶段 -> {s1._stage}")
    for _ in range(40):
        app.processEvents()
        time.sleep(0.012)
    check(s1._alpha > a0, f"淡入推进 {a0:.2f} -> {s1._alpha:.2f}")
    # 阶段号不能越过末段（否则 STAGES[stage] 越界）
    for _ in range(len(sp.STAGES) + 3):
        s1.advance()
    check(s1._stage == len(sp.STAGES) - 1,
          f"advance() 到末段即停（{s1._stage}，共 {len(sp.STAGES)} 段）")
    s1.shutdown()

    print("[startup] ⑥ ★ 兜底：走完阶段必须自动退场（不能把用户困住）")
    # 只 advance 不 finish，模拟调用方忘了收尾 / 抛异常的情况
    for _ in range(3):
        s.advance()
    t0 = time.time()
    closed = False
    # 上限 8s：自动退场要先等满 MIN_SHOW_MS(900ms) 再淡出 FADE_OUT_MS(260ms)
    while time.time() - t0 < 8.0:
        app.processEvents()
        time.sleep(0.02)
        if s._outro >= 1.0 or not s.isVisible():
            closed = True
            break
    check(closed, f"未调 finish() 也能自动淡出关闭（耗时 {time.time()-t0:.2f}s）")

    print("[startup] ⑦ shutdown() / finish() 的幂等与立刻性")
    s2 = sp.Splash()
    s2.show()
    s2.begin()
    app.processEvents()
    s2.finish()
    s2.finish()          # 第二次必须是空操作，不能抛异常
    s2.shutdown()
    s2.shutdown()
    check(s2.isVisible() is False, "finish() 幂等 + shutdown() 后窗口已关闭")
    check(getattr(s2, "_closing", False) is True, "_closing 标志已置位")

    print("[startup] ⑧ 主入口接线")
    with open(os.path.join(root, "main.py"), encoding="utf-8") as f:
        src = f.read()
    check("Splash()" in src, "main.py 创建了 Splash")
    check("splash.begin()" in src, "main.py 调用了 begin()")
    check(src.count("splash.advance()") >= 2,
          f"main.py 分阶段推进（{src.count('splash.advance()')} 次）")
    check("splash.finish()" in src, "main.py 调用了 finish()")
    check(src.count("splash.shutdown()") >= 2,
          f"异常路径都调了 shutdown()（{src.count('splash.shutdown()')} 处）")

    print("[startup] ⑨★★ 进程治理：绝不能杀掉自己的父进程（onefile 双进程）")
    # ★★ 这条守卫来自v1.6.0 的一个真 bug：PyInstaller onefile 下同一个 exe 有两个
    #   同名进程（bootloader 父 + 应用子）。原实现只排除 os.getpid()（应用自己），
    #   于是把 bootloader 也 taskkill /F 掉了 —— 父进程一死，子进程失去依附被挂起，
    #   表现为「双击 exe 什么都没发生、进程还在但不显示窗口」。
    from app import singleton as sg
    check(hasattr(sg, "_ancestor_pids"), "singleton 提供了 _ancestor_pids()")
    anc = sg._ancestor_pids()
    me = os.getpid()
    check(me not in anc, f"祖先集合不含自己（{sorted(anc)[:6]}）")
    check(len(anc) >= 1, f"祖先集合非空（本进程祖先 {sorted(anc)[:6]}）")
    # 当前进程的父亲一定在祖先集合里 —— 这是判定逻辑正确的核心断言
    import ctypes
    from ctypes import wintypes

    class _PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
                    ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    k32 = ctypes.windll.kernel32
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.restype = wintypes.BOOL
    k32.Process32NextW.restype = wintypes.BOOL
    snap = k32.CreateToolhelp32Snapshot(0x00000002, 0)
    parent = 0
    ent = _PE()
    ent.dwSize = ctypes.sizeof(_PE)
    if snap not in (0, ctypes.c_void_p(-1).value):
        try:
            if k32.Process32FirstW(snap, ctypes.byref(ent)):
                while True:
                    if int(ent.th32ProcessID) == me:
                        parent = int(ent.th32ParentProcessID)
                        break
                    if not k32.Process32NextW(snap, ctypes.byref(ent)):
                        break
        finally:
            k32.CloseHandle(snap)
    check(parent in anc,
          f"直接父进程 {parent} 在祖先集合里（漏了它就会杀掉 bootloader）")

    #★ 静态守卫：kill_previous_instances 里必须用集合判断而不是 `pid == me`
    with open(os.path.join(root, "app", "singleton.py"), encoding="utf-8") as f:
        sg_src = f.read()
    check("if pid == me:" not in sg_src,
          "singleton 不再用 `pid == me`（onefile 下会漏掉 bootloader）")
    check("protected" in sg_src and "_ancestor_pids()" in sg_src,
          "singleton 用 protected 集合（自己 + 整条祖先链）")

    # ★ 真的调一次 kill_previous_instances，确认不会把探针自己的父进程杀掉。
    #   冻结态才走清理分支，开发态直接 return []，所以这里只验「不崩、返回列表」。
    killed = sg.kill_previous_instances(lambda m: None)
    check(isinstance(killed, list), f"kill_previous_instances 返回 {killed}")
    check(os.getpid() == me, "调用后探针进程仍存活（没误杀自己）")

    print("[startup] 结论：", end=" ")
    if fails:
        print(f"失败 {len(fails)} 项")
        for f_ in fails:
            print("   -", f_)
        return 1
    print(f"全部通过（{ok} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())