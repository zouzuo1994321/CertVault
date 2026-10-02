# -*- coding: utf-8 -*-
"""全部图标由 QPainter 现场绘制 —— 不依赖任何外部图片资源，任意尺寸都清晰。

之所以不用字体图标 / emoji：Windows 上不同版本字形差异大，且彩色 emoji 无法随主题变色。
"""

from __future__ import annotations

import math

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QIcon, QImage, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QRadialGradient)

from . import theme

# ---------------------------------------------------------------- 绘制工具


def _pen(p: QPainter, color: QColor, s: float, w: float = 0.085) -> None:
    pen = QPen(color)
    pen.setWidthF(max(1.0, s * w))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def _line(p: QPainter, x1, y1, x2, y2, s) -> None:
    p.drawLine(QPointF(x1 * s, y1 * s), QPointF(x2 * s, y2 * s))


def _rrect(p: QPainter, x, y, w, h, s, r=0.16) -> None:
    p.drawRoundedRect(QRectF(x * s, y * s, w * s, h * s), r * s, r * s)


# ------------------------------------------------------------------ 各图标


def _i_dashboard(p, s, c):
    for x, y in ((0.14, 0.14), (0.56, 0.14), (0.14, 0.56), (0.56, 0.56)):
        _rrect(p, x, y, 0.30, 0.30, s, 0.07)


def _i_cert(p, s, c):
    p.drawRoundedRect(QRectF(0.12 * s, 0.14 * s, 0.60 * s, 0.50 * s), 0.07 * s, 0.07 * s)
    _line(p, 0.22, 0.29, 0.62, 0.29, s)
    _line(p, 0.22, 0.42, 0.55, 0.42, s)
    _line(p, 0.22, 0.55, 0.48, 0.55, s)
    p.drawEllipse(QPointF(0.73 * s, 0.68 * s), 0.15 * s, 0.15 * s)
    _line(p, 0.67, 0.80, 0.64, 0.94, s)
    _line(p, 0.79, 0.80, 0.82, 0.94, s)


def _i_bell(p, s, c):
    path = QPainterPath()
    path.moveTo(0.26 * s, 0.70 * s)
    path.lineTo(0.26 * s, 0.44 * s)
    path.cubicTo(0.26 * s, 0.26 * s, 0.74 * s, 0.26 * s, 0.74 * s, 0.44 * s)
    path.lineTo(0.74 * s, 0.70 * s)
    path.closeSubpath()
    p.drawPath(path)
    _line(p, 0.16, 0.71, 0.84, 0.71, s)
    path2 = QPainterPath()
    path2.moveTo(0.42 * s, 0.79 * s)
    path2.lineTo(0.44 * s, 0.86 * s)
    path2.cubicTo(0.50 * s, 0.92 * s, 0.56 * s, 0.86 * s, 0.56 * s, 0.79 * s)
    p.setBrush(QBrush(c))
    p.drawPath(path2)
    p.setBrush(Qt.NoBrush)


def _i_calendar(p, s, c):
    _rrect(p, 0.14, 0.20, 0.72, 0.64, s, 0.09)
    _line(p, 0.14, 0.38, 0.86, 0.38, s)
    _line(p, 0.32, 0.12, 0.32, 0.26, s)
    _line(p, 0.68, 0.12, 0.68, 0.26, s)
    p.setBrush(QBrush(c))
    for x in (0.28, 0.46, 0.64):
        p.drawEllipse(QPointF(x * s, 0.60 * s), 0.045 * s, 0.045 * s)
    p.setBrush(Qt.NoBrush)


def _i_book(p, s, c):
    p.drawRoundedRect(QRectF(0.14 * s, 0.18 * s, 0.32 * s, 0.64 * s), 0.05 * s, 0.05 * s)
    p.drawRoundedRect(QRectF(0.54 * s, 0.18 * s, 0.32 * s, 0.64 * s), 0.05 * s, 0.05 * s)
    _line(p, 0.50, 0.18, 0.50, 0.82, s)


def _i_info(p, s, c):
    p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.36 * s, 0.36 * s)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(0.5 * s, 0.30 * s), 0.045 * s, 0.045 * s)
    p.setBrush(Qt.NoBrush)
    _line(p, 0.50, 0.44, 0.50, 0.70, s)


