"""adb 封装：自动发现 adb、连接 MuMu、uiautomator dump、截屏。"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

# 打包为 exe（--windowed 无控制台）时，子进程 adb 会弹黑色控制台窗口。
# 加 CREATE_NO_WINDOW 让子进程不创建新窗口。（仅在 Windows 上有效）
if sys.platform == "win32":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    _NO_WINDOW = 0

# MuMu 12 常见安装路径（覆盖官方默认 + 用户实测路径）
_MUMU_ADB_CANDIDATES = [
    "C:/Program Files/Netease/MuMu Player 12/shell/adb.exe",
    "C:/Program Files/Netease/MuMuPlayer-12.0/shell/adb.exe",
    "C:/Program Files/MuMuPlayer 12/shell/adb.exe",
    "D:/Program Files/Netease/MuMu/nx_device/12.0/shell/adb.exe",
]

# 常见模拟器 adb 端口
_DEFAULT_PORTS = [16384, 7555, 5555]


def find_adb(explicit: str | None = None) -> str:
    """返回 adb 可执行文件路径；找不到返回空串。"""
    if explicit and Path(explicit).exists():
        return explicit
    # 环境变量
    for env in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        root = os.environ.get(env, "")
        if root:
            cand = Path(root) / "platform-tools" / "adb.exe"
            if cand.exists():
                return str(cand)
    # 常见 MuMu 路径
    for cand in _MUMU_ADB_CANDIDATES:
        if Path(cand).exists():
            return cand
    # MuMuPlayer 各版本（12/15 等）通用目录：MuMuPlayer*/nx_device/*/shell/adb.exe
    for base in ("C:/Program Files", "C:/Program Files (x86)", "D:/", "E:/"):
        try:
            hits = sorted(Path(base).glob("MuMuPlayer*/nx_device/*/shell/adb.exe"))
        except OSError:
            continue
        if hits:
            return str(hits[0])
    # PATH 中的 adb
    try:
        which = subprocess.run(
            ["where", "adb"], capture_output=True, text=True, shell=False,
            creationflags=_NO_WINDOW,
        )
        if which.returncode == 0 and which.stdout.strip():
            return which.stdout.strip().splitlines()[0]
    except OSError:
        pass
    return ""


class AdbError(Exception):
    pass


class Adb:
    """连接模拟器的 adb 句柄。"""

    def __init__(self, adb_path: str | None = None, host: str = "127.0.0.1", port: int | None = None):
        self.adb_path = find_adb(adb_path)
        if not self.adb_path:
            raise AdbError("未找到 adb。请确认已安装 MuMu/Android SDK，或在 config.toml 的 [adb] 中指定 path。")
        self.host = host
        self.port = port
        self._serial: str | None = None

    # ---------- 基础命令 ----------
    def _run(self, args: list[str], timeout: int = 15, check: bool = True) -> str:
        cmd = [self.adb_path] + args
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8",
                errors="replace", creationflags=_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as e:
            raise AdbError(f"adb 命令超时: {' '.join(args)}") from e
        if check and proc.returncode != 0:
            raise AdbError(f"adb 命令失败 [{proc.returncode}]: {' '.join(args)}\n{proc.stderr.strip()}")
        return proc.stdout

    def _run_serial(self, args: list[str], timeout: int = 15, check: bool = True) -> str:
        serial = self.ensure_serial()
        try:
            return self._run(["-s", serial] + args, timeout=timeout, check=check)
        except AdbError as e:
            # MuMu adb 偶发掉线（device offline）→ 重连后重试一次
            if "offline" in str(e) or "not found" in str(e).lower():
                self._serial = None
                serial = self.ensure_serial()
                return self._run(["-s", serial] + args, timeout=timeout, check=check)
            raise

    # ---------- 连接 ----------
    def connect(self, port: int | None = None) -> str:
        """尝试连接本机模拟器，返回已连接的设备序列号。"""
        self.port = port or self.port
        candidates = [self.port] if self.port else _DEFAULT_PORTS
        for p in candidates:
            try:
                out = self._run(["connect", f"{self.host}:{p}"])
                if "connected" in out.lower() or "already" in out.lower():
                    self.port = p
                    self._serial = f"{self.host}:{p}"
                    return self._serial
            except AdbError:
                continue
        # 兜底：可能已由模拟器自动注册（如 emulator-5554）
        for serial in self.devices():
            if serial:
                self._serial = serial
                return serial
        raise AdbError("无法连接模拟器。请确认 MuMu 已启动且保持 adb 调试开启。")

    def devices(self) -> list[str]:
        try:
            out = self._run(["devices"])
        except AdbError:
            return []
        return [line.split("\t")[0] for line in out.splitlines()[1:] if "\tdevice" in line]

    def ensure_serial(self) -> str:
        if not self._serial:
            try:
                self._serial = self.connect()
            except AdbError:
                raise
        return self._serial

    # ---------- 屏幕 ----------
    def screencap_png(self) -> bytes:
        """返回当前屏幕 PNG 字节。"""
        self.ensure_serial()
        cmd = [self.adb_path, "-s", self._serial, "exec-out", "screencap", "-p"]
        proc = subprocess.run(cmd, capture_output=True, timeout=20, creationflags=_NO_WINDOW)
        if proc.returncode != 0 or not proc.stdout:
            raise AdbError("截屏失败。")
        return proc.stdout

    def dump_ui_xml(self) -> str:
        """执行 uiautomator dump 并返回界面 XML 文本。

        重要：MuMu 15 / Android 15 (x86_64) 上 uiautomator dump 会「文件写好后、
        退出关停线程时」段错误，导致退出码 139（SIGSEGV）——但 XML 产物是好的。
        因此这里不以退出码判断成败，而是按「文件是否写出了有效 XML」判断；
        失败时再按「普通 → --compressed」轮换 + 间隔重试。
        """
        plans = [
            ["shell", "uiautomator", "dump", "/sdcard/yk_dump.xml"],
            ["shell", "uiautomator", "dump", "--compressed", "/sdcard/yk_dump.xml"],
            ["shell", "uiautomator", "dump", "/sdcard/yk_dump.xml"],
            ["shell", "uiautomator", "dump", "--compressed", "/sdcard/yk_dump.xml"],
        ]
        last_err: Exception | None = None
        for i, args in enumerate(plans):
            if i > 0:
                time.sleep(0.8)
            try:
                self.ensure_serial()
                # 先删旧文件：只接受本次 dump 新写出的 XML，避免读到上一次残留
                self._run_serial(["shell", "rm", "-f", "/sdcard/yk_dump.xml"], check=False, timeout=5)
                # dump 不检查退出码：Android 15 上可能「写成功但退出段错误(139)」
                self._run_serial(args, check=False)
                xml = self._run_serial(["exec-out", "cat", "/sdcard/yk_dump.xml"])
                if "<" in xml[:200]:
                    return xml
            except AdbError as e:
                last_err = e
                continue
        devs = "、".join(self.devices()) or "（无）"
        detail = str(last_err) if last_err else "dump 无有效输出（未拿到界面 XML）"
        raise AdbError(
            f"uiautomator dump 失败: {detail}\n"
            f"当前 adb 设备：{devs}\n"
            "提示：uiautomator 在 Android 15 模拟器上可能「文件写好了但退出时崩溃(139)」；"
            "本工具已按文件内容判断成败。若仍失败，请确认模拟器未最小化/挂起、屏幕未锁屏，"
            "必要时重启模拟器再试。"
        )

    def extract_image_bounds(self, xml: str) -> list[tuple[int, int, int, int]]:
        """从 dump XML 中找出题干区域附近的 ImageView 控件边界 (l,t,r,b)。"""
        bounds = []
        # 简单启发：取所有 ImageView 的 bounds，后续在 parser 里按区域过滤
        for m in re.finditer(r'class="android\.widget\.ImageView"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml):
            l, t, r, b = (int(g) for g in m.groups())
            if r - l > 40 and b - t > 40:  # 过滤图标类小图
                bounds.append((l, t, r, b))
        return bounds
