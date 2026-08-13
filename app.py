"""医考帮备考助手：tkinter 侧边窗 + 全局热键 + 后台工作线程。"""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import scrolledtext

from dotenv import load_dotenv

load_dotenv()

from core.adb import Adb, AdbError  # noqa: E402
from core.aggregate_service import AggregateService  # noqa: E402
from core.config import load_config  # noqa: E402
from core.db import DB  # noqa: E402
from core.deepseek_client import DeepSeekClient, DeepSeekError  # noqa: E402
from core.explain_service import ExplainService  # noqa: E402
from core.record_service import RecordService  # noqa: E402

FONT = ("Microsoft YaHei", 11)


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

        self.last_explained = None
        self.last_explained_text = ""

        self.work_q: queue.Queue = queue.Queue()
        self.ui_q: queue.Queue = queue.Queue()

        self._build_ui()
        self._start_worker()
        self._setup_hotkeys()

        self._refresh_count()
        self._post_status(self._startup_status())
        self.root.after(80, self._poll_ui)

    # ---------------- UI ----------------
    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("医考帮备考助手")
        self.root.configure(bg="#f5f6f8")
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"440x620+{max(0, sw - 470)}+80")

        top = tk.Frame(self.root, bg="#f5f6f8")
        top.pack(fill="x", padx=10, pady=(10, 2))
        tk.Label(top, text="医考帮备考助手", font=("Microsoft YaHei", 14, "bold"),
                 bg="#f5f6f8").pack(side="left")

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
        tk.Button(row2, text="保存本讲解", command=self._enqueue("save_explained"), width=12,
                  bg="#e6f4ef", fg="#1a7f64", relief="flat", font=FONT).pack(side="left", padx=3)
        tk.Button(row2, text="打开手册", command=self._enqueue("open_handbook"), width=12,
                  bg="#e6f4ef", fg="#1a7f64", relief="flat", font=FONT).pack(side="left", padx=3)
        self.count_lbl = tk.Label(row2, text="", bg="#f5f6f8", fg="#6b7280",
                                  font=("Microsoft YaHei", 10))
        self.count_lbl.pack(side="right", padx=6)

        self.text = scrolledtext.ScrolledText(self.root, wrap="word", font=FONT,
                                              bg="white", fg="#1f2328", relief="flat",
                                              padx=10, pady=8)
        self.text.pack(fill="both", expand=True, padx=10, pady=6)

        self.status_var = tk.StringVar(value="正在启动…")
        tk.Label(self.root, textvariable=self.status_var, bg="#1f2328", fg="#d1d5db",
                 anchor="w", font=("Microsoft YaHei", 10), padx=12, pady=6).pack(fill="x")

    def _startup_status(self) -> str:
        msgs = []
        if not self._adb_ready:
            msgs.append(f"adb 未连接：{self._adb_err}")
        if self._ai_err:
            msgs.append(f"AI 未就绪：{self._ai_err}（F7 仍可用）")
        return "；".join(msgs) if msgs else "就绪 ✅"

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
                    self._post_status(f"错误：{e}")
        threading.Thread(target=loop, daemon=True).start()

    def _post_status(self, msg: str):
        self.ui_q.put(("status", msg))

    def _append_text(self, text: str):
        self.ui_q.put(("append", text))

    def _clear_text(self):
        self.ui_q.put(("clear", None))

    def _refresh_count(self):
        self.ui_q.put(("count", self.db.count_questions()))

    # ---------------- 动作 ----------------
    def _do_record(self):
        ok, msg = self.record_svc.record()
        self._post_status(msg)
        self._refresh_count()

    def _do_explain(self):
        if not self.explain_svc:
            self._post_status(self._ai_err or "AI 未就绪")
            return
        if not self._adb_ready:
            self._post_status("adb 未连接，无法解析")
            return
        self._clear_text()
        self.last_explained, self.last_explained_text = None, ""
        for kind, payload in self.explain_svc.explain():
            if kind == "header":
                self._append_text(f"▍{payload}\n\n")
            elif kind == "token":
                self.last_explained_text += payload
                self._append_text(payload)
            elif kind == "error":
                self._post_status(f"✗ {payload}")
            elif kind == "done":
                self.last_explained = payload
                self._post_status("讲解完成 ✅ 满意可点「保存本讲解」")

    def _do_save_explained(self):
        if not self.last_explained:
            self._post_status("请先按 F8 解析一道题，再点保存")
            return
        q = RecordService._screen_to_question(self.last_explained)
        q["ai_explanation"] = self.last_explained_text.strip()
        is_new = self.db.upsert_question(q)
        self._refresh_count()
        self._post_status(f"✅ 已{'新建' if is_new else '并入'}错题："
                          f"{q.get('question_id') or q['id'][:8]}（含 AI 讲解）")

    def _do_aggregate(self):
        if not self.aggregate_svc:
            self._post_status(self._ai_err or "AI 未就绪")
            return
        for kind, payload in self.aggregate_svc.aggregate():
            if kind == "status":
                self._post_status(payload)
            elif kind == "error":
                self._post_status(f"✗ {payload}")
            elif kind == "done":
                self._post_status(payload)
        self._refresh_count()

    def _do_open_handbook(self):
        path = os.path.join(self.cfg["data"]["handbook_dir"], "考前速通手册.html")
        if os.path.exists(path):
            os.startfile(path)  # Windows
        else:
            self._post_status("手册尚未生成：请先按 F9 整理")

    # ---------------- 热键 ----------------
    def _setup_hotkeys(self):
        try:
            import keyboard
        except Exception:  # noqa: BLE001
            self._post_status("热键库不可用，请用窗口按钮操作")
            return
        try:
            hk = self.cfg.get("hotkeys", {})
            keyboard.add_hotkey(hk.get("record", "f7"), self._enqueue("record"))
            keyboard.add_hotkey(hk.get("explain", "f8"), self._enqueue("explain"))
            keyboard.add_hotkey(hk.get("aggregate", "f9"), self._enqueue("aggregate"))
        except Exception as e:  # noqa: BLE001
            self._post_status(f"热键注册失败（可能需管理员权限）：{e}；请用窗口按钮")

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
                    self.count_lbl.config(text=f"已记录 {payload} 题")
        except queue.Empty:
            pass
        self.root.after(80, self._poll_ui)

    def run(self):
        self.root.mainloop()


def main():
    cfg = load_config()
    App(cfg).run()


if __name__ == "__main__":
    main()