def _i_plus(p, s, c):
    _line(p, 0.50, 0.18, 0.50, 0.82, s)
    _line(p, 0.18, 0.50, 0.82, 0.50, s)


def _i_edit(p, s, c):
    p.save()
    p.translate(0.5 * s, 0.5 * s)
    p.rotate(-45)
    p.drawRoundedRect(QRectF(-0.09 * s, -0.40 * s, 0.18 * s, 0.62 * s), 0.04 * s, 0.04 * s)
    p.drawLine(QPointF(-0.09 * s, 0.22 * s), QPointF(0.09 * s, 0.22 * s))
    p.restore()
    _line(p, 0.24, 0.76, 0.30, 0.84, s)


def _i_trash(p, s, c):
    _line(p, 0.16, 0.26, 0.84, 0.26, s)
    _line(p, 0.40, 0.16, 0.60, 0.16, s)
    p.drawPolyline([QPointF(0.24 * s, 0.30 * s), QPointF(0.28 * s, 0.86 * s),
                    QPointF(0.72 * s, 0.86 * s), QPointF(0.76 * s, 0.30 * s)])
    _line(p, 0.42, 0.42, 0.42, 0.74, s)
    _line(p, 0.58, 0.42, 0.58, 0.74, s)


def _i_search(p, s, c):
    p.drawEllipse(QPointF(0.44 * s, 0.44 * s), 0.26 * s, 0.26 * s)
    _line(p, 0.63, 0.63, 0.84, 0.84, s)


def _i_export(p, s, c):
    _line(p, 0.50, 0.14, 0.50, 0.60, s)
    p.drawPolyline([QPointF(0.34 * s, 0.44 * s), QPointF(0.50 * s, 0.60 * s),
                    QPointF(0.66 * s, 0.44 * s)])
    p.drawPolyline([QPointF(0.20 * s, 0.66 * s), QPointF(0.20 * s, 0.86 * s),
                    QPointF(0.80 * s, 0.86 * s), QPointF(0.80 * s, 0.66 * s)])


def _i_import(p, s, c):
    _line(p, 0.50, 0.60, 0.50, 0.14, s)
    p.drawPolyline([QPointF(0.34 * s, 0.44 * s), QPointF(0.50 * s, 0.60 * s),
                    QPointF(0.66 * s, 0.44 * s)])
    p.drawPolyline([QPointF(0.20 * s, 0.66 * s), QPointF(0.20 * s, 0.86 * s),
                    QPointF(0.80 * s, 0.86 * s), QPointF(0.80 * s, 0.66 * s)])


def _i_refresh(p, s, c):
    p.drawArc(QRectF(0.18 * s, 0.18 * s, 0.64 * s, 0.64 * s), 55 * 16, 250 * 16)
    _line(p, 0.72, 0.14, 0.74, 0.40, s)
    _line(p, 0.74, 0.40, 0.48, 0.34, s)


def _i_close(p, s, c):
    _line(p, 0.24, 0.24, 0.76, 0.76, s)
    _line(p, 0.76, 0.24, 0.24, 0.76, s)


def _i_check(p, s, c):
    p.drawPolyline([QPointF(0.20 * s, 0.52 * s), QPointF(0.42 * s, 0.74 * s),
                    QPointF(0.82 * s, 0.26 * s)])


def _i_min(p, s, c):
    """最小化：一条横线。"""
    _line(p, 0.22, 0.52, 0.78, 0.52, s)


def _i_max(p, s, c):
    """最大化：一个方框。"""
    _rrect(p, 0.24, 0.24, 0.52, 0.52, s, 0.06)


def _i_restore(p, s, c):
    """还原：两个错位的方框。"""
    _rrect(p, 0.16, 0.32, 0.44, 0.44, s, 0.06)
    p.drawPolyline([QPointF(0.32 * s, 0.32 * s), QPointF(0.32 * s, 0.16 * s),
                    QPointF(0.84 * s, 0.16 * s), QPointF(0.84 * s, 0.68 * s),
                    QPointF(0.68 * s, 0.68 * s)])


