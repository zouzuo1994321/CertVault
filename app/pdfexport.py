# -*- coding: utf-8 -*-
"""PDF / CSV 导出：证书信息单、全库台账、数据表。

使用 Qt 自带的 QPdfWriter 现场绘制，避免引入 reportlab 等第三方依赖，
既能把 exe 压到最小，也能复用同一套中文字体。
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QPageLayout, QPageSize, QPainter,
                           QPen, QPdfWriter)

from . import theme, version

DPI = 300
MM = DPI / 25.4


def _font(size_pt: float, bold: bool = False) -> QFont:
    f = QFont("Microsoft YaHei UI")
    f.setPointSizeF(size_pt)
    f.setBold(bold)
    return f


class _Sheet:
    """一页 A4 的绘制上下文，自动处理分页。"""

    def __init__(self, path: Path, title: str) -> None:
        self.path = Path(path)
        self.writer = QPdfWriter(str(self.path))
        self.writer.setPageSize(QPageSize(QPageSize.A4))
        self.writer.setResolution(DPI)
        self.writer.setPageMargins(QMarginsF(14, 14, 14, 14),
                                   QPageLayout.Unit.Millimeter)
        self.w = self.writer.width()
        self.h = self.writer.height()
        self.p = QPainter(self.writer)
        self.p.setRenderHint(QPainter.Antialiasing, True)
        self.p.setRenderHint(QPainter.TextAntialiasing, True)
        self.y = 0.0
        self.title = title
        self.page_no = 0
        self._new_page()

    # ------------------------------------------------------------ 页面框架
    def _new_page(self) -> None:
        if self.page_no:
            self.writer.newPage()
        self.page_no += 1
        self.y = 0.0
        self._draw_header()

    def _draw_header(self) -> None:
        p = self.p
        band = 22 * MM
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#1b2a3a"))
        p.drawRect(QRectF(0, 0, self.w, band))
        p.setBrush(QColor(theme.GOLD))
        p.drawRect(QRectF(0, band - 1.6 * MM, self.w, 1.6 * MM))

        p.setPen(QColor("#ffffff"))
        p.setFont(_font(15, True))
        p.drawText(QRectF(10 * MM, 0, self.w - 20 * MM, band),
                   Qt.AlignLeft | Qt.AlignVCenter, self.title)

        p.setFont(_font(9))
        p.setPen(QColor("#a8b8c8"))
        p.drawText(QRectF(10 * MM, 0, self.w - 20 * MM, band),
                   Qt.AlignRight | Qt.AlignVCenter,
                   f"{version.APP_NAME}  {version.FULL_VERSION}")
        self.y = band + 8 * MM

    def need(self, height: float) -> None:
        if self.y + height > self.h - 14 * MM:
            self._new_page()

    def footer(self) -> None:
        p = self.p
        p.setFont(_font(8))
        p.setPen(QColor(theme.MUTED))
        p.drawLine(QPointF(10 * MM, self.h - 12 * MM),
                   QPointF(self.w - 10 * MM, self.h - 12 * MM))
        p.drawText(QRectF(10 * MM, self.h - 11 * MM, self.w - 20 * MM, 10 * MM),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   f"{version.COPYRIGHT} · {version.LICENSE_LINE}")
        p.drawText(QRectF(10 * MM, self.h - 11 * MM, self.w - 20 * MM, 10 * MM),
                   Qt.AlignRight | Qt.AlignVCenter, f"第 {self.page_no} 页")

    def end(self) -> None:
        self.footer()
        self.p.end()

    # ---------------------------------------------------------------- 元素
    def section(self, text: str) -> None:
        self.need(12 * MM)
        p = self.p
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.PRIMARY))
        p.drawRect(QRectF(10 * MM, self.y + 1.2 * MM, 1.4 * MM, 4.6 * MM))
        p.setPen(QColor(theme.TEXT))
        p.setFont(_font(11.5, True))
        p.drawText(QRectF(13.5 * MM, self.y, self.w - 24 * MM, 7 * MM),
                   Qt.AlignLeft | Qt.AlignVCenter, text)
        self.y += 10 * MM

    def kv_block(self, items: Sequence[tuple], cols: int = 2) -> None:
        """键值对区块，按 cols 列排布。"""
        p = self.p
        fm_h = 8.6 * MM
        usable = self.w - 24 * MM
        col_w = usable / cols
        rows = (len(items) + cols - 1) // cols
        self.need(rows * fm_h + 2 * MM)
        for idx, (k, v) in enumerate(items):
            r, c = divmod(idx, cols)
            x = 12 * MM + c * col_w
            y = self.y + r * fm_h
            p.setPen(QColor(theme.MUTED))
            p.setFont(_font(9))
            p.drawText(QRectF(x, y, col_w - 4 * MM, fm_h),
                       Qt.AlignLeft | Qt.AlignVCenter, str(k))
            p.setPen(QColor(theme.TEXT))
            p.setFont(_font(10))
            p.drawText(QRectF(x + 26 * MM, y, col_w - 30 * MM, fm_h),
                       Qt.AlignLeft | Qt.AlignVCenter,
                       _elide(p, str(v) if v else "—", col_w - 30 * MM))
        self.y += rows * fm_h + 2 * MM

    def para(self, text: str, size: float = 9.5, color: str = theme.TEXT_SUB) -> None:
        p = self.p
        p.setFont(_font(size))
        p.setPen(QColor(color))
        rect = QRectF(12 * MM, self.y, self.w - 24 * MM, self.h)
        r = p.boundingRect(rect, Qt.TextWordWrap, text)
        self.need(r.height() + 3 * MM)
        rect = QRectF(12 * MM, self.y, self.w - 24 * MM, r.height() + 2 * MM)
        p.drawText(rect, Qt.TextWordWrap, text)
        self.y += r.height() + 3 * MM

    def highlight(self, label: str, value: str, sub: str = "") -> None:
        self.need(20 * MM)
        p = self.p
        box = QRectF(12 * MM, self.y, self.w - 24 * MM, 17 * MM)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor("#f7f9fc"))
        p.drawRoundedRect(box, 2.4 * MM, 2.4 * MM)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.GOLD))
        p.drawRoundedRect(QRectF(box.left(), box.top(), 1.8 * MM, box.height()), 0.9 * MM, 0.9 * MM)
        p.setPen(QColor(theme.MUTED))
        p.setFont(_font(9))
        p.drawText(QRectF(box.left() + 6 * MM, box.top() + 1 * MM, box.width() - 10 * MM, 6 * MM),
                   Qt.AlignLeft | Qt.AlignVCenter, label)
        p.setPen(QColor(theme.TEXT))
        p.setFont(_font(13, True))
        p.drawText(QRectF(box.left() + 6 * MM, box.top() + 6 * MM, box.width() - 10 * MM, 8 * MM),
                   Qt.AlignLeft | Qt.AlignVCenter, value)
        if sub:
            p.setFont(_font(9))
            p.setPen(QColor(theme.MUTED))
            p.drawText(QRectF(box.left() + 6 * MM, box.top() + 6 * MM, box.width() - 8 * MM, 8 * MM),
                       Qt.AlignRight | Qt.AlignVCenter, sub)
        self.y += 20 * MM

    def table(self, headers: Sequence[str], widths: Sequence[float],
              rows: Sequence[Sequence[str]], row_h: float = 7.6 * MM) -> None:
        p = self.p
        total = sum(widths)
        avail = self.w - 24 * MM
        wcols = [avail * (x / total) for x in widths]
        self.need(row_h * 2)
        # 表头
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#eef2f7"))
        p.drawRect(QRectF(12 * MM, self.y, avail, row_h))
        p.setFont(_font(9, True))
        p.setPen(QColor(theme.TEXT_SUB))
        x = 12 * MM
        for hdr, cw in zip(headers, wcols):
            p.drawText(QRectF(x + 2 * MM, self.y, cw - 4 * MM, row_h),
                       Qt.AlignLeft | Qt.AlignVCenter, hdr)
            x += cw
        self.y += row_h

        p.setFont(_font(9))
        for i, row in enumerate(rows):
            if self.y + row_h > self.h - 16 * MM:
                self._new_page()
                p = self.p
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#eef2f7"))
                p.drawRect(QRectF(12 * MM, self.y, avail, row_h))
                p.setFont(_font(9, True))
                p.setPen(QColor(theme.TEXT_SUB))
                x = 12 * MM
                for hdr, cw in zip(headers, wcols):
                    p.drawText(QRectF(x + 2 * MM, self.y, cw - 4 * MM, row_h),
                               Qt.AlignLeft | Qt.AlignVCenter, hdr)
                    x += cw
                self.y += row_h
                p.setFont(_font(9))
            if i % 2 == 0:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#fafcfe"))
                p.drawRect(QRectF(12 * MM, self.y, avail, row_h))
            p.setPen(QColor(theme.TEXT))
            x = 12 * MM
            for val, cw in zip(row, wcols):
                p.drawText(QRectF(x + 2 * MM, self.y, cw - 4 * MM, row_h),
                           Qt.AlignLeft | Qt.AlignVCenter,
                           _elide(p, str(val), cw - 4 * MM))
                x += cw
            p.setPen(QColor(theme.BORDER))
            p.drawLine(QPointF(12 * MM, self.y + row_h),
                       QPointF(12 * MM + avail, self.y + row_h))
            self.y += row_h
        self.y += 4 * MM


def _elide(p: QPainter, text: str, width_px: float) -> str:
    fm = p.fontMetrics()
    if fm.horizontalAdvance(text) <= width_px:
        return text
    out = text
    while out and fm.horizontalAdvance(out + "…") > width_px:
        out = out[:-1]
    return out + "…"


# --------------------------------------------------------------- 对外接口


def export_certificate(cert: Dict[str, Any], attachments: Sequence[Dict[str, Any]],
                       out_path: Path) -> Path:
    """导出单张证书信息单（含有效期结论与附件清单）。"""
    s = _Sheet(out_path, "证书信息单 / Certificate Record")
    s.highlight(cert.get("name", ""), cert.get("name", ""),
                f"{cert.get('status_label','')} · {cert.get('left_text','')}")
    s.kv_block([
        ("证书分类", cert.get("category", "")),
        ("证书编号", cert.get("number", "")),
        ("持证人", cert.get("holder", "")),
        ("级别 / 等级", cert.get("level", "")),
        ("发证机构", cert.get("issuer", "")),
        ("当前状态", "在用" if cert.get("active", 1) else "已停用"),
        ("发证日期", cert.get("issue_date", "")),
        ("到期日期", cert.get("expiry_date", "") or "长期有效"),
        ("剩余有效期", cert.get("left_text", "")),
        ("归档时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ])
    if cert.get("remark"):
        s.section("备注")
        s.para(cert["remark"])
    s.section("附件清单")
    if attachments:
        s.table(["序号", "文件名称", "类型", "大小"],
                [0.8, 5, 1.2, 1.4],
                [[str(i + 1), a.get("title", ""), a.get("kind", "").upper(),
                  _size_text(a.get("size", 0))]
                 for i, a in enumerate(attachments)])
    else:
        s.para("暂无附件。")
    s.section("说明")
    s.para(f"本单由《{version.APP_NAME}》{version.FULL_VERSION} 于 "
           f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 自动生成，"
           "有效期数据来源于用户自行录入，仅供参考，最终请以发证机构口径为准。")
    s.end()
    return Path(out_path)


def export_ledger(rows: Sequence[Dict[str, Any]], out_path: Path,
                  scope: str = "全部证书") -> Path:
    """导出全库台账 PDF。"""
    s = _Sheet(out_path, f"证书台账 / {scope}")
    stats: Dict[str, int] = {}
    for r in rows:
        stats[r.get("status_label", "")] = stats.get(r.get("status_label", ""), 0) + 1
    s.highlight("台账概览", f"共 {len(rows)} 本证书",
                "  ·  ".join(f"{k} {v}" for k, v in stats.items()) or "—")
    data = []
    for i, r in enumerate(rows):
        data.append([
            str(i + 1), r.get("name", ""), r.get("category", ""),
            r.get("number", ""), r.get("issuer", ""),
            r.get("issue_date", "") or "—", r.get("expiry_date", "") or "长期",
            r.get("left_text", "—"), r.get("status_label", ""),
        ])
    s.table(["#", "证书名称", "分类", "编号", "发证机构", "发证日期", "到期日期", "剩余", "状态"],
            [0.4, 2.4, 1.0, 1.5, 1.8, 1.1, 1.1, 1.1, 0.9], data)
    s.end()
    return Path(out_path)


def export_csv(rows: Sequence[Dict[str, Any]], out_path: Path) -> Path:
    with open(out_path, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["序号", "证书名称", "分类", "证书编号", "持证人", "发证机构",
                    "级别", "发证日期", "到期日期", "剩余有效期", "状态", "在用", "备注"])
        for i, r in enumerate(rows):
            w.writerow([i + 1, r.get("name", ""), r.get("category", ""),
                        r.get("number", ""), r.get("holder", ""), r.get("issuer", ""),
                        r.get("level", ""), r.get("issue_date", ""),
                        r.get("expiry_date", ""), r.get("left_text", ""),
                        r.get("status_label", ""),
                        "是" if r.get("active", 1) else "否", r.get("remark", "")])
    return Path(out_path)


def export_exam_plan(rows: Sequence[Dict[str, Any]], out_path: Path) -> Path:
    s = _Sheet(out_path, "考试计划表 / Exam Plan")
    s.highlight("计划概览", f"共 {len(rows)} 项考试", "")
    s.table(["#", "考试名称", "关联证书", "考试日期", "报名截止", "考点", "费用", "状态"],
            [0.4, 2.4, 1.3, 1.1, 1.1, 1.6, 0.9, 0.9],
            [[str(i + 1), r.get("name", ""), r.get("category", ""),
              r.get("exam_date", "") or "—", r.get("reg_deadline", "") or "—",
              r.get("location", ""), r.get("fee", ""), r.get("state", "")]
             for i, r in enumerate(rows)])
    s.end()
    return Path(out_path)


def _size_text(size: int) -> str:
    if not size:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"
