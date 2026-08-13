"""医考帮备考助手：tkinter 侧边窗 + 全局热键 + 后台工作线程。

界面：状态行（醒目） + 讲解区（含历史浏览） + 日志面板（时间戳）。
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk

from dotenv import load_dotenv

from core.config import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

from core.adb import Adb, AdbError  # noqa: E402
from core.aggregate_service import AggregateService  # noqa: E402
from core.config import load_config  # noqa: E402
from core.db import DB  # noqa: E402
from core.deepseek_client import DeepSeekClient, DeepSeekError  # noqa: E402
from core.explain_service import ExplainService  # noqa: E402
from core.record_service import RecordService  # noqa: E402

FONT = ("Microsoft YaHei", 11)


def _ts() -> str:
    return time.strftime("%H:%M:%S")


class App:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        os.makedirs(cfg["data"]["dir"], exist_ok=True)
        self.db = DB(os.path.join(cfg["data"]["dir"], "medical_notes.db"))

        self.adb = Adb()
        try:
            self.adb.connect()
            self._adb_ready, self._adb_err = True, None
        except AdbError as e:
            self._adb_ready, self._adb_err = False, str(e)

        try:
            self.client = DeepSeekClient(
                model=cfg.get("deepseek", {}).get("model", "deepseek-v4-flash"),
                base_url=cfg.get("deepseek", {}).get("base_url", "https://api.deepseek.com"),
            )
            self._ai_err = None
        except DeepSeekError as e:
            self.client, self._ai_err = None, str(e)

        self.record_svc = RecordService(self.adb, self.db, cfg)
        self.explain_svc = ExplainService(self.adb, self.client, self.db) if self.client else None
        self.aggregate_svc = AggregateService(self.db, self.client, cfg) if self.client else None

        # 解析历史（内存 + 入库），供下拉框回看
        self.hist: list[dict] = []
        self.hist_idx: int | None = None
        self.last_explained = None
        self.last_explained_text = ""

        self.work_q: queue.Queue = queue.Queue()
        self.ui_q: queue.Queue = queue.Queue()

        self._build_ui()
        self._load_history()
        self._start_worker()
        self._setup_hotkeys()

        self._refresh_count()
        for line in self._startup_lines():
            self._post_log(line)
        self._set_status(self._startup_status())
        self.root.after(80, self._poll_ui)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("医考帮备考助手")
        self.root.configure(bg="#f5f6f8")
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"460x680+{max(0, sw - 490)}+60")

        top = tk.Frame(self.root, bg="#f5f6f8")
        top.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(top, text="医考帮备考助手", font=("Microsoft YaHei", 14, "bold"),
                 bg="#f5f6f8").pack(side="left")
        self.count_lbl = tk.Label(top, text="", bg="#f5f6f8", fg="#6b7280",
                                  font=("Microsoft YaHei", 10))
        self.count_lbl.pack(side="right")

        row1 = tk.Frame(self.root, bg="#f5f6f8")
        row1.pack(fill="x", padx=10, pady=2)
        for text, hotkey, action in [
            ("记录 当前题", "F7", "record"),
            ("解析 当前题", "F8", "explain"),
            ("整理", "F9", "aggregate"),
        ]:
            tk.Button(row1, text=f"{text} ({hotkey})", command=self._enqueue(action), width=12,
                      bg="#1a7f64", fg="white", activebackground="#15705a", relief="flat",
                      font=FONT).pack(side="left", padx=3)

        row2 = tk.Frame(self.root, bg="#f5f6f8")
        row2.pack(fill="x", padx=10, pady=2)
        tk.Button(row2, text="保存本讲解", command=self._enqueue("save_explained"), width=11,
                  bg="#e6f4ef", fg="#1a7f64", relief="flat", font=FONT).pack(side="left", padx=3)
        tk.Button(row2, text="打开手册", command=self._enqueue("open_handbook"), width=10,
                  bg="#e6f4ef", fg="#1a7f64", relief="flat", font=FONT).pack(side="left", padx=3)
        tk.Label(row2, text="历史：", bg="#f5f6f8", fg="#6b7280",
                 font=("Microsoft YaHei", 10)).pack(side="left", padx=(6, 0))
        self.hist_box = ttk.Combobox(row2, state="readonly", width=20, font=FONT)
        self.hist_box.pack(side="left", padx=3)
        self.hist_box.bind("<<ComboboxSelected>>", self._on_hist_select)
        self.hist_cnt = tk.Label(row2, text="", bg="#f5f6f8", fg="#6b7280",
                                 font=("Microsoft YaHei", 10))
        self.hist_cnt.pack(side="left", padx=2)

        row3 = tk.Frame(self.root, bg="#f5f6f8")
        row3.pack(fill="x", padx=10, pady=(2, 4))
        tk.Button(row3, text="❓ 使用说明", command=self._open_help, width=14,
                  bg="#f3f4f6", fg="#374151", relief="flat", font=FONT).pack(side="left", padx=3)
        tk.Button(row3, text="⚙ 设置", command=self._open_settings, width=14,
                  bg="#f3f4f6", fg="#374151", relief="flat", font=FONT).pack(side="left", padx=3)

        # 醒目状态行
        self.status_var = tk.StringVar(value="启动中…")
        tk.Label(self.root, textvariable=self.status_var, bg="#1f2328", fg="#7ee2b8",
                 anchor="w", justify="left", wraplength=430,
                 font=("Microsoft YaHei", 11, "bold"), padx=12, pady=8).pack(fill="x", padx=10)

        self.text = scrolledtext.ScrolledText(self.root, wrap="word", font=FONT,
                                              bg="white", fg="#1f2328", relief="flat",
                                              padx=10, pady=8)
        self.text.pack(fill="both", expand=True, padx=10, pady=(8, 4))

        tk.Label(self.root, text="日志", bg="#f5f6f8", fg="#9aa3af",
                 anchor="w", font=("Microsoft YaHei", 9)).pack(fill="x", padx=12)
        self.log = scrolledtext.ScrolledText(self.root, wrap="word", height=6, state="disabled",
                                             bg="#1f2328", fg="#cbd5e1", relief="flat",
                                             font=("Consolas", 9), padx=10, pady=4)
        self.log.pack(fill="x", padx=10, pady=(0, 10))

    # ---------------- 启动信息 ----------------
    def _startup_lines(self) -> list[str]:
        lines = [f"[{_ts()}] 启动：adb {'✅' if self._adb_ready else '❌'}，"
                 f"AI {'✅' if self.client else '❌'}"
                 f"（错题 {self.db.count_questions()} 题）"]
        if not self._adb_ready:
            lines.append(f"[{_ts()}] 提示：{self._adb_err}")
        if not self.client:
            lines.append(f"[{_ts()}] 提示：{self._ai_err}")
        return lines

    def _startup_status(self) -> str:
        if not self._adb_ready:
            return f"adb 未连接：{self._adb_err}（请确认模拟器已启动）"
        if not self.client:
            return f"AI 未就绪：{self._ai_err}（F7 仍可用）"
        return "就绪 ✅ 在题干屏按 F7 记录，按 F8 解析；评论区再按一次 F7 并入评论"

    # ---------------- 线程 / 队列 ----------------
    def _enqueue(self, action: str):
        return lambda: self.work_q.put((action, None))

    def _start_worker(self):
        def loop():
            while True:
                action, _ = self.work_q.get()
                try:
                    getattr(self, f"_do_{action}")()
                except Exception as e:  # noqa: BLE001
                    self._set_status(f"✗ 错误：{e}")
                    self._post_log(f"[{_ts()}] 错误：{e}")
        threading.Thread(target=loop, daemon=True).start()

    def _set_status(self, msg: str):
        self.ui_q.put(("status", msg))

    def _post_log(self, line: str):
        self.ui_q.put(("log", line))

    def _append_text(self, text: str):
        self.ui_q.put(("append", text))

    def _clear_text(self):
        self.ui_q.put(("clear", None))

    def _refresh_count(self):
        self.ui_q.put(("count", self.db.count_questions()))

    # ---------------- 解析历史 ----------------
    def _load_history(self):
        self.hist = self.db.recent_explain_history(limit=100)
        if self.hist:
            self.hist_idx = len(self.hist) - 1
            self.ui_q.put(("hist_refresh", self._hist_labels()))
            self._set_status(f"已载入 {len(self.hist)} 条解析历史")

    def _hist_labels(self) -> list[str]:
        out = []
        for i, h in enumerate(self.hist, 1):
            qid = h.get("question_id") or ""
            stem = (h.get("stem") or "")[:16]
            out.append(f"{i}. {qid} {stem}")
        return out

    def _on_hist_select(self, _event=None):
        sel = self.hist_box.current()
        if sel is None or not (0 <= sel < len(self.hist)):
            return
        self.hist_idx = sel
        h = self.hist[sel]
        self.text.delete("1.0", "end")
        self.text.insert("1.0", f"▍{h.get('question_id') or ''}  {h.get('stem') or ''}\n\n{h.get('content') or ''}")
        self._set_status(f"历史第 {sel + 1}/{len(self.hist)} 条（本讲解如需入错题本，点「保存本讲解」需在题干屏按 F8）")

    def _add_history(self, qid, stem, content):
        self.db.add_explain_history(qid, stem, content)
        self.hist.append({"question_id": qid, "stem": stem, "content": content})
        self.hist_idx = len(self.hist) - 1
        self.ui_q.put(("hist_refresh", self._hist_labels()))

    # ---------------- 动作 ----------------
    def _do_record(self):
        self._set_status("正在记录当前屏幕…")
        ok, msg = self.record_svc.record()
        self._set_status(msg)
        self._post_log(f"[{_ts()}] {msg}")
        self._refresh_count()

    def _do_explain(self):
        if not self.explain_svc:
            self._set_status(self._ai_err or "AI 未就绪")
            return
        if not self._adb_ready:
            self._set_status("adb 未连接，无法解析")
            return
        self._set_status("正在读取屏幕并解析…")
        self._clear_text()
        self.last_explained, self.last_explained_text = None, ""
        for kind, payload in self.explain_svc.explain():
            if kind == "header":
                self._append_text(f"▍ {payload}\n\n")
            elif kind == "token":
                self.last_explained_text += payload
                self._append_text(payload)
            elif kind == "error":
                self._set_status(f"✗ {payload}")
                self._post_log(f"[{_ts()}] ✗ {payload}")
            elif kind == "done":
                self.last_explained = payload
                self._add_history(payload.get("question_id"), payload.get("stem"),
                                  self.last_explained_text.strip())
                self._set_status("讲解完成 ✅ 满意可点「保存本讲解」存入错题本；历史下拉框可回看")
                self._post_log(f"[{_ts()}] 讲解完成：{payload.get('question_id')}")

    def _do_save_explained(self):
        if not self.last_explained:
            self._set_status("请先按 F8 解析一道题，再点保存")
            return
        q = RecordService._screen_to_question(self.last_explained)
        q["ai_explanation"] = self.last_explained_text.strip()
        is_new = self.db.upsert_question(q)
        self._refresh_count()
        msg = f"✅ 已{'新建' if is_new else '并入'}错题：{q.get('question_id') or q['id'][:8]}（含 AI 讲解）"
        self._set_status(msg)
        self._post_log(f"[{_ts()}] {msg}")

    def _do_aggregate(self):
        if not self.aggregate_svc:
            self._set_status(self._ai_err or "AI 未就绪")
            return
        self._set_status("正在整理…（分批调用 AI，请稍候）")
        for kind, payload in self.aggregate_svc.aggregate():
            if kind == "status":
                self._set_status(payload)
                self._post_log(f"[{_ts()}] {payload}")
            elif kind == "error":
                self._set_status(f"✗ {payload}")
                self._post_log(f"[{_ts()}] ✗ {payload}")
            elif kind == "done":
                if payload:
                    self._set_status(payload)
                    self._post_log(f"[{_ts()}] {payload}")
        self._refresh_count()

    def _open_help(self):
        from ui_dialogs import HelpDialog
        HelpDialog(self.root)

    def _open_settings(self):
        from ui_dialogs import SettingsDialog
        SettingsDialog(self.root, self.cfg)

    def _do_open_handbook(self):
        path = os.path.join(self.cfg["data"]["handbook_dir"], "考前速通手册.html")
        if os.path.exists(path):
            os.startfile(path)  # Windows
            self._set_status("已用浏览器打开手册")
            self._post_log(f"[{_ts()}] 打开手册：{path}")
        else:
            self._set_status("手册尚未生成：请先按 F9 整理")
            self._post_log(f"[{_ts()}] 手册不存在，未打开")

    # ---------------- 热键 ----------------
    def _setup_hotkeys(self):
        try:
            import keyboard
        except Exception:  # noqa: BLE001
            self._post_log(f"[{_ts()}] 热键库不可用：请用窗口按钮操作")
            return
        try:
            hk = self.cfg.get("hotkeys", {})
            keyboard.add_hotkey(hk.get("record", "f7"), self._enqueue("record"))
            keyboard.add_hotkey(hk.get("explain", "f8"), self._enqueue("explain"))
            keyboard.add_hotkey(hk.get("aggregate", "f9"), self._enqueue("aggregate"))
            self._post_log(f"[{_ts()}] 热键已注册：F7 记录 / F8 解析 / F9 整理")
            self._post_log(f"[{_ts()}] 若模拟器聚焦时热键无效（MuMu 管理员运行时常见），请用窗口按钮，或以管理员身份运行本程序")
        except Exception as e:  # noqa: BLE001
            self._post_log(f"[{_ts()}] 热键注册失败（可能需管理员权限）：{e}；请用窗口按钮")

    # ---------------- UI 轮询 ----------------
    def _poll_ui(self):
        try:
            while True:
                kind, payload = self.ui_q.get_nowait()
                if kind == "status":
                    self.status_var.set(payload)
                elif kind == "clear":
                    self.text.delete("1.0", "end")
                elif kind == "append":
                    self.text.insert("end", payload)
                    self.text.see("end")
                elif kind == "count":
                    self.count_lbl.config(text=f"错题 {payload}")
                elif kind == "log":
                    self._log_append(payload)
                elif kind == "hist_refresh":
                    labels = payload
                    self.hist_box["values"] = labels
                    if labels:
                        self.hist_box.current(len(labels) - 1)
                        self.hist_cnt.config(text=f"{len(labels)} 条")
        except queue.Empty:
            pass
        self.root.after(80, self._poll_ui)

    def _log_append(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        # 限制日志行数，防无限增长
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > 400:
            self.log.delete("1.0", f"{line_count - 300}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        self.root.mainloop()


def main():
    cfg = load_config()
    App(cfg).run()


if __name__ == "__main__":
    main()
