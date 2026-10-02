# -*- coding: utf-8 -*-
"""SQLite 数据层：证书 / 分类 / 附件 / 考试计划 / 学习资料 / 设置。

设计取舍：
- 用标准库 sqlite3 而非 ORM —— 单文件 exe 体积敏感，且查询逻辑简单，手写 SQL 更透明。
- 附件不存 BLOB，而是把用户选择的文件复制到 data/files/ 并记录相对路径：
  这样 PDF 能直接被 QtPdf 打开预览，也不会把数据库撑大。
"""

from __future__ import annotations

import shutil
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    name     TEXT NOT NULL UNIQUE,
    color    TEXT NOT NULL DEFAULT '#2e6f9e',
    sort     INTEGER NOT NULL DEFAULT 100,
    builtin  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS certificates (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT '其他',
    number      TEXT DEFAULT '',
    holder      TEXT DEFAULT '',
    issuer      TEXT DEFAULT '',
    level       TEXT DEFAULT '',
    issue_date  TEXT DEFAULT '',
    expiry_date TEXT DEFAULT '',
    active      INTEGER NOT NULL DEFAULT 1,
    remark      TEXT DEFAULT '',
    created_at  TEXT DEFAULT '',
    updated_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS attachments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    cert_id    INTEGER NOT NULL,
    title      TEXT NOT NULL DEFAULT '',
    kind       TEXT NOT NULL DEFAULT 'file',
    path       TEXT NOT NULL DEFAULT '',
    size       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT '',
    FOREIGN KEY (cert_id) REFERENCES certificates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exams (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    category    TEXT DEFAULT '',
    exam_date   TEXT DEFAULT '',
    reg_deadline TEXT DEFAULT '',
    location    TEXT DEFAULT '',
    fee         TEXT DEFAULT '',
    state       TEXT DEFAULT '计划中',
    score       TEXT DEFAULT '',
    remark      TEXT DEFAULT '',
    created_at  TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS materials (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    category   TEXT NOT NULL DEFAULT '学习资料',
    kind       TEXT NOT NULL DEFAULT 'link',
    target     TEXT NOT NULL DEFAULT '',
    note       TEXT DEFAULT '',
    created_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);

-- 提醒处置（v1.3.0）：每本证书一行，记「延到哪天再提醒」「忽略到哪天」。
-- 删除证书时靠 ON DELETE CASCADE 一起清掉，不会留下孤儿行。
CREATE TABLE IF NOT EXISTS reminder_state (
    cert_id         INTEGER PRIMARY KEY,
    ignored_until   TEXT NOT NULL DEFAULT '',   -- 'yyyy-mm-dd'；FOREVER = 永久忽略
    postponed_until TEXT NOT NULL DEFAULT '',   -- 'yyyy-mm-dd' 之前不再提醒
    handled_at      TEXT NOT NULL DEFAULT '',   -- 最近一次处置的时间，留痕
    note            TEXT NOT NULL DEFAULT '',
    FOREIGN KEY (cert_id) REFERENCES certificates(id) ON DELETE CASCADE
);
"""

# 「忽略到永远」的哨兵日期。选 9999-12-31 是为了不用给表加一个布尔列，
# 判定时只跟 iso 日期字符串比大小，逻辑与普通日期完全一致。
FOREVER = "9999-12-31"

# 处置菜单里的预设档位（天数）；忽略列表里的 0 表示「永久」。
POSTPONE_CHOICES = (7, 30, 90, 180, 365)
IGNORE_CHOICES = (7, 30, 90, 0)

DEFAULT_CATEGORIES = [
    ("职业资格", "#2e6f9e", 10),
    ("语言能力", "#2f9e63", 20),
    ("学历学位", "#6b5bb5", 30),
    ("技能认证", "#c9a227", 40),
    ("培训合格", "#e08b2c", 50),
    ("荣誉奖项", "#c05299", 60),
    ("其他", "#8a99ab", 90),
]

DEFAULT_SETTINGS: Dict[str, str] = {
    "warn_days": "90",          # 进入「即将到期」的天数阈值
    "urgent_days": "30",        # 进入「紧急」的天数阈值
    "popup_on_start": "1",      # 启动时是否弹出到期提醒
    "last_popup_date": "",      # 记录已弹过提醒的日期，避免同日反复打扰
    "data_version": "1",
    # ---- 窗口悬浮窗（floatwin.py）。老库靠 INSERT OR IGNORE 自动补齐，无需迁移。
    "float_on": "0",            # 是否显示桌面悬浮窗（用户的总开关）
    "float_top": "1",           # 是否始终置顶
    "float_autohide": "0",      # 靠边后是否自动收起成一条窄边
    "float_blocks": "clock,stats,expiring,exams",   # 显示哪些内容块
    "float_max_rows": "5",      # 列表类内容块最多显示几行
    "float_x": "",              # 面板位置（上回关掉时留在哪，就还在哪）
    "float_y": "",
    # ---- 系统托盘（tray.py）。同样靠 INSERT OR IGNORE 自动补齐，无需迁移。
    "tray_on": "1",             # 最小化时收进托盘（而不是缩在任务栏里）
    "close_to_tray": "1",       # 关闭窗口也收进托盘；真退出走托盘菜单的「退出」
    "tray_notify": "1",         # 收进托盘后用气泡通知提醒即将到期
    # ---- 开机自启（autostart.py）。与上面三项同样靠 INSERT OR IGNORE 自动补齐。
    "autostart": "0",           # 是否随Windows 登录自动启动（见 autostart.py）
}

EXAM_STATES = ["计划中", "已报名", "已通过", "未通过", "已取消"]
MATERIAL_CATEGORIES = ["考试大纲", "官方教材", "历年真题", "网课视频", "笔记整理", "政策文件", "其他"]


def today_str() -> str:
    return date.today().isoformat()


def parse_date(value: str) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except Exception:  # noqa: BLE001
        return None


def cert_validity(expiry: str, warn_days: int = 90, urgent_days: int = 30,
                  today: Optional[date] = None):
    """返回 (状态键, 中文名, 剩余天数或 None)。

    状态键：permanent / expired / urgent / soon / valid
    """
    today = today or date.today()
    d = parse_date(expiry)
    if d is None:
        return "permanent", "长期有效", None
    left = (d - today).days
    if left < 0:
        return "expired", "已过期", left
    if left <= urgent_days:
        return "urgent", "紧急", left
    if left <= warn_days:
        return "soon", "即将到期", left
    return "valid", "有效", left


def left_text(left: Optional[int]) -> str:
    if left is None:
        return "—"
    if left < 0:
        return f"已过期 {abs(left)} 天"
    if left == 0:
        return "今天到期"
    return f"剩余 {left} 天"


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _suppressed(cert: Dict[str, Any], today: str) -> str:
    """该证书当前是否被处置压住：``postponed`` / ``ignored`` / ``''``。

    比的是 iso 日期字符串（含当日），所以「延至今天」= 今天仍不提醒。
    延期优先于忽略：两者独立时先看延期是否还在有效期内。
    """
    p = cert.get("postponed_until") or ""
    if p and p >= today:
        return "postponed"
    g = cert.get("ignored_until") or ""
    if g and g >= today:
        return "ignored"
    return ""


def suppress_label(cert: Dict[str, Any], today: Optional[str] = None) -> str:
    """给界面用的一句话说明：这个证书被怎么处理掉了、到什么时候为止。"""
    today = today or date.today().isoformat()
    kind = cert.get("suppressed") or ""
    if kind == "postponed":
        return f"已延至 {cert.get('postponed_until') or '—'}"
    if kind == "ignored":
        if cert.get("handled_at") and (cert.get("ignored_until") or "") == today:
            return "已标记处理"
        end = cert.get("ignored_until") or ""
        return "已永久忽略" if end == FOREVER else f"已忽略至 {end or '—'}"
    if cert.get("postponed_until"):
        return f"延期已过（{cert['postponed_until']}）"
    if cert.get("ignored_until"):
        return "忽略已过"
    return ""


class Database:
    def __init__(self, path: Optional[Path] = None) -> None:
        paths.ensure_dirs()
        self.path = Path(path) if path else paths.DB_PATH
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()

    # ------------------------------------------------------------ 基础设施
    def _migrate(self) -> None:
        self.conn.executescript(SCHEMA)
        cur = self.conn.execute("SELECT COUNT(*) AS c FROM categories")
        if cur.fetchone()["c"] == 0:
            self.conn.executemany(
                "INSERT INTO categories(name, color, sort, builtin) VALUES (?,?,?,1)",
                DEFAULT_CATEGORIES,
            )
        for k, v in DEFAULT_SETTINGS.items():
            self.conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?,?)", (k, v))
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.commit()
            self.conn.close()
        except Exception:  # noqa: BLE001
            pass

    def _q(self, sql: str, args: Iterable[Any] = ()) -> List[sqlite3.Row]:
        return list(self.conn.execute(sql, tuple(args)).fetchall())

    def _one(self, sql: str, args: Iterable[Any] = ()) -> Optional[sqlite3.Row]:
        rows = self._q(sql, args)
        return rows[0] if rows else None

    def _exec(self, sql: str, args: Iterable[Any] = ()) -> int:
        cur = self.conn.execute(sql, tuple(args))
        self.conn.commit()
        return cur.lastrowid or 0

    # ---------------------------------------------------------------- 设置
    def get_setting(self, key: str, default: str = "") -> str:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO settings(key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    def warn_days(self) -> int:
        try:
            return max(1, int(self.get_setting("warn_days", "90")))
        except ValueError:
            return 90

    def urgent_days(self) -> int:
        try:
            return max(1, int(self.get_setting("urgent_days", "30")))
        except ValueError:
            return 30

    # ---------------------------------------------------------------- 分类
    def categories(self) -> List[sqlite3.Row]:
        return self._q("SELECT * FROM categories ORDER BY sort, id")

    def category_names(self) -> List[str]:
        return [r["name"] for r in self.categories()]

    def category_color(self, name: str) -> str:
        row = self._one("SELECT color FROM categories WHERE name=?", (name,))
        return row["color"] if row else "#8a99ab"

    def add_category(self, name: str, color: str = "#2e6f9e") -> bool:
        name = name.strip()
        if not name:
            return False
        if self._one("SELECT id FROM categories WHERE name=?", (name,)):
            return False
        maxsort = self._one("SELECT MAX(sort) AS m FROM categories")
        nxt = (maxsort["m"] or 100) + 10
        self._exec("INSERT INTO categories(name, color, sort, builtin) VALUES (?,?,?,0)",
                   (name, color, nxt))
        return True

    def rename_category(self, old: str, new: str) -> bool:
        new = new.strip()
        if not new or old == new:
            return False
        if self._one("SELECT id FROM categories WHERE name=?", (new,)):
            return False
        self._exec("UPDATE categories SET name=? WHERE name=?", (new, old))
        self._exec("UPDATE certificates SET category=? WHERE category=?", (new, old))
        return True

    def delete_category(self, name: str) -> bool:
        row = self._one("SELECT builtin FROM categories WHERE name=?", (name,))
        if not row:
            return False
        self._exec("DELETE FROM categories WHERE name=?", (name,))
        self._exec("UPDATE certificates SET category='其他' WHERE category=?", (name,))
        return True

    def category_stats(self) -> List[Dict[str, Any]]:
        rows = self._q(
            "SELECT c.name AS name, c.color AS color, "
            "  (SELECT COUNT(*) FROM certificates t WHERE t.category=c.name) AS total "
            "FROM categories c ORDER BY total DESC, c.sort"
        )
        return [dict(r) for r in rows if r["total"] > 0]

    # ---------------------------------------------------------------- 证书
    def certificates(self, keyword: str = "", category: str = "", status: str = "",
                     include_inactive: bool = True) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM certificates WHERE 1=1"
        args: List[Any] = []
        if keyword:
            sql += (" AND (name LIKE ? OR number LIKE ? OR issuer LIKE ? "
                    "OR holder LIKE ? OR remark LIKE ?)")
            like = f"%{keyword}%"
            args += [like] * 5
        if category:
            sql += " AND category=?"
            args.append(category)
        if not include_inactive:
            sql += " AND active=1"
        sql += " ORDER BY (CASE WHEN expiry_date='' THEN 1 ELSE 0 END), expiry_date, id DESC"
        rows = [dict(r) for r in self._q(sql, args)]
        warn, urgent = self.warn_days(), self.urgent_days()
        for r in rows:
            key, label, left = cert_validity(r.get("expiry_date", ""), warn, urgent)
            r["status_key"] = key
            r["status_label"] = label
            r["left_days"] = left
            r["left_text"] = left_text(left)
            r["attach_count"] = (self._one(
                "SELECT COUNT(*) AS c FROM attachments WHERE cert_id=?", (r["id"],)
            )["c"])
        if status:
            rows = [r for r in rows if r["status_key"] == status]
        return rows

    def get_certificate(self, cid: int) -> Optional[Dict[str, Any]]:
        row = self._one("SELECT * FROM certificates WHERE id=?", (cid,))
        return dict(row) if row else None

    def certificate_with_status(self, cid: int) -> Optional[Dict[str, Any]]:
        """单本证书 + 有效期派生字段（供导出信息单使用）。"""
        cert = self.get_certificate(cid)
        if not cert:
            return None
        key, label, left = cert_validity(cert.get("expiry_date", ""),
                                         self.warn_days(), self.urgent_days())
        cert["status_key"] = key
        cert["status_label"] = label
        cert["left_days"] = left
        cert["left_text"] = left_text(left)
        return cert

    def save_certificate(self, data: Dict[str, Any], cid: Optional[int] = None) -> int:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields = ["name", "category", "number", "holder", "issuer", "level",
                  "issue_date", "expiry_date", "active", "remark"]
        values = [data.get(f, "") for f in fields]
        if cid:
            sets = ", ".join(f"{f}=?" for f in fields)
            self._exec(f"UPDATE certificates SET {sets}, updated_at=? WHERE id=?",
                       values + [now, cid])
            return cid
        cols = ", ".join(fields) + ", created_at, updated_at"
        marks = ", ".join("?" for _ in fields) + ", ?, ?"
        return self._exec(f"INSERT INTO certificates({cols}) VALUES ({marks})",
                          values + [now, now])

    def delete_certificate(self, cid: int) -> None:
        for a in self._q("SELECT path FROM attachments WHERE cert_id=?", (cid,)):
            self._remove_file(a["path"])
        self._exec("DELETE FROM attachments WHERE cert_id=?", (cid,))
        self._exec("DELETE FROM certificates WHERE id=?", (cid,))

    def certificate_stats(self) -> Dict[str, int]:
        rows = self.certificates()
        stats = {"total": 0, "valid": 0, "soon": 0, "urgent": 0,
                 "expired": 0, "permanent": 0, "inactive": 0}
        for r in rows:
            stats["total"] += 1
            stats[r["status_key"]] = stats.get(r["status_key"], 0) + 1
            if not r.get("active", 1):
                stats["inactive"] += 1
        return stats

    def expiring(self, include_suppressed: bool = False) -> List[Dict[str, Any]]:
        """到期与即将到期清单（含已过期），按剩余天数升序。

        默认**排除**已被「延期 / 忽略 / 标记已处理」压下的证书 —— 这样提醒弹窗、
        悬浮窗、首页概览与到期提醒页会同时遵守用户的处置意愿，不会东边忽略、
        西边还在弹。``include_suppressed=True`` 时全部返回，并用
        ``suppressed`` 标注处置方式（``postponed`` / ``ignored``）。
        """
        today = date.today().isoformat()
        states = self.reminder_states()
        out: List[Dict[str, Any]] = []
        for r in self.certificates():
            if r["status_key"] not in ("expired", "urgent", "soon"):
                continue
            st = states.get(r["id"]) or {}
            r["postponed_until"] = st.get("postponed_until", "")
            r["ignored_until"] = st.get("ignored_until", "")
            r["handled_at"] = st.get("handled_at", "")
            r["suppressed"] = _suppressed(r, today)
            if r["suppressed"] and not include_suppressed:
                continue
            out.append(r)
        out.sort(key=lambda r: (r["left_days"] if r["left_days"] is not None else 0))
        return out

    # ---------------------------------------------------------- 提醒处置
    def reminder_states(self) -> Dict[int, Dict[str, Any]]:
        """全部处置记录，按 cert_id 索引（一次查完，别在列表里逐条查）。"""
        return {r["cert_id"]: dict(r) for r in
                self._q("SELECT * FROM reminder_state")}

    def reminder_state(self, cert_id: int) -> Dict[str, Any]:
        row = self._one("SELECT * FROM reminder_state WHERE cert_id=?", (cert_id,))
        if row:
            return dict(row)
        return {"cert_id": cert_id, "ignored_until": "", "postponed_until": "",
                "handled_at": "", "note": ""}

    def _save_state(self, cert_id: int, **kw: str) -> None:
        st = self.reminder_state(cert_id)
        st.update(kw)
        # INSERT OR REPLACE 而不是 UPSERT：老库 SQLite 也能跑，且只有 5 列，够简单
        self._exec(
            "INSERT OR REPLACE INTO reminder_state"
            "(cert_id, ignored_until, postponed_until, handled_at, note)"
            " VALUES (?,?,?,?,?)",
            (cert_id, st["ignored_until"], st["postponed_until"],
             st["handled_at"], st["note"]),
        )

    def postpone_reminder(self, cert_id: int, days: int = 30,
                          until: Optional[str] = None) -> str:
        """把提醒延后。``until`` 给了就用它（自定义日期），否则 today + days。

        返回实际生效的日期。延期**不会**清掉忽略：若该证书同时处于忽略状态，
        恢复后仍按忽略的期限走 —— 两者独立，符合「先延后忽略」的实际用法。
        """
        target = until or (date.today() + timedelta(days=days)).isoformat()
        self._save_state(cert_id, postponed_until=target, handled_at=_now())
        return target

    def ignore_reminder(self, cert_id: int, days: int = 30) -> str:
        """忽略提醒。``days <= 0`` 表示永久忽略。返回截止日期。"""
        target = FOREVER if days <= 0 else (
            date.today() + timedelta(days=days)).isoformat()
        self._save_state(cert_id, ignored_until=target, handled_at=_now())
        return target

    def handle_reminder(self, cert_id: int) -> str:
        """标记已处理：今天不再提醒（等同于「忽略 1 天」）但留痕。

        用于「我知道了，这本我已自行换证 / 已提交材料」—— 与「忽略」的差别
        体现在 ``handled_at`` 有值，界面上会标成「已处理」。
        """
        today = date.today().isoformat()
        self._save_state(cert_id, ignored_until=today, handled_at=_now())
        return today

    def restore_reminder(self, cert_id: int) -> None:
        """清除处置，恢复正常提醒。"""
        self._exec("DELETE FROM reminder_state WHERE cert_id=?", (cert_id,))

    # ---------------------------------------------------------------- 附件
    def attachments(self, cert_id: int) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._q(
            "SELECT * FROM attachments WHERE cert_id=? ORDER BY id", (cert_id,))]

    def attach_file(self, cert_id: int, src: str) -> Optional[Dict[str, Any]]:
        srcp = Path(src)
        if not srcp.exists():
            return None
        paths.ensure_dirs()
        token = uuid.uuid4().hex[:8]
        safe = f"{cert_id}_{token}{srcp.suffix.lower()}"
        dst = paths.FILES_DIR / safe
        try:
            shutil.copy2(srcp, dst)
        except Exception:  # noqa: BLE001
            return None
        kind = "pdf" if srcp.suffix.lower() == ".pdf" else "file"
        aid = self._exec(
            "INSERT INTO attachments(cert_id, title, kind, path, size, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (cert_id, srcp.name, kind, safe, dst.stat().st_size,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        return {"id": aid, "cert_id": cert_id, "title": srcp.name, "kind": kind,
                "path": safe, "size": dst.stat().st_size}

    def attach_existing(self, cert_id: int, rel_path: str, title: str = "") -> int:
        p = paths.FILES_DIR / rel_path
        size = p.stat().st_size if p.exists() else 0
        return self._exec(
            "INSERT INTO attachments(cert_id, title, kind, path, size, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (cert_id, title or Path(rel_path).name,
             "pdf" if Path(rel_path).suffix.lower() == ".pdf" else "file",
             rel_path, size, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

    def remove_attachment(self, aid: int, delete_file: bool = True) -> None:
        row = self._one("SELECT path FROM attachments WHERE id=?", (aid,))
        self._exec("DELETE FROM attachments WHERE id=?", (aid,))
        if row and delete_file:
            self._remove_file(row["path"])

    @staticmethod
    def _remove_file(rel: str) -> None:
        try:
            p = paths.FILES_DIR / rel
            if p.exists():
                p.unlink()
        except Exception:  # noqa: BLE001
            pass

    def attachment_abspath(self, rel: str) -> Path:
        return paths.FILES_DIR / rel

    # ------------------------------------------------------------ 考试计划
    def exams(self, keyword: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM exams"
        args: List[Any] = []
        if keyword:
            sql += " WHERE name LIKE ? OR category LIKE ? OR location LIKE ? OR remark LIKE ?"
            args = [f"%{keyword}%"] * 4
        sql += " ORDER BY (CASE WHEN exam_date='' THEN 1 ELSE 0 END), exam_date, id DESC"
        rows = [dict(r) for r in self._q(sql, args)]
        today = date.today()
        for r in rows:
            d = parse_date(r.get("exam_date", ""))
            r["days_left"] = (d - today).days if d else None
            r["days_text"] = left_text(r["days_left"]) if d else "—"
            rd = parse_date(r.get("reg_deadline", ""))
            r["reg_days"] = (rd - today).days if rd else None
        return rows

    def upcoming_exams(self, limit: int = 6) -> List[Dict[str, Any]]:
        today = date.today()
        rows = [r for r in self.exams()
                if r["days_left"] is not None and r["days_left"] >= 0
                and r.get("state") in ("计划中", "已报名")]
        rows.sort(key=lambda r: r["days_left"])
        return rows[:limit]

    def save_exam(self, data: Dict[str, Any], eid: Optional[int] = None) -> int:
        fields = ["name", "category", "exam_date", "reg_deadline", "location",
                  "fee", "state", "score", "remark"]
        values = [data.get(f, "") for f in fields]
        if eid:
            sets = ", ".join(f"{f}=?" for f in fields)
            self._exec(f"UPDATE exams SET {sets} WHERE id=?", values + [eid])
            return eid
        cols = ", ".join(fields) + ", created_at"
        marks = ", ".join("?" for _ in fields) + ", ?"
        return self._exec(f"INSERT INTO exams({cols}) VALUES ({marks})",
                          values + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    def delete_exam(self, eid: int) -> None:
        self._exec("DELETE FROM exams WHERE id=?", (eid,))

    # ------------------------------------------------------------ 学习资料
    def materials(self, keyword: str = "", category: str = "") -> List[Dict[str, Any]]:
        sql = "SELECT * FROM materials WHERE 1=1"
        args: List[Any] = []
        if keyword:
            sql += " AND (title LIKE ? OR note LIKE ? OR target LIKE ?)"
            args += [f"%{keyword}%"] * 3
        if category:
            sql += " AND category=?"
            args.append(category)
        sql += " ORDER BY category, id DESC"
        return [dict(r) for r in self._q(sql, args)]

    def save_material(self, data: Dict[str, Any], mid: Optional[int] = None) -> int:
        fields = ["title", "category", "kind", "target", "note"]
        values = [data.get(f, "") for f in fields]
        if mid:
            sets = ", ".join(f"{f}=?" for f in fields)
            self._exec(f"UPDATE materials SET {sets} WHERE id=?", values + [mid])
            return mid
        cols = ", ".join(fields) + ", created_at"
        marks = ", ".join("?" for _ in fields) + ", ?"
        return self._exec(f"INSERT INTO materials({cols}) VALUES ({marks})",
                          values + [datetime.now().strftime("%Y-%m-%d %H:%M:%S")])

    def delete_material(self, mid: int) -> None:
        self._exec("DELETE FROM materials WHERE id=?", (mid,))

    def material_stats(self) -> Dict[str, int]:
        rows = self._q("SELECT category, COUNT(*) AS c FROM materials GROUP BY category")
        return {r["category"]: r["c"] for r in rows}

    # ------------------------------------------------------------ 数据管理
    def export_rows(self) -> List[Dict[str, Any]]:
        return self.certificates()

    def backup(self) -> Optional[Path]:
        paths.ensure_dirs()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = paths.BACKUP_DIR / f"library_{stamp}.db"
        try:
            self.conn.commit()
            shutil.copy2(self.path, dst)
            return dst
        except Exception:  # noqa: BLE001
            return None