def _i_chevron_left(p, s, c):
    p.drawPolyline([QPointF(0.62 * s, 0.20 * s), QPointF(0.36 * s, 0.50 * s),
                    QPointF(0.62 * s, 0.80 * s)])


def _i_chevron_right(p, s, c):
    p.drawPolyline([QPointF(0.38 * s, 0.20 * s), QPointF(0.64 * s, 0.50 * s),
                    QPointF(0.38 * s, 0.80 * s)])


def _i_zoom_in(p, s, c):
    p.drawEllipse(QPointF(0.44 * s, 0.44 * s), 0.26 * s, 0.26 * s)
    _line(p, 0.63, 0.63, 0.84, 0.84, s)
    _line(p, 0.44, 0.32, 0.44, 0.56, s)
    _line(p, 0.32, 0.44, 0.56, 0.44, s)


def _i_zoom_out(p, s, c):
    p.drawEllipse(QPointF(0.44 * s, 0.44 * s), 0.26 * s, 0.26 * s)
    _line(p, 0.63, 0.63, 0.84, 0.84, s)
    _line(p, 0.32, 0.44, 0.56, 0.44, s)


def _i_fit(p, s, c):
    _line(p, 0.12, 0.28, 0.12, 0.72, s)
    _line(p, 0.88, 0.28, 0.88, 0.72, s)
    _line(p, 0.28, 0.50, 0.72, 0.50, s)
    p.drawPolyline([QPointF(0.38 * s, 0.38 * s), QPointF(0.24 * s, 0.50 * s),
                    QPointF(0.38 * s, 0.62 * s)])
    p.drawPolyline([QPointF(0.62 * s, 0.38 * s), QPointF(0.76 * s, 0.50 * s),
                    QPointF(0.62 * s, 0.62 * s)])


def _i_doc(p, s, c):
    path = QPainterPath()
    path.moveTo(0.22 * s, 0.10 * s)
    path.lineTo(0.60 * s, 0.10 * s)
    path.lineTo(0.80 * s, 0.30 * s)
    path.lineTo(0.80 * s, 0.90 * s)
    path.lineTo(0.22 * s, 0.90 * s)
    path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline([QPointF(0.60 * s, 0.10 * s), QPointF(0.60 * s, 0.30 * s),
                    QPointF(0.80 * s, 0.30 * s)])
    _line(p, 0.33, 0.50, 0.69, 0.50, s)
    _line(p, 0.33, 0.64, 0.69, 0.64, s)
    _line(p, 0.33, 0.78, 0.55, 0.78, s)


def _i_pdf(p, s, c):
    path = QPainterPath()
    path.moveTo(0.22 * s, 0.10 * s)
    path.lineTo(0.60 * s, 0.10 * s)
    path.lineTo(0.80 * s, 0.30 * s)
    path.lineTo(0.80 * s, 0.90 * s)
    path.lineTo(0.22 * s, 0.90 * s)
    path.closeSubpath()
    p.drawPath(path)
    p.drawPolyline([QPointF(0.60 * s, 0.10 * s), QPointF(0.60 * s, 0.30 * s),
                    QPointF(0.80 * s, 0.30 * s)])
    p.drawRoundedRect(QRectF(0.18 * s, 0.50 * s, 0.56 * s, 0.24 * s), 0.05 * s, 0.05 * s)


def _i_folder(p, s, c):
    path = QPainterPath()
    path.moveTo(0.12 * s, 0.80 * s)
    path.lineTo(0.12 * s, 0.26 * s)
    path.lineTo(0.42 * s, 0.26 * s)
    path.lineTo(0.50 * s, 0.36 * s)
    path.lineTo(0.88 * s, 0.36 * s)
    path.lineTo(0.88 * s, 0.80 * s)
    path.closeSubpath()
    p.drawPath(path)


def _i_clock(p, s, c):
    p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.36 * s, 0.36 * s)
    _line(p, 0.50, 0.50, 0.50, 0.28, s)
    _line(p, 0.50, 0.50, 0.68, 0.60, s)


