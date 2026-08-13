"""SQLite 数据层：错题、评论、待绑定评论、AI 解析、整理状态。"""
from __future__ import annotations

import datetime
import json
import sqlite3
import threading
from typing import Any

_QUESTION_COLS = [
    "id", "question_id", "stem", "options", "correct_answer", "my_answer",
    "paper", "unit", "question_type", "kaodian", "standard_explanation",
    "explanation_blob", "stats", "comment_tags", "has_image", "image_path",
    "chapter_label", "system_group", "ai_summary", "ai_mnemonics",
    "ai_wrong_reason", "ai_explanation", "created_at", "updated_at", "processed",
]


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


class DB:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    # ---------- schema ----------
    def _init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS questions (
                    id TEXT PRIMARY KEY,
                    question_id TEXT,
                    stem TEXT,
                    options TEXT,
                    correct_answer TEXT,
                    my_answer TEXT,
                    paper TEXT,
                    unit TEXT,
                    question_type TEXT,
                    kaodian TEXT,
                    standard_explanation TEXT,
                    explanation_blob TEXT,
                    stats TEXT,
                    comment_tags TEXT,
                    has_image INTEGER DEFAULT 0,
                    image_path TEXT,
                    chapter_label TEXT,
                    system_group TEXT,
                    ai_summary TEXT,
                    ai_mnemonics TEXT,
                    ai_wrong_reason TEXT,
                    ai_explanation TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    processed INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_id TEXT,
                    nickname TEXT,
                    content TEXT,
                    likes INTEGER DEFAULT 0,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS pending_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    paper TEXT,
                    nickname TEXT,
                    content TEXT,
                    likes INTEGER DEFAULT 0,
                    created_at TEXT
                );
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_comments_q ON comments(question_id);
                CREATE INDEX IF NOT EXISTS idx_questions_paper ON questions(paper);
                """
            )
            self._conn.commit()

    # ---------- helpers ----------
    @staticmethod
    def _pack(q: dict) -> dict:
        d = dict(q)
        if "options" in d and isinstance(d["options"], (dict, list)):
            d["options"] = json.dumps(d["options"], ensure_ascii=False)
        if "comment_tags" in d and isinstance(d["comment_tags"], list):
            d["comment_tags"] = json.dumps(d["comment_tags"], ensure_ascii=False)
        if "has_image" in d:
            d["has_image"] = 1 if d["has_image"] else 0
        if "processed" in d:
            d["processed"] = 1 if d["processed"] else 0
        return d

    @staticmethod
    def _unpack(row: sqlite3.Row) -> dict:
        d = dict(row)
        for key in ("options", "comment_tags"):
            if d.get(key):
                try:
                    d[key] = json.loads(d[key])
                except (TypeError, json.JSONDecodeError):
                    d[key] = []
        return d

    # ---------- questions ----------
    def upsert_question(self, q: dict) -> bool:
        """写回一条错题（按 id=题干哈希 合并，非空字段覆盖），返回是否新建。"""
        with self._lock:
            existing = self._get_row("questions", q["id"])
            merged = dict(existing) if existing else {}
            for k in _QUESTION_COLS:
                v = q.get(k)
                if v not in (None, ""):
                    merged[k] = v
            if existing is None:
                merged["created_at"] = now_iso()
            merged["updated_at"] = now_iso()
            merged.setdefault("processed", 0)
            self._upsert("questions", self._pack(merged))
            return existing is None

    def get_question(self, qid: str) -> dict | None:
        with self._lock:
            row = self._get_row("questions", qid)
            return self._unpack(row) if row else None

    def recent_question(self, paper: str, window_minutes: int,
                        before_iso: str | None = None) -> dict | None:
        """合并窗口内最近的题干记录（用于评论区并入）。"""
        before_iso = before_iso or now_iso()
        start = (datetime.datetime.fromisoformat(before_iso)
                 - datetime.timedelta(minutes=window_minutes)).isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM questions WHERE paper=? AND created_at>=? AND stem IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (paper, start),
            )
            row = cur.fetchone()
            return self._unpack(row) if row else None

    def set_question_ai(self, qid: str, group: str, summary: str,
                        mnemonic: str, wrong_reason: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE questions SET system_group=?, ai_summary=?, ai_mnemonics=?, "
                "ai_wrong_reason=?, processed=1, updated_at=? WHERE id=?",
                (group, summary, mnemonic, wrong_reason, now_iso(), qid),
            )
            self._conn.commit()

    def unprocessed_questions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM questions WHERE stem IS NOT NULL AND processed=0 "
                "ORDER BY created_at"
            ).fetchall()
            return [self._unpack(r) for r in rows]

    def all_processed_questions(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM questions WHERE stem IS NOT NULL AND processed=1 "
                "ORDER BY created_at"
            ).fetchall()
            return [self._unpack(r) for r in rows]

    def count_questions(self) -> int:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]

    # ---------- comments ----------
    def append_comments(self, qid: str, comments: list[dict]) -> int:
        """向某题追加评论（按内容去重），返回新增条数。"""
        if not comments:
            return 0
        with self._lock:
            existing = {
                r["content"]
                for r in self._conn.execute(
                    "SELECT content FROM comments WHERE question_id=?", (qid,)
                ).fetchall()
            }
            added = 0
            for c in comments:
                content = (c.get("content") or "").strip()
                if not content or content in existing:
                    continue
                self._conn.execute(
                    "INSERT INTO comments(question_id, nickname, content, likes, created_at) "
                    "VALUES(?,?,?,?,?)",
                    (qid, c.get("nickname", ""), content, int(c.get("likes") or 0), now_iso()),
                )
                existing.add(content)
                added += 1
            self._conn.commit()
            return added

    def get_comments(self, qid: str) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT nickname, content, likes FROM comments WHERE question_id=? "
                "ORDER BY likes DESC", (qid,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ---------- pending comments（待绑定）----------
    def add_pending(self, paper: str, comments: list[dict]) -> int:
        if not comments:
            return 0
        with self._lock:
            added = 0
            for c in comments:
                content = (c.get("content") or "").strip()
                if not content:
                    continue
                self._conn.execute(
                    "INSERT INTO pending_comments(paper, nickname, content, likes, created_at) "
                    "VALUES(?,?,?,?,?)",
                    (paper, c.get("nickname", ""), content, int(c.get("likes") or 0), now_iso()),
                )
                added += 1
            self._conn.commit()
            return added

    def bind_pending(self, qid: str, paper: str) -> int:
        """把某试卷的待绑定评论并入指定题，前提是该待绑定晚于该试卷其他任何题目。

        规则：只绑定「创建时间晚于该试卷上其他所有题」的待绑定，且限 60 分钟内的。
        避免把 A 题评论误绑到后录的 B 题。
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT MAX(created_at) FROM questions WHERE paper=? AND id!=?", (paper, qid)
            ).fetchone()
            last_other = row[0] or "1970-01-01T00:00:00"
            bound: list[sqlite3.Row] = self._conn.execute(
                "SELECT * FROM pending_comments WHERE paper=? AND created_at>? "
                "AND created_at>=?",
                (paper, last_other, now_iso()[:11]),  # created_at>= 今日零点，粗滤
            ).fetchall()
            if not bound:
                return 0
            for r in bound:
                self._conn.execute(
                    "INSERT INTO comments(question_id, nickname, content, likes, created_at) "
                    "VALUES(?,?,?,?,?)",
                    (qid, r["nickname"], r["content"], r["likes"], r["created_at"]),
                )
                self._conn.execute("DELETE FROM pending_comments WHERE id=?", (r["id"],))
            self._conn.commit()
            return len(bound)

    # ---------- meta ----------
    def meta_get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            row = self._conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
            if not row:
                return default
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]

    def meta_set(self, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO meta(key,value) VALUES(?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, json.dumps(value, ensure_ascii=False)),
            )
            self._conn.commit()

    # ---------- raw ----------
    def _get_row(self, table: str, pk: str) -> sqlite3.Row | None:
        return self._conn.execute(f"SELECT * FROM {table} WHERE id=?", (pk,)).fetchone()

    def _upsert(self, table: str, d: dict) -> None:
        cols = list(d.keys())
        sql = f"INSERT INTO {table}({','.join(cols)}) VALUES({','.join('?' * len(cols))}) " \
              f"ON CONFLICT(id) DO UPDATE SET " + \
              ",".join(f"{c}=excluded.{c}" for c in cols if c != "id")
        self._conn.execute(sql, [d[c] for c in cols])
        self._conn.commit()
