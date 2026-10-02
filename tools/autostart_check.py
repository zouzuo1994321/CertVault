# -*- coding: utf-8 -*-
"""开机自启回归探针（v1.5.0 新增）。

⚠️ 测试策略：**绝不动真实的注册表项**（用户自己的开机启动项）。
探针用 monkeypatch 把 `VALUE_NAME` 换成测试专属的名字，
在 `HKCU\\...\\Run` 下建一个临时项、测完立刻删掉。
这样既能真实验证 winreg 读写行为，又不会污染用户环境。

用法：<venv>/Scripts/python.exe tools/autostart_check.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication     # noqa: E402

TEST_VALUE = "证书管理库 CertVault __SELFTEST__"


def main() -> int:
    from app import autostart
    import winreg

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

    # 用干净的值名开始
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                        0, winreg.KEY_SET_VALUE) as k:
        try:
            winreg.DeleteValue(k, TEST_VALUE)
        except FileNotFoundError:
            pass

    print("[autostart] ① 环境判定")
    check(os.name == "nt", "当前是 Windows")
    check(autostart.RUN_KEY ==
          r"Software\Microsoft\Windows\CurrentVersion\Run",
          f"注册表路径正确（HKCU，无管理员权限）：{autostart.RUN_KEY}")
    check(isinstance(autostart.is_supported(), bool), "is_supported() 返回布尔")

    print("[autostart] ② 开发态必须拒绝（不能把 python.exe 写进启动项）")
    # 源码态下 is_frozen() 为 False
    if not autostart.is_frozen():
        check(not autostart.is_supported(), "开发态is_supported() 为 False")
        check("开发态" in autostart.status(), f"status() 如实说明原因：{autostart.status()[:30]}…")
        raised = False
        try:
            autostart.enable()
        except autostart.AutostartUnavailable:
            raised = True
        check(raised, "开发态调enable() 抛 AutostartUnavailable（而不是写坏启动项）")
        err = autostart.sync(True)
        check(err is not None, f"开发态 sync(True) 如实返回原因而非静默成功：{str(err)[:30]}…")

    print("[autostart] ③ 注册表读写（用测试值名，不碰用户真实项）")
    orig_name = autostart.VALUE_NAME
    autostart.VALUE_NAME = TEST_VALUE
    try:
        check(autostart.is_enabled() is False, "初始状态：未启用")
        check(autostart.sync(False) is None, "sync(False) 在未启用时返回 None（幂等）")
        check(autostart.is_enabled() is False, "sync(False) 后仍未启用")

        # 手动塞一个值，验证 is_enabled 读得到
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, TEST_VALUE, 0, winreg.REG_SZ, r'"C:\fake\app.exe"')
        check(autostart.is_enabled() is True, "写入后可读回（is_enabled 为 True）")

        # sync(False) 应当把它删掉
        check(autostart.sync(False) is None, "sync(False) 返回 None")
        check(autostart.is_enabled() is False, "sync(False) 已删除注册表项")

        # 冻结态下的 enable()
        orig_frozen = autostart.is_frozen
        autostart.is_frozen = lambda: True
        try:
            check(autostart.is_supported() is True, "模拟冻结态 is_supported() 为 True")
            cmd = autostart._command()
            check(cmd.startswith('"') and cmd.endswith('"'),
                  f"启动命令带引号（路径含空格/中文才不会截断）：{cmd[:34]}…")
            check(os.path.basename(cmd.strip('"')).endswith(".exe"),
                  "命令指向 exe 文件")
            autostart.enable()
            check(autostart.is_enabled() is True, "enable() 写入成功")
            # 核对注册表里存的就是带引号的路径
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY) as k:
                v, _ = winreg.QueryValueEx(k, TEST_VALUE)
            check(v == cmd, "注册表里的值与 _command() 一致")
            autostart.disable()
            check(autostart.is_enabled() is False, "disable() 删除成功")
            # 幂等：再删一次不报错
            autostart.disable()
            check(autostart.is_enabled() is False, "disable() 重复调用幂等")
        finally:
            autostart.is_frozen = orig_frozen
    finally:
        autostart.VALUE_NAME = orig_name
        # 清理测试项（保险起见，即使上面某步抛异常也执行）
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, autostart.RUN_KEY,
                                0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, TEST_VALUE)
        except FileNotFoundError:
            pass

    check(autostart.is_enabled() is False, "测试值名已清理，未留下残留")

    print("[autostart] ④ 设置项与 UI 接线")
    from app.db import Database
    tmp = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "data", "_autostart.db")
    if os.path.exists(tmp):
        os.remove(tmp)
    db = Database(tmp)
    check(db.get_setting("autostart", "0") == "0", "新库默认 autostart=0（不开机自启）")
    db.set_setting("autostart", "1")
    check(db.get_setting("autostart", "0") == "1", "autostart 可正常写入/读出")
    db.close()
    os.remove(tmp)

    app = QApplication.instance() or QApplication(sys.argv)
    from app import palette
    palette.apply_palette(app)
    from app.dialogs import SettingsDialog

    db2 = Database()
    dlg = SettingsDialog(db2)
    dlg.show()
    app.processEvents()
    check(hasattr(dlg, "cb_autostart"), "设置面板有开机自启开关")
    check(hasattr(dlg, "lb_autostart"), "设置面板有状态说明文字")
    check(dlg.cb_autostart.isEnabled() is False,
          "开发态下开关被禁用（不让用户勾一个无效设置）")
    txt = dlg.lb_autostart.text()
    check(bool(txt) and "开发态" in txt, f"状态文字说明了原因：{txt[:34]}…")
    dlg.reject()
    db2.close()

    print("[autostart] 结论：", end=" ")
    if fails:
        print(f"失败 {len(fails)} 项")
        for f in fails:
            print("   -", f)
        return 1
    print(f"全部通过（{ok} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())