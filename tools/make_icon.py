# -*- coding: utf-8 -*-
"""生成 assets/app.ico —— 多尺寸 PNG 内嵌 ICO（Vista+ 格式）。

Qt 的 ICO 写入支持不可靠，这里直接手写 ICONDIR/ICONDIRENTRY 结构，
把 QPainter 绘制的各尺寸 PNG 塞进同一个 ico 文件。
"""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

# 注意：不要用 QT_QPA_PLATFORM=offscreen —— 该插件在 Windows 下会导致
# QGuiApplication 退出时段错误，且字体库为空。这里使用默认平台，仅绘制图形不建窗口。
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SIZES = [16, 24, 32, 48, 64, 128, 256]


def render_png(size: int) -> bytes:
    """渲染指定尺寸的 PNG 字节。

    注意：PySide 里 `QBuffer(QByteArray())` 会让 QByteArray 临时对象被回收，
    进而访问已释放内存导致段错误；因此直接落临时文件再读回。
    """
    import tempfile
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    from app.icons import paint_logo
    paint_logo(p, float(size))
    p.end()

    tmp = Path(tempfile.mkdtemp(prefix="certvault_ico_")) / f"{size}.png"
    assert img.save(str(tmp), "PNG"), f"保存 {size}px PNG 失败"
    data = tmp.read_bytes()
    try:
        tmp.unlink()
        tmp.parent.rmdir()
    except OSError:
        pass
    return data


def build_ico(out_path: Path, pngs: dict) -> Path:
    entries = b""
    blobs = b""
    offset = 6 + 16 * len(pngs)
    for size, data in pngs.items():
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                               len(data), offset)
        blobs += data
        offset += len(data)
    header = struct.pack("<HHH", 0, 1, len(pngs))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(header + entries + blobs)
    return out_path


def main() -> int:
    from PySide6.QtGui import QGuiApplication
    _ = QGuiApplication(sys.argv)

    pngs = {s: render_png(s) for s in SIZES}
    out = build_ico(ROOT / "assets" / "app.ico", pngs)

    # 同时导出一张 512px PNG 备用（README 展示 / 桌面快捷方式）
    big = render_png(256)
    png_path = ROOT / "assets" / "logo.png"
    png_path.write_bytes(big)

    print(f"[icon] 已生成 {out}  ({out.stat().st_size} 字节, "
          f"{len(SIZES)} 个尺寸: {SIZES})")
    print(f"[icon] 已生成 {png_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
