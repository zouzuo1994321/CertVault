# -*- coding: utf-8 -*-
"""品牌标识渲染探针：把三个官方 logo 按各自主色渲染成放大图，便于肉眼核对。

用法：<venv>/Scripts/python.exe tools/brand_check.py
输出：build/diag/brand_*.png
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QApplication        # noqa: E402

from app import icons, palette, theme             # noqa: E402

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "build", "diag")

CASES = [
    ("github", "#24292f"),
    ("bilibili", "#00aeec"),     # 官方品牌蓝（粉 #fb7299 是辅助色）
    ("weibo", "#e6162d"),
    ("mail", "#c9a227"),
]


def sheet(size: int) -> QImage:
    """一行排开：徽标底色 + 图标，与 ContactRow 的实际观感一致。"""
    pad, badge, gap = 18, 34, 14
    w = pad + len(CASES) * (badge + gap) + pad
    img = QImage(w, badge + pad * 2, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    for i, (key, color) in enumerate(CASES):
        x = pad + i * (badge + gap)
        p.setPen(Qt.NoPen)
        # 复刻 pages._tint：品牌色淡底
        tint = QColor(color)
        tint.setAlpha(30)
        p.setBrush(tint)
        p.drawRoundedRect(QRectF(x, pad, badge, badge), 10, 10)
        # pixmap 是 dpr2 的设备像素（38x38），按逻辑尺寸 19 居中
        pm = icons.pixmap(key, color, 19)
        p.drawPixmap(QPointF(x + (badge - 19) / 2.0, pad + (badge - 19) / 2.0),
                     pm, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    return img


def big(key: str, color: str, size: int) -> QImage:
    """单个图标放大到 size，用于核对轮廓细节。"""
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(QColor("#ffffff"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    pm = icons.pixmap(key, color, size)
    p.drawPixmap(QPointF(0, 0), pm, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    return img


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    app = QApplication(sys.argv)
    palette.apply_palette(app)

    fails = []

    # 1) 遮罩必须能解出来，且不是全透明
    for key, color in CASES:
        if key == "mail":
            continue
        m = icons.brand_mask(key)
        if m is None:
            fails.append(f"{key}:遮罩解不出")
            continue
        if m.width() < 8 or m.height() < 8:
            fails.append(f"{key}: 遮罩尺寸异常 {m.width()}x{m.height()}")

    # 2) 每个图标都要真的画出东西（非全透明），否则页面上就是隐形
    for key, color in CASES:
        pm = icons.pixmap(key, color, 19)
        im = pm.toImage().convertToFormat(QImage.Format_ARGB32)
        opaque = 0
        total = 0
        for y in range(0, im.height(), 2):
            for x in range(0, im.width(), 2):
                total += 1
                if (im.pixel(x, y) >> 24) > 24:
                    opaque += 1
        ratio = opaque / max(1, total)
        # 遮罩法比手绘版实心度低一些（有镂空），但不能低于 8%
        if ratio < 0.08:
            fails.append(f"{key}: 19px 下实心度仅 {ratio:.1%}，几乎看不见")
        big(key, color, 128).save(os.path.join(OUT, f"brand_{key}_big.png"))
        print(f"[brand] {key:10s} 实心度 {ratio:6.1%}  遮罩 "
              f"{icons.brand_mask(key).width() if icons.brand_mask(key) else '-'}")

    # 3)★ 图形必须**完整落在画布内**（不越界）。曾经的 bug：
    #    drawImage(QPointF, img) 是 1:1 逻辑像素绘制，把 38px 的图塞进 19px
    #    画布 ⇒ 四周被裁掉一截（用户报「logo 没有显示完全」）。
    #    守卫：alpha 不得触及最外圈像素，且四周1~2px 必须透明。
    for key, color in CASES:
        im = icons.pixmap(key, color, 19).toImage().convertToFormat(
            QImage.Format_ARGB32)
        w, h = im.width(), im.height()

        def a(x, y):
            return (im.pixel(x, y) >> 24) & 0xFF

        edge = 0
        for x in range(w):
            edge += (1 if a(x, 0) > 24 else 0) + (1 if a(x, h - 1) > 24 else 0)
        for y in range(h):
            edge += (1 if a(0, y) > 24 else 0) + (1 if a(w - 1, y) > 24 else 0)
        if edge > 0:
            fails.append(f"{key}: 图形触到画布边缘（{edge} 个边缘像素不透明）"
                         f"—— 多半是 drawImage 用错了重载导致裁切")
        # 图形也必须真的画在画布**中央附近**，不能偏到一角
        cx = sum(x for y in range(h) for x in range(w) if a(x, y) > 24) / max(
            1, sum(1 for y in range(h) for x in range(w) if a(x, y) > 24))
        if not (0.3 * w < cx < 0.7 * w):
            fails.append(f"{key}: 图形重心偏在 cx={cx:.0f}/{w}，不在中央")

    sheet(0).save(os.path.join(OUT, "brand_sheet.png"))
    # 另存一份带尺寸的放大图，便于核对细节（预览器对同名文件有缓存）
    for key, color in CASES:
        big(key, color, 128).save(os.path.join(OUT, f"brand_zoom_{key}.png"))

    if fails:
        print("[brand] 失败项：")
        for f in fails:
            print("   -", f)
        return 1
    print("[brand] 结论： 全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())