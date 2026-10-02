# -*- coding: utf-8 -*-
"""对话框层：证书编辑 / PDF 预览 / 到期提醒 / 考试计划 / 学习资料 / 分类 / 设置。"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog,
                               QDialog, QDialogButtonBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSizePolicy, QSplitter, QStackedWidget,
                               QTabWidget, QVBoxLayout, QWidget)

from . import db as dbm
from . import icons, paths, pdfexport, procutil, theme, version
from .floatwin import BLOCKS as FLOAT_BLOCKS
from .floatwin import DEFAULT_BLOCKS as FLOAT_DEFAULT_BLOCKS
from .widgets import (Badge, Card, ComboBox, DateEdit, IconButton, SearchBox,
                      SectionTitle, SpinBox, hline, mono_label, realize,
                      status_badge)

try:  # QtPdf 在极少数精简构建中可能缺失，缺失时优雅降级
    from PySide6.QtPdf import QPdfDocument
    from PySide6.QtPdfWidgets import QPdfView
    HAS_PDF = True
except Exception:  # noqa: BLE001
    QPdfDocument = None  # type: ignore
    QPdfView = None  # type: ignore
    HAS_PDF = False


# ------------------------------------------------------------------ 小工具


def info(parent, text: str, title: str = "提示") -> None:
    QMessageBox.information(parent, title, text)


def warn(parent, text: str, title: str = "注意") -> None:
    QMessageBox.warning(parent, title, text)


def error(parent, text: str, title: str = "出错了") -> None:
    QMessageBox.critical(parent, title, text)


def confirm(parent, text: str, title: str = "请确认") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(QMessageBox.Question)
    yes = box.addButton("确认", QMessageBox.AcceptRole)
    box.addButton("取消", QMessageBox.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def open_path(path: Path | str) -> bool:
    """用系统默认程序打开文件或目录。"""
    p = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(p)  # type: ignore[attr-defined]
        else:
            procutil.popen_silent(["xdg-open", p])
        return True
    except Exception:  # noqa: BLE001
        return False


def open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))


def reveal(path: Path | str) -> None:
    if sys.platform.startswith("win"):
        # ⚠️ 走静默调用：explorer 是 GUI 程序不弹控制台，但 Popen 默认会在
        # 无控制台宿主里闪一下；统一用 procutil 保持行为一致。
        procutil.popen_silent(["explorer", "/select,", str(path)])
    else:
        open_path(Path(path).parent)


def _labeled(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("Muted")
    return lbl


def _row(label: str, w: QWidget, stretch: int = 1) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(10)
    lbl = QLabel(label)
    lbl.setFixedWidth(72)
    lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lbl.setStyleSheet(f"color:{theme.TEXT_SUB};")
    lay.addWidget(lbl)
    lay.addWidget(w, stretch)
    return lay


def dlg_qss() -> str:
    return theme.QSS


# ============================================================== PDF 预览器


class PdfViewer(QDialog):
    """内置 PDF 预览：翻页、缩放、适应宽度、导出副本、外部打开。"""

    def __init__(self, pdf_path: Path, title: str = "PDF 预览",
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"{title} — {Path(pdf_path).name}")
        self.setStyleSheet(dlg_qss())
        self.resize(1020, 760)
        self.pdf_path = Path(pdf_path)
        self._zoom = 1.0
        self.doc = None

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.btn_prev = IconButton("chevron-left", "上一页")
        self.btn_next = IconButton("chevron-right", "下一页")
        self.btn_out = IconButton("zoom-out", "缩小")
        self.btn_in = IconButton("zoom-in", "放大")
        self.btn_fit = IconButton("fit", "适应宽度")
        self.lbl_page = mono_label("— / —", theme.TEXT_SUB, 12)
        self.lbl_name = QLabel(self.pdf_path.name)
        self.lbl_name.setStyleSheet(f"color:{theme.TEXT}; font-weight:600;")
        self.lbl_meta = mono_label(_size_text(self.pdf_path.stat().st_size
                                              if self.pdf_path.exists() else 0))

        bar.addWidget(self.btn_prev)
        bar.addWidget(self.btn_next)
        bar.addWidget(self.lbl_page)
        bar.addSpacing(14)
        bar.addWidget(self.btn_out)
        bar.addWidget(self.btn_in)
        bar.addWidget(self.btn_fit)
        bar.addStretch(1)
        bar.addWidget(self.lbl_name)
        bar.addSpacing(8)
        bar.addWidget(self.lbl_meta)
        root.addLayout(bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        if HAS_PDF and self.pdf_path.exists():
            self.doc = QPdfDocument(self)
            err = self.doc.load(str(self.pdf_path))
            self.view = QPdfView()
            self.view.setDocument(self.doc)
            self.view.setPageMode(self._page_mode(QPdfView))
            self.view.setZoomMode(self._zoom_mode(QPdfView).FitToWidth)
            self.stack.addWidget(self.view)
            if not _pdf_ok(err, self.doc):
                self._fallback("无法解析该 PDF 文件（可能已加密或损坏）。")
            else:
                self.lbl_page.setText(f"1 / {self.doc.pageCount()}")
                self.btn_prev.clicked.connect(lambda: self._step(-1))
                self.btn_next.clicked.connect(lambda: self._step(1))
                self.btn_in.clicked.connect(lambda: self._zoom_by(1.2))
                self.btn_out.clicked.connect(lambda: self._zoom_by(1 / 1.2))
                self.btn_fit.clicked.connect(
                    lambda: self.view.setZoomMode(self._zoom_mode(QPdfView).FitToWidth))
                self.view.pageNavigator().currentPageChanged.connect(self._on_page)
        else:
            self._fallback("当前环境缺少 PDF 渲染组件，可使用系统程序打开。")

        foot = QHBoxLayout()
        self.btn_open = QPushButton("用系统程序打开")
        realize(self.btn_open, "open", theme.TEXT_SUB)
        self.btn_save = QPushButton("导出副本")
        realize(self.btn_save, "export", theme.TEXT_SUB)
        self.btn_close = QPushButton("关闭")
        close_btn = self.btn_close
        self.btn_open.clicked.connect(lambda: open_path(self.pdf_path))
        self.btn_save.clicked.connect(self._save_copy)
        close_btn.clicked.connect(self.accept)
        foot.addWidget(self.btn_open)
        foot.addWidget(self.btn_save)
        foot.addStretch(1)
        foot.addWidget(close_btn)
        root.addLayout(foot)

    # --- QtPdf 枚举在不同绑定版本下路径略有差异，做一次兜底解析
    @staticmethod
    def _page_mode(cls):
        pm = getattr(cls, "PageMode", None)
        if pm is None:
            return None
        return getattr(pm, "MultiPage", None)

    @staticmethod
    def _zoom_mode(cls):
        class _Z:  # 兜底
            Custom = 0
            FitToWidth = 1
            FitInView = 2
        return getattr(cls, "ZoomMode", _Z)

    def _fallback(self, msg: str) -> None:
        from .widgets import EmptyState
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.addStretch(1)
        es = EmptyState("PDF 预览不可用", msg, "pdf", "用系统程序打开")
        es.action_clicked.connect(lambda: open_path(self.pdf_path))
        lay.addWidget(es)
        lay.addStretch(1)
        self.stack.addWidget(holder)
        self.stack.setCurrentWidget(holder)

    def _step(self, delta: int) -> None:
        nav = self.view.pageNavigator()
        page = nav.currentPage() + delta
        page = max(0, min(page, self.doc.pageCount() - 1))
        nav.jumpToPage(page)

    def _zoom_by(self, factor: float) -> None:
        self._zoom = max(0.25, min(6.0, self.view.zoomFactor() * factor))
        self.view.setZoomMode(self._zoom_mode(QPdfView).Custom)
        self.view.setZoomFactor(self._zoom)

    def _on_page(self, page: int) -> None:
        self.lbl_page.setText(f"{page + 1} / {self.doc.pageCount()}")

    def _save_copy(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "导出 PDF 副本", str(Path.home() / self.pdf_path.name), "PDF 文件 (*.pdf)")
        if not target:
            return
        try:
            import shutil
            shutil.copy2(self.pdf_path, target)
            info(self, f"已导出到：\n{target}")
        except Exception as exc:  # noqa: BLE001
            error(self, f"导出失败：{exc}")


def _size_text(size: int) -> str:
    if not size:
        return "—"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def _pdf_ok(err, doc) -> bool:
    """QPdfDocument.load() 的返回枚举在不同绑定版本下比较方式不同，做统一兜底。"""
    try:
        if doc.pageCount() <= 0:
            return False
    except Exception:  # noqa: BLE001
        return False
    try:
        none_enum = QPdfDocument.Error.None_
        return err == none_enum
    except Exception:  # noqa: BLE001
        return str(err).endswith("None_") or "0" in str(err)


# ============================================================ 证书编辑对话框


class CertDialog(QDialog):
    """证书新增 / 编辑：信息表单 + 附件管理 + 内联 PDF 预览。"""

    def __init__(self, database: dbm.Database, cert_id: Optional[int] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.cert_id = cert_id
        self.pending: List[str] = []       # 新增态待落库的附件源文件
        self.removed: List[int] = []       # 编辑态待删除的附件 id
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("编辑证书" if cert_id else "新增证书")
        self.resize(980, 700)

        data = self.db.get_certificate(cert_id) if cert_id else None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        head = QHBoxLayout()
        t = QLabel("编辑证书信息" if cert_id else "录入新证书")
        t.setStyleSheet(f"font-size:17px; font-weight:700; color:{theme.TEXT};")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(mono_label(version.FULL_VERSION))
        root.addLayout(head)

        split = QSplitter(Qt.Horizontal)
        root.addWidget(split, 1)

        # ---------------- 左：表单
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(10)

        card = Card("基本信息")
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("必填，例如：注册会计师（CPA）")
        self.cb_cat = ComboBox()
        self.cb_cat.setEditable(True)
        self.cb_cat.addItems(self.db.category_names())
        self.ed_number = QLineEdit()
        self.ed_number.setPlaceholderText("证书编号 / 管理号")
        self.ed_holder = QLineEdit()
        self.ed_holder.setPlaceholderText("证书持有人姓名")
        self.ed_issuer = QLineEdit()
        self.ed_issuer.setPlaceholderText("发证机构 / 颁发单位")
        self.ed_level = QLineEdit()
        self.ed_level.setPlaceholderText("如：初级 / 中级 / 高级 / A 类")

        card.add(_row("名称 *", self.ed_name))
        card.add(_row("分类", self.cb_cat))
        card.add(_row("编号", self.ed_number))
        card.add(_row("持证人", self.ed_holder))
        card.add(_row("发证机构", self.ed_issuer))
        card.add(_row("级别", self.ed_level))
        lv.addWidget(card)

        card2 = Card("有效期")
        self.cb_longterm = QCheckBox("长期有效（无到期日）")
        self.de_issue = DateEdit(QDate.currentDate())
        self.de_issue.setDisplayFormat("yyyy-MM-dd")
        self.de_expiry = DateEdit(QDate.currentDate().addYears(3))
        self.de_expiry.setDisplayFormat("yyyy-MM-dd")
        self.cb_active = QCheckBox("证书在用（取消勾选表示已注销 / 停用）")
        self.cb_active.setChecked(True)
        self.lbl_left = QLabel("—")
        self.lbl_left.setStyleSheet(f"color:{theme.PRIMARY}; font-weight:600;")

        card2.add(_row("发证日期", self.de_issue))
        card2.add(self.cb_longterm)
        card2.add(_row("到期日期", self.de_expiry))
        card2.add(_row("剩余", self.lbl_left, 0))
        card2.add(self.cb_active)
        lv.addWidget(card2)

        card3 = Card("备注")
        self.pt_remark = QPlainTextEdit()
        self.pt_remark.setPlaceholderText("证书记录、继续教育要求、年审提示等…")
        self.pt_remark.setFixedHeight(90)
        card3.add(self.pt_remark)
        lv.addWidget(card3)
        lv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(left)
        split.addWidget(scroll)

        # ---------------- 右：附件
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(10)

        acard = Card("证书附件（PDF / 图片 / 扫描件）")
        btn_add = QPushButton("添加附件")
        btn_add.setObjectName("Primary")
        realize(btn_add, "plus", "#ffffff")
        btn_add.clicked.connect(self._add_files)
        acard.add_head_widget(btn_add)

        self.lst_attach = QListWidget()
        self.lst_attach.setMinimumHeight(180)
        self.lst_attach.itemDoubleClicked.connect(lambda _: self._preview())
        acard.add(self.lst_attach)

        arow = QHBoxLayout()
        self.btn_preview = QPushButton("预览 PDF")
        realize(self.btn_preview, "pdf", theme.PRIMARY)
        self.btn_open = QPushButton("外部打开")
        realize(self.btn_open, "open", theme.TEXT_SUB)
        self.btn_del = QPushButton("移除")
        self.btn_del.setObjectName("Danger")
        realize(self.btn_del, "trash", theme.DANGER)
        self.btn_preview.clicked.connect(self._preview)
        self.btn_open.clicked.connect(self._open_attach)
        self.btn_del.clicked.connect(self._remove_attach)
        arow.addWidget(self.btn_preview)
        arow.addWidget(self.btn_open)
        arow.addWidget(self.btn_del)
        arow.addStretch(1)
        acard.add(arow)
        rv.addWidget(acard)

        tip = QLabel("提示：附件会被复制到 data/files/ 目录随库保存，"
                     "双击条目可直接预览。")
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        rv.addWidget(tip)
        rv.addStretch(1)
        split.addWidget(right)
        split.setSizes([560, 380])

        # ---------------- 底部按钮
        foot = QHBoxLayout()
        self.lbl_hint = QLabel("带 * 的为必填项")
        self.lbl_hint.setObjectName("Muted")
        foot.addWidget(self.lbl_hint)
        foot.addStretch(1)
        btn_cancel = QPushButton("取消")
        btn_cancel.clicked.connect(self.reject)
        btn_save = QPushButton("保存证书")
        btn_save.setObjectName("Primary")
        realize(btn_save, "check", "#ffffff")
        btn_save.clicked.connect(self._save)
        foot.addWidget(btn_cancel)
        foot.addWidget(btn_save)
        root.addLayout(foot)

        # ---------------- 回填
        if data:
            self.ed_name.setText(data.get("name", ""))
            self.cb_cat.setCurrentText(data.get("category", "其他"))
            self.ed_number.setText(data.get("number", ""))
            self.ed_holder.setText(data.get("holder", ""))
            self.ed_issuer.setText(data.get("issuer", ""))
            self.ed_level.setText(data.get("level", ""))
            self.pt_remark.setPlainText(data.get("remark", ""))
            self.cb_active.setChecked(bool(data.get("active", 1)))
            d = dbm.parse_date(data.get("issue_date", ""))
            if d:
                self.de_issue.setDate(QDate(d.year, d.month, d.day))
            e = dbm.parse_date(data.get("expiry_date", ""))
            if e:
                self.de_expiry.setDate(QDate(e.year, e.month, e.day))
            else:
                self.cb_longterm.setChecked(True)
        self._reload_attach()

        self.cb_longterm.toggled.connect(self._on_longterm)
        self.de_expiry.dateChanged.connect(lambda _: self._refresh_left())
        self.cb_longterm.toggled.connect(lambda _: self._refresh_left())
        self._on_longterm(self.cb_longterm.isChecked())

    # -------------------------------------------------------------- 事件
    def _on_longterm(self, on: bool) -> None:
        self.de_expiry.setEnabled(not on)
        self._refresh_left()

    def _refresh_left(self) -> None:
        if self.cb_longterm.isChecked():
            self.lbl_left.setText("长期有效")
            self.lbl_left.setStyleSheet(f"color:{theme.PRIMARY}; font-weight:600;")
            return
        key, label, left = dbm.cert_validity(
            self.de_expiry.date().toString("yyyy-MM-dd"),
            self.db.warn_days(), self.db.urgent_days())
        self.lbl_left.setText(f"{label} · {dbm.left_text(left)}")
        self.lbl_left.setStyleSheet(
            f"color:{theme.status_color(key)}; font-weight:600;")

    def _reload_attach(self) -> None:
        self.lst_attach.clear()
        rows = self.db.attachments(self.cert_id) if self.cert_id else []
        rows = [r for r in rows if r["id"] not in self.removed]
        for r in rows:
            item = QListWidgetItem(f"{r['title']}    ·    {_size_text(r['size'])}")
            item.setData(Qt.UserRole, ("db", r["id"], r["path"], r["title"]))
            item.setIcon(icons.icon("pdf" if r["kind"] == "pdf" else "doc",
                                    theme.DANGER if r["kind"] == "pdf" else theme.TEXT_SUB, 16))
            self.lst_attach.addItem(item)
        for src in self.pending:
            p = Path(src)
            item = QListWidgetItem(f"{p.name}    ·    待保存")
            item.setData(Qt.UserRole, ("new", None, src, p.name))
            item.setIcon(icons.icon("pdf" if p.suffix.lower() == ".pdf" else "doc",
                                    theme.MUTED, 16))
            self.lst_attach.addItem(item)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择证书附件", str(Path.home()),
            "证书文件 (*.pdf *.jpg *.jpeg *.png *.bmp *.webp);;PDF 文件 (*.pdf);;所有文件 (*.*)")
        if not files:
            return
        for f in files:
            self.pending.append(f)
        self._reload_attach()

    def _current(self):
        item = self.lst_attach.currentItem()
        if not item:
            return None
        return item.data(Qt.UserRole)

    def _resolve(self, info_tuple) -> Optional[Path]:
        kind, _aid, path, _title = info_tuple
        p = Path(path)
        if not p.is_absolute():
            p = paths.FILES_DIR / path
        return p if p.exists() else None

    def _preview(self) -> None:
        cur = self._current()
        if not cur:
            warn(self, "请先在列表中选择一个附件。")
            return
        p = self._resolve(cur)
        if not p:
            error(self, "附件文件不存在，可能已被移动或删除。")
            return
        if p.suffix.lower() != ".pdf":
            open_path(p)
            return
        PdfViewer(p, "证书 PDF 预览", self).exec()

    def _open_attach(self) -> None:
        cur = self._current()
        if not cur:
            warn(self, "请先在列表中选择一个附件。")
            return
        p = self._resolve(cur)
        if not p or not open_path(p):
            error(self, "无法打开该附件。")

    def _remove_attach(self) -> None:
        cur = self._current()
        if not cur:
            warn(self, "请先在列表中选择一个附件。")
            return
        kind, aid, path, title = cur
        if not confirm(self, f"确定移除附件「{title}」？\n（同时会删除 data/files 中的副本）"):
            return
        if kind == "db":
            self.removed.append(aid)
        else:
            if path in self.pending:
                self.pending.remove(path)
        self._reload_attach()

    def _save(self) -> None:
        name = self.ed_name.text().strip()
        if not name:
            warn(self, "请填写证书名称。")
            self.ed_name.setFocus()
            return
        cat = self.cb_cat.currentText().strip() or "其他"
        if cat not in self.db.category_names():
            self.db.add_category(cat, theme.PRIMARY)
        data = {
            "name": name,
            "category": cat,
            "number": self.ed_number.text().strip(),
            "holder": self.ed_holder.text().strip(),
            "issuer": self.ed_issuer.text().strip(),
            "level": self.ed_level.text().strip(),
            "issue_date": self.de_issue.date().toString("yyyy-MM-dd"),
            "expiry_date": "" if self.cb_longterm.isChecked()
            else self.de_expiry.date().toString("yyyy-MM-dd"),
            "active": 1 if self.cb_active.isChecked() else 0,
            "remark": self.pt_remark.toPlainText().strip(),
        }
        cid = self.db.save_certificate(data, self.cert_id)
        self.cert_id = cid
        for aid in self.removed:
            self.db.remove_attachment(aid)
        self.removed.clear()
        ok, failed = 0, []
        for src in list(self.pending):
            res = self.db.attach_file(cid, src)
            if res:
                ok += 1
            else:
                failed.append(Path(src).name)
        self.pending.clear()
        if failed:
            warn(self, "以下附件复制失败：\n" + "\n".join(failed))
        self.saved_id = cid
        self.accept()


# ================================================================ 考试计划


class ExamDialog(QDialog):
    def __init__(self, database: dbm.Database, exam_id: Optional[int] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.exam_id = exam_id
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("编辑考试计划" if exam_id else "新增考试计划")
        self.resize(620, 520)

        data = None
        if exam_id:
            rows = [r for r in self.db.exams() if r["id"] == exam_id]
            data = rows[0] if rows else None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        t = QLabel("编辑考试计划" if exam_id else "新增考试计划")
        t.setStyleSheet(f"font-size:17px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(t)

        card = Card()
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("例如：2027 年注册会计师专业阶段考试")
        self.cb_cat = ComboBox()
        self.cb_cat.setEditable(True)
        self.cb_cat.addItems([""] + self.db.category_names())
        self.de_date = DateEdit(QDate.currentDate().addMonths(1))
        self.de_date.setDisplayFormat("yyyy-MM-dd")
        self.de_reg = DateEdit(QDate.currentDate())
        self.de_reg.setDisplayFormat("yyyy-MM-dd")
        self.ed_loc = QLineEdit()
        self.ed_loc.setPlaceholderText("考点城市 / 考场")
        self.ed_fee = QLineEdit()
        self.ed_fee.setPlaceholderText("如：¥ 90 / 科")
        self.cb_state = ComboBox()
        self.cb_state.addItems(dbm.EXAM_STATES)
        self.ed_score = QLineEdit()
        self.ed_score.setPlaceholderText("成绩 / 分数（选填）")
        self.pt_remark = QPlainTextEdit()
        self.pt_remark.setFixedHeight(80)

        card.add(_row("考试名称 *", self.ed_name))
        card.add(_row("关联证书", self.cb_cat))
        card.add(_row("考试日期", self.de_date))
        card.add(_row("报名截止", self.de_reg))
        card.add(_row("考点", self.ed_loc))
        card.add(_row("费用", self.ed_fee))
        card.add(_row("状态", self.cb_state))
        card.add(_row("成绩", self.ed_score))
        card.add(_row("备注", self.pt_remark))
        root.addWidget(card, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b1 = QPushButton("取消")
        b1.clicked.connect(self.reject)
        b2 = QPushButton("保存")
        b2.setObjectName("Primary")
        realize(b2, "check", "#ffffff")
        b2.clicked.connect(self._save)
        foot.addWidget(b1)
        foot.addWidget(b2)
        root.addLayout(foot)

        if data:
            self.ed_name.setText(data.get("name", ""))
            self.cb_cat.setCurrentText(data.get("category", ""))
            self.ed_loc.setText(data.get("location", ""))
            self.ed_fee.setText(data.get("fee", ""))
            self.ed_score.setText(data.get("score", ""))
            self.pt_remark.setPlainText(data.get("remark", ""))
            self.cb_state.setCurrentText(data.get("state", "计划中"))
            d = dbm.parse_date(data.get("exam_date", ""))
            if d:
                self.de_date.setDate(QDate(d.year, d.month, d.day))
            rd = dbm.parse_date(data.get("reg_deadline", ""))
            if rd:
                self.de_reg.setDate(QDate(rd.year, rd.month, rd.day))

    def _save(self) -> None:
        if not self.ed_name.text().strip():
            warn(self, "请填写考试名称。")
            return
        self.db.save_exam({
            "name": self.ed_name.text().strip(),
            "category": self.cb_cat.currentText().strip(),
            "exam_date": self.de_date.date().toString("yyyy-MM-dd"),
            "reg_deadline": self.de_reg.date().toString("yyyy-MM-dd"),
            "location": self.ed_loc.text().strip(),
            "fee": self.ed_fee.text().strip(),
            "state": self.cb_state.currentText(),
            "score": self.ed_score.text().strip(),
            "remark": self.pt_remark.toPlainText().strip(),
        }, self.exam_id)
        self.accept()


# ================================================================ 学习资料


class MaterialDialog(QDialog):
    def __init__(self, database: dbm.Database, material_id: Optional[int] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.material_id = material_id
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("编辑学习资料" if material_id else "新增学习资料")
        self.resize(620, 430)

        data = None
        if material_id:
            rows = [r for r in self.db.materials() if r["id"] == material_id]
            data = rows[0] if rows else None

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        t = QLabel("编辑学习资料" if material_id else "新增学习资料")
        t.setStyleSheet(f"font-size:17px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(t)

        card = Card()
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("资料名称，例如：CPA 会计教材（2026 版）")
        self.cb_cat = ComboBox()
        self.cb_cat.addItems(dbm.MATERIAL_CATEGORIES)
        self.cb_kind = ComboBox()
        self.cb_kind.addItems(["网络链接", "本地文件", "本地文件夹"])
        self.ed_target = QLineEdit()
        self.ed_target.setPlaceholderText("粘贴网址，或点击右侧「浏览」选择本地文件")
        btn_browse = QPushButton("浏览…")
        realize(btn_browse, "folder", theme.TEXT_SUB)
        btn_browse.clicked.connect(self._browse)
        trow = QHBoxLayout()
        trow.setSpacing(8)
        trow.addWidget(self.ed_target, 1)
        trow.addWidget(btn_browse)
        target_holder = QWidget()
        target_holder.setLayout(trow)
        self.pt_note = QPlainTextEdit()
        self.pt_note.setFixedHeight(90)
        self.pt_note.setPlaceholderText("学习要点、章节进度、获取渠道等…")

        card.add(_row("资料名称 *", self.ed_title))
        card.add(_row("资料分类", self.cb_cat))
        card.add(_row("资料类型", self.cb_kind))
        card.add(_row("地址", target_holder))
        card.add(_row("备注", self.pt_note))
        root.addWidget(card, 1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b1 = QPushButton("取消")
        b1.clicked.connect(self.reject)
        b2 = QPushButton("保存")
        b2.setObjectName("Primary")
        realize(b2, "check", "#ffffff")
        b2.clicked.connect(self._save)
        foot.addWidget(b1)
        foot.addWidget(b2)
        root.addLayout(foot)

        if data:
            self.ed_title.setText(data.get("title", ""))
            self.cb_cat.setCurrentText(data.get("category", "其他"))
            kind_map = {"link": "网络链接", "file": "本地文件", "dir": "本地文件夹"}
            self.cb_kind.setCurrentText(kind_map.get(data.get("kind", "link"), "网络链接"))
            self.ed_target.setText(data.get("target", ""))
            self.pt_note.setPlainText(data.get("note", ""))

    def _browse(self) -> None:
        if self.cb_kind.currentText() == "本地文件夹":
            p = QFileDialog.getExistingDirectory(self, "选择文件夹", str(Path.home()))
        else:
            p, _ = QFileDialog.getOpenFileName(self, "选择资料文件", str(Path.home()),
                                               "所有文件 (*.*)")
        if p:
            self.ed_target.setText(p)

    def _save(self) -> None:
        if not self.ed_title.text().strip():
            warn(self, "请填写资料名称。")
            return
        kind = {"网络链接": "link", "本地文件": "file", "本地文件夹": "dir"}[
            self.cb_kind.currentText()]
        self.db.save_material({
            "title": self.ed_title.text().strip(),
            "category": self.cb_cat.currentText(),
            "kind": kind,
            "target": self.ed_target.text().strip(),
            "note": self.pt_note.toPlainText().strip(),
        }, self.material_id)
        self.accept()


# ================================================================ 分类管理


class CategoryDialog(QDialog):
    changed = Signal()

    def __init__(self, database: dbm.Database, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("证书分类管理")
        self.resize(520, 480)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        t = QLabel("证书分类管理")
        t.setStyleSheet(f"font-size:17px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(t)
        root.addWidget(_labeled("分类用于归档证书，删除分类后其下证书会归入「其他」。"))

        self.lst = QListWidget()
        root.addWidget(self.lst, 1)

        row = QHBoxLayout()
        self.ed_new = QLineEdit()
        self.ed_new.setPlaceholderText("新分类名称")
        btn_add = QPushButton("新增")
        btn_add.setObjectName("Primary")
        realize(btn_add, "plus", "#ffffff")
        btn_ren = QPushButton("重命名")
        realize(btn_ren, "edit", theme.TEXT_SUB)
        btn_del = QPushButton("删除")
        btn_del.setObjectName("Danger")
        realize(btn_del, "trash", theme.DANGER)
        btn_add.clicked.connect(self._add)
        btn_ren.clicked.connect(self._rename)
        btn_del.clicked.connect(self._delete)
        row.addWidget(self.ed_new, 1)
        row.addWidget(btn_add)
        row.addWidget(btn_ren)
        row.addWidget(btn_del)
        root.addLayout(row)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b = QPushButton("完成")
        b.clicked.connect(self.accept)
        foot.addWidget(b)
        root.addLayout(foot)
        self._reload()

    def _reload(self) -> None:
        self.lst.clear()
        stats = {s["name"]: s["total"] for s in self.db.category_stats()}
        for c in self.db.categories():
            item = QListWidgetItem(f"{c['name']}      共 {stats.get(c['name'], 0)} 本")
            item.setData(Qt.UserRole, c["name"])
            item.setIcon(icons.icon("folder", c["color"], 16))
            self.lst.addItem(item)

    def _add(self) -> None:
        name = self.ed_new.text().strip()
        if not name:
            return
        color = QColorDialog.getColor(QColor(theme.PRIMARY), self, "选择分类颜色")
        if self.db.add_category(name, color.name() if color.isValid() else theme.PRIMARY):
            self.ed_new.clear()
            self._reload()
            self.changed.emit()
        else:
            warn(self, "该分类已存在。")

    def _rename(self) -> None:
        item = self.lst.currentItem()
        if not item:
            return
        old = item.data(Qt.UserRole)
        new, ok = _text_input(self, "重命名分类", "新的分类名称：", old)
        if not ok or not new.strip():
            return
        if self.db.rename_category(old, new.strip()):
            self._reload()
            self.changed.emit()
        else:
            warn(self, "重命名失败：名称重复或为空。")

    def _delete(self) -> None:
        item = self.lst.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole)
        if not confirm(self, f"确定删除分类「{name}」？\n其下证书将归入「其他」。"):
            return
        self.db.delete_category(name)
        self._reload()
        self.changed.emit()


def _text_input(parent, title: str, label: str, default: str = "") -> tuple:
    dlg = QDialog(parent)
    dlg.setStyleSheet(dlg_qss())
    dlg.setWindowTitle(title)
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(18, 18, 18, 18)
    lay.addWidget(_labeled(label))
    ed = QLineEdit(default)
    lay.addWidget(ed)
    row = QHBoxLayout()
    row.addStretch(1)
    b1 = QPushButton("取消")
    b1.clicked.connect(dlg.reject)
    b2 = QPushButton("确定")
    b2.setObjectName("Primary")
    b2.clicked.connect(dlg.accept)
    row.addWidget(b1)
    row.addWidget(b2)
    lay.addLayout(row)
    dlg.resize(380, 140)
    if dlg.exec() == QDialog.Accepted:
        return ed.text(), True
    return "", False


# ================================================================ 设置


class SettingsDialog(QDialog):
    changed = Signal()

    def __init__(self, database: dbm.Database, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.db = database
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("设置")
        self.resize(620, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)
        t = QLabel("设置")
        t.setStyleSheet(f"font-size:17px; font-weight:700; color:{theme.TEXT};")
        root.addWidget(t)

        # 卡片一多，矮屏上就要被压扁；装进滚动区，窗口再小也只是需要滚一下。
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget, QScrollArea > QWidget > QWidget"
            " { background: transparent; border: none; }")
        body = QWidget()
        col = QVBoxLayout(body)
        col.setContentsMargins(0, 0, 6, 0)
        col.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        card = Card("到期提醒")
        self.sp_warn = SpinBox()
        self.sp_warn.setRange(1, 3650)
        self.sp_warn.setSuffix("  天")
        self.sp_warn.setValue(self.db.warn_days())
        self.sp_urgent = SpinBox()
        self.sp_urgent.setRange(1, 3650)
        self.sp_urgent.setSuffix("  天")
        self.sp_urgent.setValue(self.db.urgent_days())
        self.cb_popup = QCheckBox("启动时自动弹出到期提醒")
        self.cb_popup.setChecked(self.db.get_setting("popup_on_start", "1") == "1")
        card.add(_row("提前提醒", self.sp_warn))
        card.add(_row("紧急阈值", self.sp_urgent))
        card.add(self.cb_popup)
        hint = QLabel("说明：剩余天数 ≤ 提前提醒 进入「即将到期」，≤ 紧急阈值 进入「紧急」，"
                      "小于 0 天标记为「已过期」。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        card.add(hint)
        col.addWidget(card)

        card2 = Card("数据管理")
        path_row = QHBoxLayout()
        self.lbl_dir = QLabel(str(paths.DATA_DIR))
        self.lbl_dir.setStyleSheet(f"color:{theme.TEXT_SUB}; font-size:12px;")
        self.lbl_dir.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_open = QPushButton("打开目录")
        realize(btn_open, "folder", theme.TEXT_SUB)
        btn_open.clicked.connect(lambda: open_path(paths.DATA_DIR))
        path_row.addWidget(self.lbl_dir, 1)
        path_row.addWidget(btn_open)
        holder = QWidget()
        holder.setLayout(path_row)
        card2.add(holder)

        brow = QHBoxLayout()
        b_backup = QPushButton("备份数据库")
        realize(b_backup, "database", theme.TEXT_SUB)
        b_sample = QPushButton("载入示例数据")
        realize(b_sample, "star", theme.GOLD)
        b_clear = QPushButton("清空全部数据")
        b_clear.setObjectName("Danger")
        realize(b_clear, "trash", theme.DANGER)
        b_backup.clicked.connect(self._backup)
        b_sample.clicked.connect(self._sample)
        b_clear.clicked.connect(self._clear)
        brow.addWidget(b_backup)
        brow.addWidget(b_sample)
        brow.addStretch(1)
        brow.addWidget(b_clear)
        card2.add(brow)
        col.addWidget(card2)

        # ---------------------------------------------------- 窗口悬浮窗
        card3 = Card("窗口悬浮窗")
        self.cb_float = QCheckBox("启用桌面悬浮窗（顶栏的悬浮图标 / Ctrl+Shift+F 也可随时开关）")
        self.cb_float.setChecked(self.db.get_setting("float_on", "0") == "1")
        self.cb_float_top = QCheckBox("始终置顶显示")
        self.cb_float_top.setChecked(self.db.get_setting("float_top", "1") == "1")
        self.cb_float_hide = QCheckBox("靠边后自动收起成一条窄边（鼠标移上去自动展开）")
        self.cb_float_hide.setChecked(self.db.get_setting("float_autohide", "0") == "1")
        self.sp_rows = SpinBox()
        self.sp_rows.setRange(1, 12)
        self.sp_rows.setSuffix("  行")
        try:
            rows = int(self.db.get_setting("float_max_rows", "5"))
        except (TypeError, ValueError):
            rows = 5
        self.sp_rows.setValue(max(1, min(12, rows)))
        card3.add(self.cb_float)
        card3.add(self.cb_float_top)
        card3.add(self.cb_float_hide)
        card3.add(_row("列表条数", self.sp_rows))

        lbl_blocks = QLabel("显示哪些内容")
        lbl_blocks.setObjectName("Muted")
        card3.add(lbl_blocks)
        chosen = {s.strip() for s in
                  (self.db.get_setting("float_blocks", "") or "").split(",") if s.strip()}
        if not chosen:
            chosen = set(FLOAT_DEFAULT_BLOCKS.split(","))
        holder = QWidget()
        grid = QGridLayout(holder)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)
        self.cb_blocks: Dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(FLOAT_BLOCKS):
            cb = QCheckBox(label)
            cb.setChecked(key in chosen)
            self.cb_blocks[key] = cb
            grid.addWidget(cb, i // 3, i % 3)
        card3.add(holder)

        hint3 = QLabel("提示：拖动悬浮窗顶部移动，靠近屏幕边缘自动吸附；"
                       "面板上右键可以直接勾选内容、置顶与贴边收起。")
        hint3.setObjectName("Muted")
        hint3.setWordWrap(True)
        card3.add(hint3)
        col.addWidget(card3)

        # ---------------------------------------------------- 系统托盘
        card4 = Card("系统托盘")
        self.cb_tray = QCheckBox(
            "最小化时收进系统托盘（窗口隐藏，桌面悬浮窗继续驻留）")
        self.cb_tray.setChecked(self.db.get_setting("tray_on", "1") == "1")
        self.cb_tray_close = QCheckBox(
            "关闭窗口时也收进托盘（真退出请用托盘菜单的「退出」）")
        self.cb_tray_close.setChecked(self.db.get_setting("close_to_tray", "1") == "1")
        self.cb_tray_notify = QCheckBox(
            "收进托盘后用气泡通知提醒有证书将到期")
        self.cb_tray_notify.setChecked(
            self.db.get_setting("tray_notify", "1") == "1")
        card4.add(self.cb_tray)
        card4.add(self.cb_tray_close)
        card4.add(self.cb_tray_notify)
        hint4 = QLabel("提示：托盘图标上单击可恢复窗口，右键打开菜单"
                       "（显示主窗口 / 到期提醒 / 悬浮窗开关 / 立即检查 / 退出）。")
        hint4.setObjectName("Muted")
        hint4.setWordWrap(True)
        card4.add(hint4)
        col.addWidget(card4)

        # ---------------------------------------------------- 开机自启
        card5 = Card("开机自启")
        from . import autostart
        self.cb_autostart = QCheckBox("随 Windows 登录自动启动证书管理库")
        # 以**注册表实际状态**为准，而不是设置项：设置项可能与注册表不一致
        # （比如用户手工在注册表里删了项，或换了机器/换了 exe 路径）。
        self.cb_autostart.setChecked(autostart.is_enabled())
        if not autostart.is_supported():
            # 开发态 / 非 Windows：明说原因，并禁用控件，别让用户勾一个无效开关
            self.cb_autostart.setEnabled(False)
            self.cb_autostart.setToolTip(autostart.status())
        card5.add(self.cb_autostart)
        self.lb_autostart = QLabel(autostart.status())
        self.lb_autostart.setObjectName("Muted")
        self.lb_autostart.setWordWrap(True)
        card5.add(self.lb_autostart)
        col.addWidget(card5)

        col.addStretch(1)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b1 = QPushButton("取消")
        b1.clicked.connect(self.reject)
        b2 = QPushButton("保存设置")
        b2.setObjectName("Primary")
        realize(b2, "check", "#ffffff")
        b2.clicked.connect(self._save)
        foot.addWidget(b1)
        foot.addWidget(b2)
        root.addLayout(foot)

    def _save(self) -> None:
        if self.sp_urgent.value() > self.sp_warn.value():
            warn(self, "紧急阈值不能大于提前提醒天数。")
            return
        blocks = [k for k, cb in self.cb_blocks.items() if cb.isChecked()]
        if self.cb_float.isChecked() and not blocks:
            warn(self, "启用悬浮窗时至少要勾选一块显示内容。")
            return
        self.db.set_setting("warn_days", str(self.sp_warn.value()))
        self.db.set_setting("urgent_days", str(self.sp_urgent.value()))
        self.db.set_setting("popup_on_start", "1" if self.cb_popup.isChecked() else "0")
        self.db.set_setting("float_on", "1" if self.cb_float.isChecked() else "0")
        self.db.set_setting("float_top", "1" if self.cb_float_top.isChecked() else "0")
        self.db.set_setting("float_autohide",
                            "1" if self.cb_float_hide.isChecked() else "0")
        self.db.set_setting("float_blocks", ",".join(blocks))
        self.db.set_setting("float_max_rows", str(self.sp_rows.value()))
        self.db.set_setting("tray_on", "1" if self.cb_tray.isChecked() else "0")
        self.db.set_setting("close_to_tray",
                            "1" if self.cb_tray_close.isChecked() else "0")
        self.db.set_setting("tray_notify",
                            "1" if self.cb_tray_notify.isChecked() else "0")

        # 开机自启：**先改注册表，成功/已达成才落库**。
        # 反过来（先落库再写注册表）会留下「设置显示已开启、实际没生效」的假状态。
        want = self.cb_autostart.isChecked()
        if self.cb_autostart.isEnabled():
            from . import autostart
            err = autostart.sync(want)
            if err:
                warn(self, f"开机自启设置失败：\n{err}")
                return
        self.db.set_setting("autostart", "1" if want else "0")

        self.changed.emit()
        self.accept()

    def _backup(self) -> None:
        p = self.db.backup()
        if p:
            info(self, f"已备份到：\n{p}")
        else:
            error(self, "备份失败。")

    def _sample(self) -> None:
        from .sampledata import load_samples
        n = load_samples(self.db)
        info(self, f"已载入 {n} 条示例数据，可在证书管理中直接查看或删除。")
        self.changed.emit()

    def _clear(self) -> None:
        if not confirm(self, "确定清空全部证书 / 考试计划 / 学习资料？\n"
                            "此操作不可撤销，建议先备份数据库。"):
            return
        for r in self.db.certificates():
            self.db.delete_certificate(r["id"])
        for e in self.db.exams():
            self.db.delete_exam(e["id"])
        for m in self.db.materials():
            self.db.delete_material(m["id"])
        info(self, "数据已清空。")
        self.changed.emit()


# ============================================================ 到期提醒弹窗


class ReminderDialog(QDialog):
    """到期提醒：启动时或手动唤起的集中提醒面板。"""

    goto_certs = Signal()

    def __init__(self, database: dbm.Database, parent: Optional[QWidget] = None,
                 startup: bool = True) -> None:
        super().__init__(parent)
        self.db = database
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("证书到期提醒")
        self.resize(660, 560)
        self.setModal(True)

        rows = self.db.expiring()
        expired = [r for r in rows if r["status_key"] == "expired"]
        urgent = [r for r in rows if r["status_key"] == "urgent"]
        soon = [r for r in rows if r["status_key"] == "soon"]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        band = QFrame()
        band.setStyleSheet(f"background:{theme.SIDEBAR};")
        bl = QHBoxLayout(band)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(12)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("bell", theme.GOLD, 30))
        bl.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel("证书到期提醒")
        t.setStyleSheet("color:#ffffff; font-size:17px; font-weight:700;")
        col.addWidget(t)
        sub = QLabel(f"共 {len(rows)} 本证书需要关注"
                     f"（已过期 {len(expired)} · 紧急 {len(urgent)} · 即将到期 {len(soon)}）")
        sub.setStyleSheet("color:#9fb0c2; font-size:12px;")
        col.addWidget(sub)
        bl.addLayout(col)
        bl.addStretch(1)
        root.addWidget(band)

        body = QVBoxLayout()
        body.setContentsMargins(18, 16, 18, 16)
        body.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        iv = QVBoxLayout(inner)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(14)

        for title, group, tone in (("已过期（需尽快处理）", expired, theme.DANGER),
                                   ("紧急（临近到期）", urgent, "#e0622c"),
                                   ("即将到期", soon, theme.WARN)):
            if not group:
                continue
            c = Card(title, f"{len(group)} 本", padding=14)
            c.title.setStyleSheet(f"font-size:14px; font-weight:700; color:{tone};")
            for r in group:
                c.add(_reminder_row(self.db, r))
            iv.addWidget(c)
        if not rows:
            from .widgets import EmptyState
            iv.addWidget(EmptyState("太好了，暂时没有到期的证书",
                                    "所有证书都在有效期内。", "check"))
        iv.addStretch(1)
        scroll.setWidget(inner)
        body.addWidget(scroll, 1)

        foot = QHBoxLayout()
        self.cb_mute = QCheckBox("今天不再提醒")
        foot.addWidget(self.cb_mute)
        foot.addStretch(1)
        b_detail = QPushButton("查看到期清单")
        realize(b_detail, "bell", theme.PRIMARY)
        b_ok = QPushButton("知道了")
        b_ok.setObjectName("Primary")
        if not rows:
            b_detail.setEnabled(False)
        b_detail.clicked.connect(self._goto)
        b_ok.clicked.connect(self.accept)
        foot.addWidget(b_detail)
        foot.addWidget(b_ok)
        body.addLayout(foot)
        root.addLayout(body)

        if startup and not rows:
            self.setWindowTitle("证书到期提醒")
        self._mute = False

    def _goto(self) -> None:
        self._mute = self.cb_mute.isChecked()
        self.goto_certs.emit()
        self.accept()

    @property
    def muted_today(self) -> bool:
        return self.cb_mute.isChecked()


def _reminder_row(database: dbm.Database, r: Dict[str, Any]) -> QWidget:
    w = QFrame()
    w.setObjectName("Card")
    w.setStyleSheet(f"#Card {{ background:#fbfcfe; border:1px solid {theme.BORDER};"
                    f" border-radius:9px; }}")
    lay = QHBoxLayout(w)
    lay.setContentsMargins(12, 9, 12, 9)
    lay.setSpacing(10)

    dot = QLabel()
    dot.setPixmap(icons.pixmap("warn", theme.status_color(r["status_key"]), 18))
    lay.addWidget(dot)

    col = QVBoxLayout()
    col.setSpacing(2)
    n = QLabel(r["name"])
    n.setStyleSheet(f"font-weight:600; color:{theme.TEXT};")
    col.addWidget(n)
    meta = QLabel(f"{r['category']} · 到期 {r['expiry_date']}"
                  + (f" · {r['issuer']}" if r.get("issuer") else ""))
    meta.setStyleSheet(f"color:{theme.MUTED}; font-size:11px;")
    col.addWidget(meta)
    lay.addLayout(col, 1)
    lay.addWidget(status_badge(r["status_key"]))
    left = QLabel(r["left_text"])
    left.setStyleSheet(f"color:{theme.status_color(r['status_key'])};"
                       f" font-weight:600; font-size:12px;")
    left.setFixedWidth(96)
    left.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    lay.addWidget(left)
    return w


# ========================================================== 提醒处置 · 延期


class PostponeDialog(QDialog):
    """自定义延期：挑一个日子，在那天之前这本证书不再提醒。"""

    def __init__(self, cert_name: str, parent: Optional[QWidget] = None,
                 days: int = 30) -> None:
        super().__init__(parent)
        self.setStyleSheet(dlg_qss())
        self.setWindowTitle("自定义延期")
        self.setModal(True)
        self.resize(430, 236)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(11)

        t = QLabel(f"把「{cert_name}」的提醒延到哪一天？")
        t.setWordWrap(True)
        t.setStyleSheet(f"color:{theme.TEXT}; font-weight:700; font-size:13px;")
        root.addWidget(t)

        hint = QLabel("在所选日期（含）之前，这本证书不会出现在「需要关注」里，"
                      "启动提醒与悬浮窗也不会再提它；过了这天自动恢复提醒。")
        hint.setWordWrap(True)
        hint.setObjectName("Muted")
        root.addWidget(hint)

        self.date_edit = DateEdit(QDate.currentDate().addDays(days))
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        # 不允许选今天或更早 —— 那样等于没有延期
        self.date_edit.setMinimumDate(QDate.currentDate().addDays(1))
        drow = QHBoxLayout()
        drow.setSpacing(10)
        lab = QLabel("提醒日期")
        lab.setObjectName("Muted")
        drow.addWidget(lab)
        drow.addWidget(self.date_edit, 1)
        root.addLayout(drow)

        quick = QHBoxLayout()
        quick.setSpacing(6)
        qlab = QLabel("快捷")
        qlab.setObjectName("Muted")
        quick.addWidget(qlab)
        for dd in (7, 15, 30, 60, 90, 180):
            b = QPushButton(f"{dd} 天")
            b.setObjectName("Ghost")
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(
                lambda _=False, n=dd: self.date_edit.setDate(
                    QDate.currentDate().addDays(n)))
            quick.addWidget(b)
        quick.addStretch(1)
        root.addLayout(quick)

        foot = QHBoxLayout()
        foot.addStretch(1)
        b_cancel = QPushButton("取消")
        b_ok = QPushButton("确定延期")
        b_ok.setObjectName("Primary")
        realize(b_ok, "clock", "#ffffff")
        b_cancel.clicked.connect(self.reject)
        b_ok.clicked.connect(self.accept)
        foot.addWidget(b_cancel)
        foot.addWidget(b_ok)
        root.addLayout(foot)

    def until(self) -> str:
        """选定的日期，iso 格式。"""
        q = self.date_edit.date()
        return f"{q.year():04d}-{q.month():02d}-{q.day():02d}"