def _i_warn(p, s, c):
    p.drawPolyline([QPointF(0.50 * s, 0.12 * s), QPointF(0.92 * s, 0.84 * s),
                    QPointF(0.08 * s, 0.84 * s), QPointF(0.50 * s, 0.12 * s)])
    _line(p, 0.50, 0.38, 0.50, 0.62, s)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(0.50 * s, 0.73 * s), 0.038 * s, 0.038 * s)
    p.setBrush(Qt.NoBrush)


def _i_settings(p, s, c):
    p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.30 * s, 0.30 * s)
    p.drawEllipse(QPointF(0.5 * s, 0.5 * s), 0.10 * s, 0.10 * s)
    import math
    for i in range(8):
        a = math.radians(i * 45)
        x1, y1 = 0.5 + 0.30 * math.cos(a), 0.5 + 0.30 * math.sin(a)
        x2, y2 = 0.5 + 0.46 * math.cos(a), 0.5 + 0.46 * math.sin(a)
        _line(p, x1, y1, x2, y2, s)


def _i_database(p, s, c):
    p.drawEllipse(QPointF(0.5 * s, 0.24 * s), 0.32 * s, 0.13 * s)
    _line(p, 0.18, 0.24, 0.18, 0.76, s)
    _line(p, 0.82, 0.24, 0.82, 0.76, s)
    p.drawArc(QRectF(0.18 * s, 0.37 * s, 0.64 * s, 0.26 * s), 180 * 16, 180 * 16)
    p.drawArc(QRectF(0.18 * s, 0.63 * s, 0.64 * s, 0.26 * s), 180 * 16, 180 * 16)


def _i_table(p, s, c):
    _rrect(p, 0.12, 0.18, 0.76, 0.64, s, 0.07)
    _line(p, 0.12, 0.38, 0.88, 0.38, s)
    _line(p, 0.12, 0.60, 0.88, 0.60, s)
    _line(p, 0.42, 0.38, 0.42, 0.82, s)


def _i_star(p, s, c):
    path = QPainterPath()
    import math
    for i in range(10):
        r = 0.40 if i % 2 == 0 else 0.17
        a = math.radians(-90 + i * 36)
        x, y = 0.5 + r * math.cos(a), 0.5 + r * math.sin(a)
        path.moveTo(x * s, y * s) if i == 0 else path.lineTo(x * s, y * s)
    path.closeSubpath()
    p.setBrush(QBrush(c))
    p.drawPath(path)
    p.setBrush(Qt.NoBrush)


def _i_open(p, s, c):
    _rrect(p, 0.14, 0.30, 0.46, 0.56, s, 0.07)
    _line(p, 0.52, 0.14, 0.86, 0.14, s)
    p.drawPolyline([QPointF(0.68 * s, 0.30 * s), QPointF(0.86 * s, 0.14 * s),
                    QPointF(0.70 * s, 0.12 * s)])


def _i_float(p, s, c):
    """悬浮窗：一个窗口轮廓 + 右下角弹出的浮层（实心），一眼看出「飘在上面」。"""
    _rrect(p, 0.10, 0.14, 0.60, 0.46, s, 0.08)
    p.setBrush(QBrush(c))
    p.drawRoundedRect(QRectF(0.42 * s, 0.46 * s, 0.48 * s, 0.42 * s), 0.07 * s, 0.07 * s)
    p.setBrush(Qt.NoBrush)


def _i_ontop(p, s, c):
    """置顶：顶边横杠 + 指向它的箭头。"""
    _line(p, 0.18, 0.20, 0.82, 0.20, s)
    _line(p, 0.50, 0.86, 0.50, 0.40, s)
    p.drawPolyline([QPointF(0.32 * s, 0.56 * s), QPointF(0.50 * s, 0.38 * s),
                    QPointF(0.68 * s, 0.56 * s)])


def _i_chevron_up(p, s, c):
    p.drawPolyline([QPointF(0.24 * s, 0.64 * s), QPointF(0.50 * s, 0.36 * s),
                    QPointF(0.76 * s, 0.64 * s)])


def _i_chevron_down(p, s, c):
    p.drawPolyline([QPointF(0.24 * s, 0.38 * s), QPointF(0.50 * s, 0.66 * s),
                    QPointF(0.76 * s, 0.38 * s)])


