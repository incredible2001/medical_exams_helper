"""使用说明 + 设置 对话框（面向无编程基础用户）。"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

from core import settings as st

FONT = ("Microsoft YaHei", 11)

HELP_TEXT = """医考帮备考助手 · 使用说明

━━━━━━━━━━━━━━━━━━━━━━
【它是干什么的】
刷题仍在医考帮 App 里做，本工具负责帮你：
  1. 记录错题（连评论区口诀一起）
  2. 一键 AI 讲解不会的题
  3. 一键生成《考前速通手册》（网页版，可打印）

━━━━━━━━━━━━━━━━━━━━━━
【三个核心操作】
● 按 F7 或点「记录 当前题」＝记录错题（两按式）：
    第一步：在题干区（能看到题目文字时）按一次 F7，记录整道题
    第二步：往下滚到评论区，等评论加载完，再按一次 F7，评论并入同一题
● 按 F8 或点「解析 当前题」＝AI 讲解：
    自动读题 → 逐选项分析 → 满意就点「保存本讲解」存进错题本
● 按 F9 或点「整理」＝生成速通手册：
    把错题按 内科/外科/妇儿/基础医学… 分类，生成网页版手册

窗口里所有按钮和快捷键效果一样，用哪个都行。

━━━━━━━━━━━━━━━━━━━━━━
【第一次使用，先点「⚙ 设置」】
① API Key（必填）：粘贴你的 DeepSeek API Key，点保存。
   没有的话去 https://platform.deepseek.com 申请（按用量计费，很便宜）。
② 模拟器 adb（一般不用动）：
   程序会自动找 MuMu 的 adb。如果提示「未找到 adb」，
   点「浏览」选择 MuMu 里的 adb.exe，常见位置：
     C:\\Program Files\\Netease\\MuMu Player 12\\shell\\adb.exe
     D:\\Program Files\\Netease\\MuMu\\nx_device\\12.0\\shell\\adb.exe
   保存后【重启程序】生效。

━━━━━━━━━━━━━━━━━━━━━━
【建议的每日流程】
  打开模拟器 → 医考帮刷题
  → 不会的题：按 F8 讲解
  → 做错/蒙对的题：题干区按 F7 → 滚评论区 → 评论加载完再按 F7
  → 收工前：按 F9 整理（忘了也没关系，下次按 F9 会自动补上）
  → 考前：点「打开手册」看网页版或打印

━━━━━━━━━━━━━━━━━━━━━━
【数据存在哪】
  程序所在文件夹的 data 子文件夹（错题库 + 图片 + 手册）。
  删掉 data 文件夹＝清空错题本，请谨慎。

【常见问题】
  Q：按快捷键没反应？
  A：改用窗口里的按钮；或右键本程序 → 以管理员身份运行。
  Q：AI 讲错了？
  A：AI 偶有出错，一切以教材和医考帮官方解析为准。
  Q：带图的题（心电图/影像/病理切片）？
  A：图会自动存到 data/images 文件夹，AI 只讲文字部分，图请自己看。
"""


class HelpDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("使用说明")
        self.geometry("680x780")
        self.configure(bg="white")
        self.transient(master)
        txt = scrolledtext.ScrolledText(self, wrap="word", font=("Microsoft YaHei", 11),
                                        relief="flat", bg="white", padx=16, pady=10)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", HELP_TEXT)
        txt.configure(state="disabled")


class SettingsDialog(tk.Toplevel):
    def __init__(self, master, cfg: dict):
        super().__init__(master)
        self.title("设置")
        self.geometry("620x470")
        self.configure(bg="#f5f6f8")
        self.transient(master)
        self.cfg = cfg

        body = tk.Frame(self, bg="#f5f6f8")
        body.pack(fill="both", expand=True, padx=18, pady=14)

        # ① API Key
        tk.Label(body, text="① DeepSeek API Key（必填）", font=FONT, bg="#f5f6f8",
                 anchor="w").grid(row=0, column=0, sticky="w", pady=(0, 2))
        key_now = st.get_env_key()
        tk.Label(body, text=f"当前状态：{'已设置 ✅' if key_now else '未设置 ⚠️'}　没有 Key 时 F8/F9 不可用",
                 font=("Microsoft YaHei", 9), fg="#6b7280", bg="#f5f6f8",
                 anchor="w").grid(row=1, column=0, sticky="w")
        self.key_var = tk.StringVar()
        tk.Entry(body, textvariable=self.key_var, show="*", font=FONT,
                 width=48).grid(row=2, column=0, sticky="w", pady=(2, 10))

        # ② adb
        tk.Label(body, text="② 模拟器 adb 路径（一般不用改）", font=FONT, bg="#f5f6f8",
                 anchor="w").grid(row=3, column=0, sticky="w", pady=(0, 2))
        row = tk.Frame(body, bg="#f5f6f8")
        row.grid(row=4, column=0, sticky="w", pady=(2, 2))
        self.adb_var = tk.StringVar(value=st.get_config_value("path"))
        tk.Entry(row, textvariable=self.adb_var, font=("Microsoft YaHei", 10),
                 width=42).pack(side="left")
        tk.Button(row, text="浏览…", command=self._pick_adb, bg="#e6f4ef", fg="#1a7f64",
                  relief="flat").pack(side="left", padx=6)
        tk.Label(body, text="留空＝自动查找。提示「未找到 adb」时才需要选（MuMu 目录的 shell 文件夹里）。",
                 font=("Microsoft YaHei", 9), fg="#6b7280", bg="#f5f6f8",
                 anchor="w").grid(row=5, column=0, sticky="w", pady=(0, 10))

        # ③ 模型
        tk.Label(body, text="③ DeepSeek 模型（可不动）", font=FONT, bg="#f5f6f8",
                 anchor="w").grid(row=6, column=0, sticky="w", pady=(0, 2))
        self.model_var = tk.StringVar(value=st.get_config_value("model") or "deepseek-v4-flash")
        tk.Entry(body, textvariable=self.model_var, font=("Microsoft YaHei", 10),
                 width=48).grid(row=7, column=0, sticky="w", pady=(2, 12))

        btns = tk.Frame(body, bg="#f5f6f8")
        btns.grid(row=8, column=0, sticky="w", pady=(4, 0))
        tk.Button(btns, text="保存全部设置", command=self._save, width=16,
                  bg="#1a7f64", fg="white", relief="flat", font=FONT).pack(side="left")
        self.status_lbl = tk.Label(btns, text="", font=("Microsoft YaHei", 9),
                                   fg="#1a7f64", bg="#f5f6f8")
        self.status_lbl.pack(side="left", padx=12)

    def _pick_adb(self):
        p = filedialog.askopenfilename(title="选择 adb.exe",
                                       filetypes=[("adb", "adb.exe")])
        if p:
            self.adb_var.set(p)

    def _save(self):
        key = self.key_var.get().strip()
        if key:
            st.save_env_key(key)
        adb = self.adb_var.get().strip()
        if adb != st.get_config_value("path"):
            st.set_config_value("path", adb)
        model = self.model_var.get().strip()
        if model and model != st.get_config_value("model"):
            st.set_config_value("model", model)
        self.status_lbl.config(text="✅ 已保存")
        messagebox.showinfo("已保存",
                            "设置已保存。\n请关闭程序后重新双击启动，即可生效。",
                            parent=self)
