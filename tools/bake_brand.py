"""一次性烘焙脚本：把三张官方品牌 PNG 的 alpha 通道转成可内嵌的遮罩数据。

用法（在含 logo 的目录下运行）：
    python tools/bake_brand.py <logo目录>

产物：app/brand_masks.py
原理：官方素材是白色硬边位图，直接贴到浅色卡面上等于隐形。这里只取它的
alpha（覆盖度）当「模子」，运行时用品牌色去填 —— 既保留官方真实轮廓，
又能随主题换色，且不需要往单文件 exe 里塞图片资源。
"""
import base64
import io
import os
import sys

from PySide6.QtCore import QBuffer, QByteArray, Qt
from PySide6.QtGui import QImage

# 采样边长：显示尺寸最大 34px 徽标 @dpr2 = 68 设备像素，128 留足余量
N = 128
ALPHA_THRESH = 24          # 判定「图形在此」的低阈值，兼顾抗锯齿边缘

SRC = [("github", "github-1.png"), ("weibo", "weibo-1.png"),
       ("bilibili", "bilibili-1.png")]


def alpha_bbox(im: QImage):
    """求 alpha >阈值的包围盒，用来裁掉原图四周的透明留白。

    不裁的话，图形只占 60~80%，缩到 19px 后有效图形只剩 12px 左右，发虚。
    """
    w, h = im.width(), im.height()
    step = 2                # 隔点采样即可，bbox 精度 2px 对 128px 底图足够
    x0, y0, x1, y1 = w, h, -1, -1
    for y in range(0, h, step):
        for x in range(0, w, step):
            if (im.pixel(x, y) >> 24) > ALPHA_THRESH:
                if x < x0:
                    x0 = x
                if x > x1:
                    x1 = x
                if y < y0:
                    y0 = y
                if y > y1:
                    y1 = y
    if x1 < 0:                             # 整张全透明，别把代码写崩
        return 0, 0, w, h
    return x0, y0, x1 + 1, y1 + 1


def bake(path: str, key: str):
    im = QImage(path)
    if im.isNull():
        raise SystemExit(f"读不出图片：{path}")
    im = im.convertToFormat(QImage.Format_ARGB32)
    # ★ 必须先转灰度再取 bbox：RGB 恒为 255，直接看灰度会得到「整张不透明」
    box = alpha_bbox(im)
    cropped = im.copy(*box)
    #★★ 取灰度的方式必须是「**alpha 填进灰度图**」，而不是 convertToFormat(Grayscale8)。
    #   官方素材 RGB 恒为 255（白色剪影），Grayscale8 取的是 **RGB 亮度** ⇒ 全 255
    #   ⇒ 遮罩全白 ⇒ 渲染出来是一个实心方块（第一版就踩了这个坑）。
    #   ⚠️ 这里用 scanLine 逐字节写，**不要用 setPixel**：8 位单通道图的 pixel()
    #   在 PySide6 里返回错乱的 32 位值（实测 4278190080），setPixel 写进去也乱。
    #   scanLine 返回二维 memoryview，索引是 [y, x]（8 位图每像素 1 字节）。
    w, h = cropped.width(), cropped.height()
    a = QImage(w, h, QImage.Format_Grayscale8)
    a.fill(0)
    src = cropped.convertToFormat(QImage.Format_ARGB32)
    for y in range(h):
        srow = src.constScanLine(y)
        drow = a.scanLine(y)
        for x in range(w):
            drow[x] = srow[4 * x + 3]      # ARGB32 每像素4 字节，偏移 3 = alpha
    a = a.scaled(N, N, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    a.save(buf, "PNG")
    buf.close()
    raw = bytes(ba)
    b64 = base64.b64encode(raw).decode()

    # 自检：遮罩必须真的既有全黑（透明）又有全白（不透明），否则说明 alpha 没取到。
    #⚠️ 读灰度值只能用 scanLine，**不能用 pixel()** —— 8 位单通道图在 PySide6 里
    #   pixel() 返回的是错乱的 32 位值（实测 4278190080）。
    lo, hi = 255, 0
    for y in range(a.height()):
        row = a.constScanLine(y)
        for x in range(a.width()):
            v = row[x]
            if v < lo:
                lo = v
            if v > hi:
                hi = v
    if lo > 40 or hi < 215:
        raise SystemExit(
            f"{key}:遮罩灰度范围异常 min={lo} max={hi} —— "
            f"这通常说明 alpha 通道没被正确取出（会渲染成实心方块）")

    bw = (box[2] - box[0]) / im.width()
    bh = (box[3] - box[1]) / im.height()
    print(f"{key:10s} 原图 {im.width()}x{im.height()}  裁剪后 {box[2]-box[0]}x{box[3]-box[1]}"
          f"  占原图 {bw:.0%}x{bh:.0%}  遮罩灰度 {lo}~{hi}  PNG {len(raw)}B  base64 {len(b64)}")
    return b64, bw, bh


def main() -> None:
    src_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    out = {}
    boxes = {}
    for key, fn in SRC:
        p = os.path.join(src_dir, fn)
        if not os.path.exists(p):
            raise SystemExit(f"缺少素材：{p}")
        b64, bw, bh = bake(p, key)
        out[key] = b64
        boxes[key] = (bw, bh)

    lines = [
        '"""官方品牌标识遮罩 —— 由 tools/bake_brand.py 从原始 PNG 烘焙，**不要手改**。',
        "",
        "只存三张官方素材的 alpha 通道（灰度 PNG），运行时由 icons.brand_mask()",
        "用品牌色填充 —— 官方素材是白色硬边位图，直接贴浅色卡面会隐形，而本项目",
        "又要求不往单文件 exe 里塞图片资源。遮罩法两者都满足：轮廓是官方的，",
        "颜色可换，且整份数据只有几 KB。",
        "",
        f"图形在原图里的占比（已裁掉透明留白）见 BRAND_BOX —— 绘制时要按它等比缩放，",
        "否则非正方形的标识（如 GitHub 竖高、微博横宽）会被拉变形。",
        '"""',
        "",
        "# key -> base64(灰度 PNG，灰度值 = 覆盖度)",
        "BRAND_MASKS = {",
    ]
    for k in ("github", "weibo", "bilibili"):
        lines.append(f'    "{k}": (')
        b = out[k]
        for i in range(0, len(b), 72):
            lines.append(f'        "{b[i:i+72]}"')
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    lines.append("# key -> (宽占比, 高占比)，相对裁剪前的原图尺寸")
    lines.append("BRAND_BOX = {")
    for k in ("github", "weibo", "bilibili"):
        bw, bh = boxes[k]
        lines.append(f'    "{k}": ({bw:.4f}, {bh:.4f}),')
    lines.append("}")
    lines.append("")

    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "brand_masks.py")
    with io.open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    print("已写出：", dst)


if __name__ == "__main__":
    main()