def _i_grip(p, s, c):
    """拖动点：两行三点。"""
    p.setBrush(QBrush(c))
    for y in (0.40, 0.62):
        for x in (0.34, 0.50, 0.66):
            p.drawEllipse(QPointF(x * s, y * s), 0.05 * s, 0.05 * s)
    p.setBrush(Qt.NoBrush)


def _i_more(p, s, c):
    """更多操作：横向三点。"""
    p.setBrush(QBrush(c))
    for x in (0.26, 0.50, 0.74):
        p.drawEllipse(QPointF(x * s, 0.5 * s), 0.07 * s, 0.07 * s)
    p.setBrush(Qt.NoBrush)


# ------------------------------------------------------- 联系作者（品牌标记）
# ★这三个是「官方真实轮廓」，但**不是**直接贴图：
#   官方素材是白色硬边位图，RGB 恒为 255 —— 放到浅色卡面上几乎看不见
#   （用户第一次给的就是白底图，渲染出来是一片空白）。
# 所以只从素材里取alpha（覆盖度）当**遮罩**，运行时用品牌色去填。
# 这样轮廓是官方的、颜色可随主题换，而且不必往单文件 exe 里塞图片资源
# （遮罩数据见app/brand_masks.py，由 tools/bake_brand.py 从原始 PNG 烘焙）。
#
# 旧版是手绘简化标记（圆脸猫 / 电视机 / 眼睛），尺寸小到 19px 时辨识度明显不如官方轮廓。

_MASK_CACHE: dict = {}


def brand_mask(key: str) -> QImage | None:
    """取烘焙好的品牌遮罩（灰度图，灰度值 = 覆盖度），带进程内缓存。"""
    if key in _MASK_CACHE:
        return _MASK_CACHE[key]
    from . import brand_masks

    b64 = brand_masks.BRAND_MASKS.get(key)
    if not b64:
        _MASK_CACHE[key] = None
        return None
    raw = QByteArray.fromBase64(b64.encode("ascii"))
    img = QImage()
    if not img.loadFromData(raw, "PNG"):
        _MASK_CACHE[key] = None
        return None
    # ⚠️ **不要 `convertToFormat(Grayscale8)`** —— 那取的是 RGB 亮度，
    # 而烘焙出来的 PNG 是「8 位灰度图」当遮罩用的，转过去就变回全白。
    # 我们要的本来就是这8 位灰度值本身，直接留原格式即可。
    if img.format() != QImage.Format_Grayscale8:
        img = img.convertToFormat(QImage.Format_Grayscale8)
    _MASK_CACHE[key] = img
    return img


