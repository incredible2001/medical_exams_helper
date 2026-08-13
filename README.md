# 医考帮备考助手 (medical_exams_helper)

面向执业医师笔试的**备考辅助工具**：刷题仍在医考帮完成，本工具负责——
「不会的题一键 AI 讲解」+「错题收集」+「生成考前速通手册」。

> ⚠️ **定位说明**：本工具**不做自动刷题/自动点击**。你手动刷题，工具只负责记录与讲解。
> 题目与评论会被发送至 **DeepSeek API** 处理；你的个人数据（错题库、手册）仅存本地。

---

## ✨ 功能一览

| 按键 | 功能 | 说明 |
|---|---|---|
| **F7** | 记录当前题目 | **两按式**：题干区按一次记录全题；滚到评论区再按一次，评论与解析并入同一题 |
| **F8** | AI 讲解当前题目 | 读取题干+选项 → DeepSeek 流式**逐选项分析**（考点/逐选项/易错点/记忆锚点），可点「保存本讲解」入库 |
| **F9** | 整理生成速通手册 | 增量分批处理新错题 → 按 7 大临床系统归类 → 生成 `data/速通手册/<分组>.md` + 合并版 `考前速通手册.html`（目录/折叠/打印） |

侧边窗（放在模拟器旁）内所有功能均有对应按钮，不依赖键盘。

## 🚀 快速开始

### 使用方式 A：直接使用发布版（无需 Python）

从 **GitHub Releases** 页面下载最新 `医考帮备考助手-vX.X.X.zip`：

1. 打开仓库 → 右侧 **Releases** 标签页
2. 下载最新版本的 zip 压缩包
3. 解压后双击 `医考帮备考助手.exe`
4. 首次使用点窗口「⚙ 设置」填入你的 DeepSeek API Key；找不到 adb 时按提示选择 MuMu 的 `adb.exe`

> 若 Windows 弹出"已保护你的电脑"提示，点击「更多信息」→「仍要运行」。

### 使用方式 B：从源码运行（需要 Python）

1. 安装 [Python 3.11+](https://www.python.org/downloads/)（勾选 *Add python.exe to PATH*）
2. 双击 **`install.bat`** 一键安装依赖
3. 双击 **`启动备考助手.bat`** 启动

> 开发者打包：运行 `build_exe.bat` 生成 `dist\医考帮备考助手.exe`。

### 环境要求
- Windows + [MuMu 模拟器 12](https://www.mumuplayer.com/)（或其他可 adb 连接的安卓模拟器）
- 医考帮 App（答题模式下）

### 配置
1. **密钥**：复制 `.env.example` 为 `.env`，填入你的 DeepSeek API Key：
   ```
   DEEPSEEK_API_KEY=sk-xxxx
   ```
   （`.env` 已被 gitignore，不会提交。也可用系统环境变量代替。）
2. **adb**（通常无需配置）：工具会自动探测。若找不到，在 `config.toml` 的 `[adb] path` 填你的 `adb.exe` 路径，端口填模拟器端口（MuMu 12 默认 `16384`）。

### 使用流程（两按式）
```
遇到不懂的题  → F8 看 AI 逐选项讲解（满意可点「保存本讲解」）
做错/蒙对存疑 → 题干区按 F7 → 看评论区 → 评论加载完再按 F7（评论并入）
收工          → F9 → 手册自动更新
```

## 📁 数据与输出

```
data/                    # 个人数据（已 gitignore，不入库）
├── medical_notes.db     # SQLite：错题 / 评论 / AI解析 / 整理状态 / 解析历史
└── 速通手册/
    ├── 基础医学.md …    # 分组 markdown
    └── 考前速通手册.html # 合并版（浏览器打开，可打印）
```

**存储与占用**：所有中间数据都在 `data/` 目录，不产生散落的临时文件。SQLite 数据库很小（几 MB 内），adb 在模拟器内反复覆写同一个临时文件（约 50 KB），不累积。清理时删除 `data/` 即可（删除前注意备份）。

## 🗂 手册分组（可改）

`taxonomy.json` 定义 7 大分组及其医考帮学科归属，可直接编辑调整。

## ⚙️ 配置

`config.toml`：adb 路径/端口、三个快捷键、DeepSeek 模型、分批大小、合并窗口等，均可在不改代码的前提下调整。模型默认 `deepseek-v4-flash`。

## 🔒 安全与隐私

- API Key 只存 `.env` / 环境变量，代码不记录、不打印。
- `data/` 含医考帮真题内容（受版权保护），整体 gitignore，**个人数据不进入仓库**。
- 开源仓库仅含代码 + 示例配置 + 文档。

## 📦 项目结构

```
main.py / app.py         入口 + tkinter 侧边窗
ui_dialogs.py            使用说明 / 设置 对话框
core/
├── adb.py               adb 自动发现 / dump / 截图
├── screen_parser.py     uiautomator 解析（题干/选项/对错/评论）
├── db.py                SQLite 数据层
├── deepseek_client.py   DeepSeek 客户端 + 讲解 prompt
├── record_service.py    F7 两按式记录 + 评论匹配
├── explain_service.py   F8 流式讲解
├── aggregate_service.py F9 增量整理
├── renderer.py          速通手册 md + HTML
├── settings.py          设置读写（.env / config.toml）
└── config.py            配置加载
scripts/test_explain.py  命令行实测（单题讲解）
```

## 免责声明
本工具仅作个人学习辅助，不替代官方教材与备考课程。AI 讲解可能存在错误，请以教材/官方解析为准。