def _draw_brand(p: QPainter, s: float, c: QColor, key: str, scale: float = 0.72) -> bool:
    """把品牌遮罩按品牌色填到 (0,0,s,s) 里。成功返回 True。

    `scale` 是图形占画布的比例 —— 遮罩已裁掉原图留白，这里再留一点余量，
    免得标识顶到画布边缘（尤其带尖角的 GitHub 猫耳）。
    非正方形标识按 `BRAND_BOX` 等比缩放居中，否则会被拉变形。

    ⚠️⚠️ **遮罩染色只能逐点构造，不能用 `setAlphaChannel`/`CompositionMode_SourceIn`**：
    在 PySide6 上二者对 `Format_Grayscale8` 源**都不生效**
    （`setAlphaChannel` 实测整张仍 100% 不透明，图标渲染成一个实心方块）。
    稳妥做法是拿 `constScanLine` 的字节当alpha，`setPixel` 拼成 (alpha, r, g, b)。
    ⚠️ 8 位单通道图的 `pixel()` 返回值是错乱的 32 位数（实测 4278190080），
    读灰度只能用 `constScanLine(y)[x]`。
    """
    img = brand_mask(key)
    if img is None:
        return False
    from . import brand_masks

    bw, bh = brand_masks.BRAND_BOX.get(key, (1.0, 1.0))
    ratio = bw / bh if bh > 0 else 1.0
    if ratio >= 1.0:                       # 横宽或方形：按宽定尺寸
        box_w, box_h = s * scale, s * scale / ratio
    else:                                  # 竖高：按高定尺寸
        box_h, box_w = s * scale, s * scale * ratio

    # ★ 遮罩按**设备像素**分辨率生成再交给Qt 缩放 —— 直接按逻辑像素造图在 dpr=2 下会发虚。
    # ⚠️⚠️ **必须用 `drawImage(QRectF, ...)` 显式给目标矩形，不能用 `drawImage(QPointF, ...)`**：
    # 后者是 1:1 逻辑像素绘制，会把一张 38px 的图当 38 逻辑像素塞进 19px 的画布 ⇒
    # 图形**四周被裁掉一截**（用户看到的「logo 没有显示完全」就是这个）。
    # 实测：同一张 38px 图用 QPointF 画红条像素 760（应为 380，正好大一倍），
    # 用 QRectF 画则 380/1064 与期望完全一致。
    dpr = p.device().devicePixelRatio() if p.device() is not None else 1.0
    px_w = max(1, int(round(box_w * dpr)))
    px_h = max(1, int(round(box_h * dpr)))

    mask = img.scaled(px_w, px_h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    cr, cg, cb, _ = c.getRgb()
    tinted = QImage(px_w, px_h, QImage.Format_ARGB32)
    for y in range(px_h):
        row = mask.constScanLine(y)
        for x in range(px_w):
            v = row[x]
            tinted.setPixel(x, y, (v << 24) | (cr << 16) | (cg << 8) | cb)
    p.drawImage(QRectF((s - box_w) / 2.0, (s - box_h) / 2.0, box_w, box_h), tinted)
    return True


def _i_github(p, s, c):
    """GitHub：官方 Octocat 剪影（遮罩填充）。"""
    if _draw_brand(p, s, c, "github", 0.86):
        return
    _brand_fallback_github(p, s, c)


def _i_bilibili(p, s, c):
    """哔哩哔哩：官方电视机（遮罩填充）。"""
    if _draw_brand(p, s, c, "bilibili", 0.88):
        return
    _brand_fallback_bilibili(p, s, c)


def _i_weibo(p, s, c):
    """微博：官方「眼」标识（遮罩填充）。"""
    if _draw_brand(p, s, c, "weibo", 0.90):
        return
    _brand_fallback_weibo(p, s, c)


# ---- 遮罩缺失时的兜底（数据文件损坏 / 名字写错时至少还能画出一个东西） ----


def _brand_fallback_github(p, s, c):
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(0.50 * s, 0.60 * s), 0.32 * s, 0.32 * s)
    p.drawPolygon(QPolygonF([QPointF(0.20 * s, 0.46 * s), QPointF(0.31 * s, 0.12 * s),
                             QPointF(0.45 * s, 0.30 * s)]))
    p.drawPolygon(QPolygonF([QPointF(0.80 * s, 0.46 * s), QPointF(0.69 * s, 0.12 * s),
                             QPointF(0.55 * s, 0.30 * s)]))
    p.setBrush(Qt.NoBrush)


def _brand_fallback_bilibili(p, s, c):
    _line(p, 0.33, 0.22, 0.27, 0.08, s)
    _line(p, 0.67, 0.22, 0.73, 0.08, s)
    _rrect(p, 0.13, 0.22, 0.74, 0.58, s, 0.16)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(0.36 * s, 0.46 * s), 0.07 * s, 0.09 * s)
    p.drawEllipse(QPointF(0.64 * s, 0.46 * s), 0.07 * s, 0.09 * s)
    p.setBrush(Qt.NoBrush)
    _pen(p, c, s)
    _line(p, 0.36, 0.66, 0.64, 0.66, s)


def _brand_fallback_weibo(p, s, c):
    p.drawArc(QRectF(0.22 * s, 0.06 * s, 0.40 * s, 0.30 * s), 205 * 16, 130 * 16)
    p.drawArc(QRectF(0.34 * s, 0.14 * s, 0.40 * s, 0.30 * s), 205 * 16, 130 * 16)
    path = QPainterPath()
    path.moveTo(0.10 * s, 0.64 * s)
    path.quadTo(0.50 * s, 0.30 * s, 0.90 * s, 0.64 * s)
    path.quadTo(0.50 * s, 0.98 * s, 0.10 * s, 0.64 * s)
    p.drawPath(path)
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(c))
    p.drawEllipse(QPointF(0.50 * s, 0.64 * s), 0.12 * s, 0.12 * s)
    p.setBrush(Qt.NoBrush)


def _i_mail(p, s, c):
    """邮箱：信封 + 封口折线（无官方素材，仍手绘）。"""
    _rrect(p, 0.09, 0.24, 0.82, 0.54, s, 0.09)
    p.drawPolyline([QPointF(0.13 * s, 0.30 * s), QPointF(0.50 * s, 0.57 * s),
                    QPointF(0.87 * s, 0.30 * s)])


_DISPATCH = {
    "dashboard": _i_dashboard, "cert": _i_cert, "bell": _i_bell,
    "calendar": _i_calendar, "book": _i_book, "info": _i_info,
    "plus": _i_plus, "edit": _i_edit, "trash": _i_trash, "search": _i_search,
    "export": _i_export, "import": _i_import, "refresh": _i_refresh,
    "close": _i_close, "check": _i_check, "chevron-left": _i_chevron_left,
    "chevron-right": _i_chevron_right, "zoom-in": _i_zoom_in,
    "zoom-out": _i_zoom_out, "fit": _i_fit, "doc": _i_doc, "pdf": _i_pdf,
    "folder": _i_folder, "clock": _i_clock, "warn": _i_warn,
    "settings": _i_settings, "database": _i_database, "table": _i_table,
    "star": _i_star, "open": _i_open,
    "min": _i_min, "max": _i_max, "restore": _i_restore,
    "float": _i_float, "ontop": _i_ontop, "grip": _i_grip,
    "chevron-up": _i_chevron_up, "chevron-down": _i_chevron_down,
    "github": _i_github, "bilibili": _i_bilibili, "weibo": _i_weibo,
    "mail": _i_mail, "more": _i_more,
}


def pixmap(name: str, color: str = theme.TEXT, size: int = 20, dpr: float = 2.0) -> QPixmap:
    """绘制命名图标为 QPixmap（默认 2 倍图，避免高分屏发虚）。

    ⚠️ 不要在这里再 `p.scale(dpr, dpr)`：QPixmap 设过 devicePixelRatio 之后，
    QPainter 会自动按该比例建立初始变换，手动再缩放一次会让图标被放大 4 倍、
    只剩下左上角一小块（表现为「图标只画了一半 / 像乱码」）。
    """
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.transparent)
    fn = _DISPATCH.get(name)
    if fn is None:
        return px
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing, True)
    _pen(p, QColor(color), size)
    fn(p, size, QColor(color))
    p.end()
    return px


def icon(name: str, color: str = theme.TEXT, size: int = 20) -> QIcon:
    return QIcon(pixmap(name, color, size))


# ------------------------------------------------------------------- 徽标


def paint_logo(p: QPainter, size: float) -> None:
    """绘制应用徽标：深蓝圆角底 + 金色勋章 + 白色对勾。"""
    p.setRenderHint(QPainter.Antialiasing, True)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#24405c"))
    grad.setColorAt(1.0, QColor("#16222f"))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)

    cx = cy = size / 2
    # 勋章外圈扇贝
    p.setBrush(QBrush(QColor(theme.GOLD)))
    for i in range(12):
        a = math.radians(i * 30)
        p.drawEllipse(QPointF(cx + 0.30 * size * math.cos(a),
                              cy + 0.30 * size * math.sin(a)),
                      size * 0.075, size * 0.075)
    p.drawEllipse(QPointF(cx, cy), size * 0.30, size * 0.30)
    p.setBrush(QBrush(QColor("#f7e9b8")))
    p.drawEllipse(QPointF(cx, cy), size * 0.235, size * 0.235)

    if size >= 28:
        pen = QPen(QColor("#1b2a3a"))
        pen.setWidthF(size * 0.075)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(cx - 0.11 * size, cy + 0.005 * size)
        path.lineTo(cx - 0.025 * size, cy + 0.095 * size)
        path.lineTo(cx + 0.125 * size, cy - 0.095 * size)
        p.drawPath(path)


def paint_logo_gaze(p: QPainter, size: float, gx: float = 0.0,
                    gy: float = 0.0) -> None:
    """「视角跟随」版徽标：把徽标拆成 5 个图层，各自按不同幅度位移。

    Live2D 那种「转头」的观感，本质是**分层视差**：近处的图层动得多、远处的动得少。
    这里把底板当作背景（几乎不动），勋章扇贝环、金盘、对勾、玻璃高光依次递增位移，
    再叠上扇贝环随视线旋转、高光顺着视线滑移，就能在不引入任何模型文件的前提下
    做出同样的立体跟随感。

    参数 ``gx`` / ``gy`` 为归一化视线方向，取值 -1 ~ 1。
    """
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(size)
    cx = cy = s / 2.0

    def off(k: float) -> QPointF:
        return QPointF(gx * s * k, gy * s * k)

    # 1) 底板：视差最小，作为「身体」几乎不动
    o = off(0.028)
    grad = QLinearGradient(o.x(), o.y(), s + o.x(), s + o.y())
    grad.setColorAt(0.0, QColor("#2c4f70"))
    grad.setColorAt(0.55, QColor("#1d2e40"))
    grad.setColorAt(1.0, QColor("#131d27"))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(grad))
    p.drawRoundedRect(QRectF(o.x(), o.y(), s, s), s * 0.24, s * 0.24)

    # 2) 勋章扇贝环：整体位移 + 随视线轻微自转，像「转头」
    o = off(0.072)
    mcx, mcy = cx + o.x(), cy + o.y()
    p.setBrush(QBrush(QColor(theme.GOLD)))
    for i in range(12):
        a = math.radians(i * 30.0 + gx * 16.0)
        p.drawEllipse(QPointF(mcx + 0.30 * s * math.cos(a),
                              mcy + 0.30 * s * math.sin(a)),
                      s * 0.075, s * 0.075)

    # 3) 金盘 → 内盘
    o = off(0.092)
    p.drawEllipse(QPointF(cx + o.x(), cy + o.y()), s * 0.30, s * 0.30)
    o = off(0.108)
    p.setBrush(QBrush(QColor("#f7e9b8")))
    p.drawEllipse(QPointF(cx + o.x(), cy + o.y()), s * 0.235, s * 0.235)

    # 4) 玻璃高光：位移最大，顺着视线滑移
    o = off(0.21)
    hx, hy = cx + o.x() * 0.55, cy + o.y() * 0.55
    hi = QRadialGradient(QPointF(hx - s * 0.09, hy - s * 0.12), s * 0.32)
    hi.setColorAt(0.0, QColor(255, 255, 255, 135))
    hi.setColorAt(0.55, QColor(255, 255, 255, 45))
    hi.setColorAt(1.0, QColor(255, 255, 255, 0))
    p.setBrush(QBrush(hi))
    p.drawEllipse(QPointF(hx, hy), s * 0.32, s * 0.32)

    # 5) 对勾：视线跟随最明显的一层
    if s >= 22:
        o = off(0.126)
        ox, oy = cx + o.x(), cy + o.y()
        pen = QPen(QColor("#1b2a3a"))
        pen.setWidthF(s * 0.075)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(ox - 0.11 * s, oy + 0.005 * s)
        path.lineTo(ox - 0.025 * s, oy + 0.095 * s)
        path.lineTo(ox + 0.125 * s, oy - 0.095 * s)
        p.drawPath(path)


def logo_pixmap(size: int, dpr: float = 2.0) -> QPixmap:
    """渲染徽标位图。同样注意：QPixmap 的 dpr 已由 QPainter 自动应用，勿手动 scale。"""
    px = QPixmap(int(size * dpr), int(size * dpr))
    px.setDevicePixelRatio(dpr)
    px.fill(Qt.transparent)
    p = QPainter(px)
    paint_logo(p, float(size))
    p.end()
    return px


def app_icon() -> QIcon:
    ic = QIcon()
    for s in (16, 24, 32, 48, 64, 128, 256):
        ic.addPixmap(logo_pixmap(s, dpr=1.0))
    return ic
