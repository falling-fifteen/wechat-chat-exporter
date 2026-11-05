"""Tkinter desktop UI for wechat-chat-exporter.

Run with ``wce gui``.  The GUI is a thin layer over the same library used by
the CLI: it never extracts keys and never opens a network socket.

Information architecture:

* one help entry (``使用说明 / Q&A``) that contains every explanation;
* step 1 data + key, step 2 conversation selection, step 3 export;
* a collapsible log panel, hidden by default.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .crypto.key_source import load_image_key, load_key, validate_key_hex
from .db.contacts import ContactResolver
from .db.decrypt import DecryptedLayout, decrypt_layout, make_work_dir
from .db.discovery import DataLayout, find_layout
from .db.repository import MessageRepository
from .export.naming import sanitize
from .export.runner import export_session
from .media.index import ImageIndex
from .media.resolver import ImageResolver
from .model.session import Session

GUI_FORMATS = ("csv", "xlsx", "html", "pdf", "docx")


class ExportApp:
    def __init__(self, root: tk.Tk, config: dict | None = None) -> None:
        self.root = root
        self.root.title(f"wechat-chat-exporter v{__version__}")
        self.root.minsize(900, 680)

        self.config_data = config or {}
        self.layout: DataLayout | None = None
        self.decrypted: DecryptedLayout | None = None
        self.work_dir: Path | None = None
        self.repo: MessageRepository | None = None
        self.sessions: dict[str, Session] = {}
        self.all_sessions: list[tuple[Session, int]] = []
        self.visible_count = 0
        self._filter_after_id: str | None = None
        self.busy = False
        self.log_visible = False
        self.closing = False
        self.cancel_event = threading.Event()
        self._faq_window: tk.Toplevel | None = None
        self.data_widgets: list[ttk.Widget] = []

        self.db_var = tk.StringVar(value=str(self.config_data.get("db_dir", "")))
        self.key_var = tk.StringVar(value=str(self.config_data.get("key_file", "")))
        self.paste_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.key_mode_var = tk.StringVar(value="file" if self.key_var.get() else "paste")
        self.out_var = tk.StringVar(
            value=str(self.config_data.get("out", str(Path.home() / "wce-exports")))
        )
        limit = self.config_data.get("limit")
        self.limit_var = tk.StringVar(value="" if limit is None else str(limit))
        self.search_var = tk.StringVar()
        self.selected_var = tk.StringVar(value="已选 0 / 共 0")
        self.status_var = tk.StringVar(value="第一次使用？点右上角「使用说明 / Q&A」")

        configured = {
            part.strip().lower()
            for part in str(self.config_data.get("formats", "")).split(",")
            if part.strip()
        } & set(GUI_FORMATS)
        self.formats = {
            name: tk.BooleanVar(
                value=(name in configured) if configured else name in ("csv", "html")
            )
            for name in GUI_FORMATS
        }
        self.image_key_file = str(self.config_data.get("image_key_file", ""))

        self._build()
        self._center(1000, 760)
        self._bind_shortcuts()
        self._toggle_key_mode()
        self._update_actions()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=12, pady=(10, 0))
        ttk.Label(
            header,
            text="wechat-chat-exporter",
            font=("Microsoft YaHei", 15, "bold"),
        ).pack(side=tk.LEFT)
        ttk.Label(header, text=f"v{__version__}", foreground="#888").pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(header, text="使用说明 / Q&A", command=self._show_faq).pack(side=tk.RIGHT)

        self._build_data_section()
        self._build_session_section()
        self._build_export_section()

        status = ttk.Frame(self.root)
        status.pack(fill=tk.X, padx=12, pady=(6, 0))
        self.progress = ttk.Progressbar(status, mode="indeterminate")
        self.progress.pack(fill=tk.X)
        self.status_label = ttk.Label(
            status, textvariable=self.status_var, anchor="w", foreground="#555"
        )
        self.status_label.pack(fill=tk.X, pady=(4, 0))
        self.progress.pack_forget()

        self.log_toggle_btn = ttk.Button(self.root, text="显示日志", command=self._toggle_log)
        self.log_toggle_btn.pack(anchor="w", padx=12, pady=(2, 0))

        self.log_frame = ttk.Frame(self.root)
        self.log = tk.Text(self.log_frame, height=7, state=tk.DISABLED, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(self.log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _build_data_section(self) -> None:
        box = ttk.LabelFrame(self.root, text="① 数据与密钥", padding=10)
        box.pack(fill=tk.X, padx=12, pady=(10, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="数据目录", width=10).grid(row=0, column=0, sticky="w", pady=3)
        db_entry = ttk.Entry(box, textvariable=self.db_var)
        db_entry.grid(row=0, column=1, sticky="ew", pady=3)
        db_buttons = ttk.Frame(box)
        db_buttons.grid(row=0, column=2, sticky="w", padx=(6, 0))
        browse_db = ttk.Button(db_buttons, text="浏览", command=self._pick_db, width=6)
        browse_db.pack(side=tk.LEFT)
        auto_find = ttk.Button(db_buttons, text="自动查找", command=self._auto_find_db, width=8)
        auto_find.pack(side=tk.LEFT, padx=(4, 0))

        ttk.Label(box, text="密钥来源", width=10).grid(row=1, column=0, sticky="w", pady=3)
        key_modes = ttk.Frame(box)
        key_modes.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
        radio_file = ttk.Radiobutton(
            key_modes,
            text="密钥文件",
            value="file",
            variable=self.key_mode_var,
            command=self._toggle_key_mode,
        )
        radio_file.pack(side=tk.LEFT)
        radio_paste = ttk.Radiobutton(
            key_modes,
            text="直接粘贴",
            value="paste",
            variable=self.key_mode_var,
            command=self._toggle_key_mode,
        )
        radio_paste.pack(side=tk.LEFT, padx=(16, 0))

        self.key_stack = ttk.Frame(box)
        self.key_stack.grid(row=2, column=1, columnspan=2, sticky="ew", pady=3)
        self.key_stack.columnconfigure(0, weight=1)

        self.key_file_frame = ttk.Frame(self.key_stack)
        self.key_file_frame.grid(row=0, column=0, sticky="ew")
        self.key_file_frame.columnconfigure(0, weight=1)
        key_file_entry = ttk.Entry(self.key_file_frame, textvariable=self.key_var)
        key_file_entry.grid(row=0, column=0, sticky="ew")
        browse_key = ttk.Button(self.key_file_frame, text="浏览", command=self._pick_key, width=6)
        browse_key.grid(row=0, column=1, padx=(6, 0))

        self.key_paste_frame = ttk.Frame(self.key_stack)
        self.key_paste_frame.grid(row=0, column=0, sticky="ew")
        self.key_paste_frame.columnconfigure(0, weight=1)
        self.key_entry = ttk.Entry(self.key_paste_frame, textvariable=self.paste_var, show="•")
        self.key_entry.grid(row=0, column=0, sticky="ew")
        show_key_check = ttk.Checkbutton(
            self.key_paste_frame,
            text="显示",
            variable=self.show_key_var,
            command=self._toggle_key,
        )
        show_key_check.grid(row=0, column=1, padx=(6, 0))

        ttk.Label(box, text="输出目录", width=10).grid(row=3, column=0, sticky="w", pady=3)
        out_entry = ttk.Entry(box, textvariable=self.out_var)
        out_entry.grid(row=3, column=1, sticky="ew", pady=3)
        browse_out = ttk.Button(box, text="浏览", command=self._pick_out, width=6)
        browse_out.grid(row=3, column=2, sticky="w", padx=(6, 0))

        self.data_widgets = [
            db_entry,
            browse_db,
            auto_find,
            radio_file,
            radio_paste,
            key_file_entry,
            self.key_entry,
            show_key_check,
            browse_key,
            out_entry,
            browse_out,
        ]

    def _build_session_section(self) -> None:
        box = ttk.LabelFrame(self.root, text="② 选择会话", padding=10)
        box.pack(fill=tk.BOTH, expand=True, padx=12, pady=(8, 0))

        toolbar = ttk.Frame(box)
        toolbar.pack(fill=tk.X, pady=(0, 6))
        self.load_btn = ttk.Button(
            toolbar, text="读取会话", command=self.load_sessions, state=tk.DISABLED
        )
        self.load_btn.pack(side=tk.LEFT)
        ttk.Label(toolbar, text="搜索").pack(side=tk.LEFT, padx=(12, 4))
        self.search_entry = ttk.Entry(toolbar, textvariable=self.search_var, width=24)
        self.search_entry.pack(side=tk.LEFT)
        ttk.Button(toolbar, text="全选", command=self._select_all, width=6).pack(
            side=tk.LEFT, padx=(8, 2)
        )
        ttk.Button(toolbar, text="清空", command=self._clear_selection, width=6).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Label(toolbar, textvariable=self.selected_var).pack(side=tk.RIGHT)

        tree_frame = ttk.Frame(box)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = ("name", "count", "kind")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("name", text="会话")
        self.tree.heading("count", text="条数")
        self.tree.heading("kind", text="类型")
        self.tree.column("name", width=560)
        self.tree.column("count", width=100, anchor="e")
        self.tree.column("kind", width=80, anchor="center")
        vscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        hscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vscroll.set, xscrollcommand=hscroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vscroll.grid(row=0, column=1, sticky="ns")
        hscroll.grid(row=1, column=0, sticky="ew")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._update_selection_state())
        self.tree.bind("<Control-a>", self._select_all_event)
        self.search_var.trace_add("write", self._on_search_changed)

    def _build_export_section(self) -> None:
        box = ttk.LabelFrame(self.root, text="③ 导出", padding=10)
        box.pack(fill=tk.X, padx=12, pady=(8, 0))
        box.columnconfigure(1, weight=1)

        ttk.Label(box, text="导出格式", width=10).grid(row=0, column=0, sticky="w")
        format_frame = ttk.Frame(box)
        format_frame.grid(row=0, column=1, columnspan=2, sticky="w")
        for name, var in self.formats.items():
            check = ttk.Checkbutton(
                format_frame,
                text=name.upper(),
                variable=var,
                command=self._update_actions,
            )
            check.pack(side=tk.LEFT, padx=3)
            self.data_widgets.append(check)

        ttk.Label(box, text="最新条数", width=10).grid(row=1, column=0, sticky="w", pady=3)
        limit_row = ttk.Frame(box)
        limit_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=3)
        self.limit_entry = ttk.Entry(limit_row, textvariable=self.limit_var, width=12)
        self.limit_entry.pack(side=tk.LEFT)
        ttk.Label(limit_row, text="条（留空=全部；例如 5000 只导最新 5000 条）").pack(
            side=tk.LEFT, padx=(6, 0)
        )

        actions = ttk.Frame(box)
        actions.grid(row=2, column=0, columnspan=3, sticky="e", pady=(4, 0))
        self.open_btn = ttk.Button(actions, text="打开输出目录", command=self.open_output)
        self.open_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.export_btn = ttk.Button(
            actions,
            text="开始导出",
            command=self.start_export,
            style="Primary.TButton",
            state=tk.DISABLED,
        )
        self.export_btn.pack(side=tk.LEFT)

    def _center(self, width: int, height: int) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(0, (screen_w - width) // 2)
        y = max(0, (screen_h - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<F1>", lambda _e: self._show_faq())
        self.root.bind("<F5>", lambda _e: self.load_sessions())
        self.root.bind("<Control-Return>", lambda _e: self.start_export())

    # --------------------------------------------------------------- pickers
    def _pick_db(self) -> None:
        path = filedialog.askdirectory(title="选择 db_storage 或其上级目录")
        if path:
            self.db_var.set(path)

    def _pick_key(self) -> None:
        path = filedialog.askopenfilename(title="选择包含 64 位密钥的文件")
        if path:
            self.key_var.set(path)

    def _pick_out(self) -> None:
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.out_var.set(path)

    def _toggle_key(self) -> None:
        self.key_entry.configure(show="" if self.show_key_var.get() else "•")

    def _toggle_key_mode(self) -> None:
        if self.key_mode_var.get() == "file":
            self.key_paste_frame.grid_remove()
            self.key_file_frame.grid()
        else:
            self.key_file_frame.grid_remove()
            self.key_paste_frame.grid()
        self._update_actions()

    def _auto_find_db(self) -> None:
        found = self._find_db_candidates()
        if len(found) == 1:
            self.db_var.set(str(found[0]))
            self._set_status("已自动找到数据目录，请确认后读取会话")
        elif found:
            listing = "\n".join(str(path) for path in found[:10])
            messagebox.showinfo(
                "找到多个数据目录",
                "找到多个微信账号目录，请手动选择其中一个：\n\n" + listing,
            )
        else:
            messagebox.showinfo(
                "没有找到",
                "没有在常见位置找到 db_storage。\n\n"
                "请打开微信：左下角 设置 → 文件管理 → 打开文件夹，"
                "进入 xwechat_files 后选择 wxid_ 开头的账号目录。\n"
                "更多说明见「使用说明 / Q&A」→「数据目录」。",
            )

    @staticmethod
    def _find_db_candidates() -> list[Path]:
        home = Path.home()
        roots = [
            home / "Documents" / "xwechat_files",
            home / "Documents" / "WeChat Files",
            home / "OneDrive" / "Documents" / "xwechat_files",
            home / "OneDrive" / "Documents" / "WeChat Files",
        ]
        for drive in "CDEFGH":
            roots.append(Path(f"{drive}:/WeChat Files/xwechat_files"))
            roots.append(Path(f"{drive}:/WeChat Files/WeChat Files"))
            roots.append(Path(f"{drive}:/xwechat_files"))
        found: list[Path] = []
        for candidate in roots:
            if not candidate.is_dir():
                continue
            if (candidate / "db_storage").is_dir() and candidate not in found:
                found.append(candidate)
            try:
                for child in candidate.iterdir():
                    if child.is_dir() and (child / "db_storage").is_dir() and child not in found:
                        found.append(child)
            except OSError:
                continue
        return found

    # --------------------------------------------------------------- help
    def _show_faq(self) -> None:
        if self._faq_window is not None and self._faq_window.winfo_exists():
            self._faq_window.lift()
            self._faq_window.focus_set()
            return
        win = tk.Toplevel(self.root)
        win.title("使用说明 / Q&A")
        win.geometry("840x680")
        win.minsize(640, 480)
        win.transient(self.root)
        notebook = ttk.Notebook(win)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        for title, body in self._help_sections():
            self._add_help_tab(notebook, title, body)
        self._faq_window = win
        win.protocol("WM_DELETE_WINDOW", self._close_faq)

    def _close_faq(self) -> None:
        if self._faq_window is not None:
            self._faq_window.destroy()
            self._faq_window = None

    @staticmethod
    def _add_help_tab(notebook: ttk.Notebook, title: str, body: str) -> None:
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=title)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Text(
            frame,
            wrap=tk.WORD,
            padx=10,
            pady=8,
            font=("Microsoft YaHei", 10),
            spacing1=2,
            spacing3=6,
        )
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        text.insert("1.0", body)
        text.configure(state=tk.DISABLED)

    @staticmethod
    def _help_sections() -> list[tuple[str, str]]:
        return [
            (
                "快速开始",
                f"""wechat-chat-exporter v{__version__}

【支持版本】
- Windows 11 + 微信 4.2.0.11：已完整验证
- 其他微信 4.x：尽力兼容
- 微信 3.x：不支持
- 微信升级后数据库结构可能变化；读取失败时先看下方日志

【六步操作】
1. 选择微信数据目录（db_storage 或它上一级的 wxid_ 文件夹）
2. 选择密钥文件，或切到「直接粘贴」输入 64 位密钥
3. 选择输出目录
4. 点「读取会话」，等待解密和统计完成
5. 在列表中搜索/多选会话，勾选导出格式
   （全选只作用于当前搜索结果；Ctrl+A 也可全选）
6. 点「开始导出」，完成后可点「打开输出目录」

快捷键：F1 打开说明，F5 读取会话，Ctrl+Enter 开始导出。
""",
            ),
            (
                "数据目录",
                """【微信数据目录是什么】
微信把聊天记录、联系人、图片等存在一个叫 db_storage 的文件夹里。
本工具读取的是这个文件夹里的加密数据库副本，不会修改原文件。

【通常在哪里】
默认路径类似：
  文档\\xwechat_files\\<你的wxid>\\db_storage

【怎么找到】
1. 打开微信电脑版
2. 左下角 设置 → 文件管理 → 打开文件夹
3. 进入 xwechat_files
4. 里面通常有一个 wxid_ 开头的账号文件夹
5. 进入后可以看到 db_storage

【在本工具里选哪个】
- 选 db_storage 文件夹本身，可以
- 选它上一级的 wxid_ 文件夹，也可以
- 也可以点「自动查找」，工具会扫描文档、OneDrive 和各盘常见位置

如果你改过微信的存储位置，以 设置 → 文件管理 里显示的路径为准。
""",
            ),
            (
                "密钥",
                """【数据库密钥是什么】
微信聊天数据库是加密的，需要一串 32 字节（64 个十六进制字符）的密钥。
它不是你的微信登录密码，也不是手机号或验证码。

【三种情况】
1. 你已经有 key.txt：选「密钥文件」，浏览选中它
2. 你手里有 64 位密钥：选「直接粘贴」，粘贴到输入框
3. 两者都没有：需要先用你信任的密钥导出工具，在你自己拥有并授权的
   设备上取得密钥。详见项目里的 docs/getting-key.md

【本工具的边界】
- 不会从微信进程里自动提取密钥
- 不会把密钥写入日志或配置文件
- 直接粘贴的密钥只保存在当前运行内存中

【安全提醒】
不要使用网盘转包、破解版或来历不明的 exe。
不要把密钥发给别人，也不要用本工具读取他人的聊天记录。
""",
            ),
            (
                "常见问题",
                """Q: 为什么别的工具只能导出 2400 条？
A: 那是依赖 DLL 的旧工具的单次查询上限。本工具直接解密所有
   message_*.db 分片，在 SQLite 里合并后再导出，不受该限制。

Q: 图片为什么显示为 [图片]？
A: 图片文件可能不在本地，或需要账号级 image key。工具会先尝试消息里的
   aeskey；失败时用占位符，不会中断导出。WXGF/WxAM 等格式暂不完整支持。

Q: 语音、视频、表情包会导出吗？
A: 目前只输出 [语音]/[视频]/[表情] 占位，不解码媒体内容。

Q: 群聊发送者为什么显示 wxid？
A: 群昵称解析是尽力而为：优先 contact.db 的备注/昵称，解析不到就显示 wxid。

Q: 提示 WAL 未 checkpoint 怎么办？
A: 说明微信还开着，最新消息可能还在 WAL 里。建议退出微信后重新导出。

Q: 导出文件在哪里？怎么核对？
A: 在输出目录；多会话时每个会话一个子目录。manifest.json 记录条数、
   文件大小和 SHA-256。也可以用 wce validate --out 目录 校验。

Q: 数据会上传到网上吗？
A: 不会。完全本地处理，无网络请求、无遥测。导出的 CSV/PDF/Word 是明文，
   请自行加密保管，不要上传到公开仓库或网盘。

Q: 失败了怎么办？
A: 先看下方日志（点「显示日志」）；可以运行 wce doctor。
   反馈问题时不要附带密钥、聊天正文、数据库文件或完整个人路径。
""",
            ),
            (
                "支持与限制",
                """【已验证环境】
- Windows 11，微信 4.2.0.11
- Python 3.10 到 3.13
- 单会话 107,985 条完整导出

【能力】
- 跨 message_*.db 分片合并，不受 2400 条上限影响
- 文字、引用/链接/文件卡片、系统消息
- 图片基础支持（.dat V3 XOR / V4 AES / WXGF）
- CSV / Excel / HTML / PDF / Word
- 单会话、多会话、全部会话
- 最新 N 条、日期范围、按月/年拆分（日期范围仅命令行）
- 群聊发送者尽力解析

【限制】
- 未重放 WAL；存在未 checkpoint 的 WAL 时会提示
- 语音/视频/表情包只占位
- 群昵称解析可能回退到 wxid
- 仅支持 SQLCipher 4（page size 4096、reserve 80）
- 图片密钥、PDF 字体、日期范围等高级选项目前通过 CLI/config 提供
""",
            ),
            (
                "隐私与合规",
                """【本地处理】
- 不联网、无遥测、无自动更新
- 解密后的明文数据库放在系统临时目录，程序退出时自动删除
- 日志只记录计数和错误码，不记录消息正文或完整密钥

【导出文件】
CSV / Excel / HTML / PDF / Word 都是明文，包含完整聊天内容。
请自行加密保管，不要上传到公开仓库、网盘或聊天工具。

【合规】
- 仅导出你本人或已获得明确授权的数据
- 导出他人聊天记录可能违反法律、平台条款和聊天参与者隐私
- 工具不会修改微信数据库，但建议先退出微信以获得一致的快照
""",
            ),
        ]

    # --------------------------------------------------------------- helpers
    def _post(self, callback: Callable[..., None], *args: object) -> None:
        if self.closing:
            return
        with contextlib.suppress(tk.TclError):
            self.root.after(0, callback, *args)

    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _toggle_log(self) -> None:
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_frame.pack(fill=tk.BOTH, padx=12, pady=(2, 10))
            self.log_toggle_btn.configure(text="隐藏日志")
            self.log.see(tk.END)
        else:
            self.log_frame.pack_forget()
            self.log_toggle_btn.configure(text="显示日志")

    def _show_log(self) -> None:
        if not self.log_visible:
            self._toggle_log()

    def _set_status(self, text: str, color: str = "#555") -> None:
        self.status_var.set(text)
        self.status_label.configure(foreground=color)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        statespec = ["disabled"] if busy else ["!disabled"]
        for widget in self.data_widgets:
            widget.state(statespec)
        self.search_entry.state(statespec)
        self.limit_entry.state(statespec)
        self.tree.configure(selectmode="none" if busy else "extended")
        if busy:
            self.progress.pack(fill=tk.X, before=self.status_label)
            self.progress.start(12)
        else:
            self.progress.stop()
            self.progress.pack_forget()
        self._update_actions()
        if text:
            self._set_status(text)

    def _update_actions(self) -> None:
        if not hasattr(self, "load_btn"):
            return
        self.load_btn.configure(state=tk.DISABLED if self.busy else tk.NORMAL)
        has_selection = bool(self.tree.selection())
        has_format = any(var.get() for var in self.formats.values())
        can_export = not self.busy and self.repo is not None and has_selection and has_format
        self.export_btn.configure(state=tk.NORMAL if can_export else tk.DISABLED)
        self.open_btn.configure(state=tk.DISABLED if self.busy else tk.NORMAL)

    def _update_selection_state(self) -> None:
        selected = len(self.tree.selection())
        self.selected_var.set(
            f"已选 {selected} / 显示 {self.visible_count} / 共 {len(self.all_sessions)}"
        )
        self._update_actions()

    def _on_search_changed(self, *_args: object) -> None:
        if self._filter_after_id is not None:
            self.root.after_cancel(self._filter_after_id)
        self._filter_after_id = self.root.after(120, self._refresh_tree)

    def _refresh_tree(self) -> None:
        self._filter_after_id = None
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        needle = self.search_var.get().strip().casefold()
        visible = 0
        for session, count in self.all_sessions:
            name = session.display_name or session.username
            kind = "群" if session.is_group else "聊"
            haystack = f"{name} {session.username} {count} {count:,} {kind}".casefold()
            if needle and needle not in haystack:
                continue
            self.tree.insert(
                "",
                tk.END,
                iid=session.username,
                values=(name, count, kind),
            )
            visible += 1
        self.visible_count = visible
        keep = [iid for iid in selected if self.tree.exists(iid)]
        if keep:
            self.tree.selection_set(keep)
        self._update_selection_state()

    def _select_all(self) -> None:
        self.tree.selection_set(self.tree.get_children())
        self._update_selection_state()

    def _select_all_event(self, _event: tk.Event) -> str:
        self._select_all()
        return "break"

    def _clear_selection(self) -> None:
        self.tree.selection_remove(self.tree.selection())
        self._update_selection_state()

    def _cleanup_session(self) -> None:
        if self.decrypted is not None:
            self.decrypted.cleanup()
        elif self.work_dir is not None:
            shutil.rmtree(self.work_dir, ignore_errors=True)
        self.decrypted = None
        self.work_dir = None
        self.layout = None
        self.repo = None
        self.sessions = {}
        self.all_sessions = []
        self.visible_count = 0
        if hasattr(self, "tree"):
            self.tree.delete(*self.tree.get_children())
            self._update_selection_state()

    def _on_close(self) -> None:
        if self.busy and not messagebox.askokcancel(
            "正在处理", "读取或导出仍在进行，确定要退出吗？"
        ):
            return
        self.closing = True
        self.cancel_event.set()
        if self._filter_after_id is not None:
            self.root.after_cancel(self._filter_after_id)
            self._filter_after_id = None
        self._cleanup_session()
        self.root.destroy()

    # --------------------------------------------------------------- load
    def load_sessions(self) -> None:
        if self.busy:
            return
        db_dir = self.db_var.get().strip()
        key_file = self.key_var.get().strip()
        pasted_key = self.paste_var.get().strip()
        mode = self.key_mode_var.get()
        if not db_dir:
            messagebox.showerror("缺少参数", "请先选择微信数据目录")
            return
        if mode == "file" and not key_file:
            messagebox.showerror("缺少参数", "请选择密钥文件，或切换为「直接粘贴」")
            return
        if mode == "paste" and not pasted_key:
            messagebox.showerror("缺少参数", "请粘贴 64 位密钥，或切换为「密钥文件」")
            return
        self.cancel_event.clear()
        self._cleanup_session()
        self._set_busy(True, "正在解密数据库并统计会话...")
        threading.Thread(
            target=self._load_worker,
            args=(db_dir, mode, key_file, pasted_key),
            daemon=True,
        ).start()

    def _load_worker(self, db_dir: str, mode: str, key_file: str, pasted_key: str) -> None:
        work: Path | None = None
        try:
            key = (
                validate_key_hex(pasted_key)
                if mode == "paste"
                else load_key(key_file, prompt=False)
            )
            layout = find_layout(db_dir)
            work = make_work_dir()
            decrypted = decrypt_layout(layout, key, work)
            contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
            repo = MessageRepository(decrypted, layout.account_wxid, contacts)
            rows: list[tuple[Session, int]] = []
            for session in contacts.sessions():
                count = repo.count(session.username)
                if count:
                    rows.append((session, count))
            if self.closing:
                shutil.rmtree(work, ignore_errors=True)
                return
            self._post(self._show_sessions, rows, layout, decrypted, repo, work)
        except Exception as exc:
            if work is not None:
                shutil.rmtree(work, ignore_errors=True)
            self._post(self._failed, str(exc), True)

    def _show_sessions(
        self,
        rows: list[tuple[Session, int]],
        layout: DataLayout,
        decrypted: DecryptedLayout,
        repo: MessageRepository,
        work: Path,
    ) -> None:
        self.layout = layout
        self.decrypted = decrypted
        self.repo = repo
        self.work_dir = work
        self.sessions = {session.username: session for session, _ in rows}
        self.all_sessions = rows
        self._refresh_tree()
        self._set_busy(False)
        self._set_status(f"找到 {len(rows)} 个有消息的会话，选择后点「开始导出」", "#2e7d32")
        self._append_log(f"会话加载完成：{len(rows)} 个")

    def _failed(self, message: str, clear: bool = False) -> None:
        self._set_busy(False, "失败")
        self._set_status("失败：" + message.splitlines()[0][:120], "#c62828")
        self._append_log("错误: " + message)
        self._show_log()
        if clear:
            self._cleanup_session()
        messagebox.showerror("失败", message)

    # ------------------------------------------------------------- export
    def start_export(self) -> None:
        if self.busy:
            return
        if self.repo is None or self.decrypted is None:
            messagebox.showerror("还没有加载", "请先点击「读取会话」")
            return
        selected = list(self.tree.selection())
        if not selected:
            messagebox.showerror("没有选择", "请先选择一个或多个会话")
            return
        formats = [name for name, var in self.formats.items() if var.get()]
        if not formats:
            messagebox.showerror("没有格式", "请至少勾选一种导出格式")
            return
        out_dir = Path(self.out_var.get().strip() or "wce-exports")
        limit = None
        raw_limit = self.limit_var.get().strip()
        if raw_limit:
            try:
                limit = int(raw_limit)
                if limit <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showerror("条数无效", "最新条数必须是正整数，留空表示全部")
                return
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("输出目录不可用", f"无法创建或写入输出目录：\n{exc}")
            return

        count = sum(cnt for session, cnt in self.all_sessions if session.username in selected)
        warning = ""
        if self.layout is not None and self.layout.wal_bytes:
            warning = (
                "\n\n提示：检测到未 checkpoint 的 WAL，最新消息可能缺失。建议退出微信后重新导出。"
            )
        summary = (
            f"将导出 {len(selected)} 个会话，约 {count} 条消息。\n\n"
            f"格式：{', '.join(formats)}\n"
            f"最新条数：{'全部' if limit is None else limit}\n"
            f"输出目录：{out_dir}\n\n"
            "同名文件将被覆盖。"
            f"{warning}\n\n继续吗？"
        )
        if not messagebox.askokcancel("开始导出", summary):
            return
        if self.repo is None or self.layout is None:
            messagebox.showerror("内部状态丢失", "请重新读取会话")
            return
        repo = self.repo
        layout = self.layout
        sessions = dict(self.sessions)
        image_key_file = self.image_key_file
        self.cancel_event.clear()
        self._set_busy(True, f"正在导出 {len(selected)} 个会话...")
        threading.Thread(
            target=self._export_worker,
            args=(
                repo,
                layout,
                sessions,
                image_key_file,
                selected,
                formats,
                out_dir,
                limit,
            ),
            daemon=True,
        ).start()

    def _export_worker(
        self,
        repo: MessageRepository,
        layout: DataLayout,
        sessions: dict[str, Session],
        image_key_file: str,
        selected: list[str],
        formats: list[str],
        out_dir: Path,
        limit: int | None,
    ) -> None:
        try:
            image_key = load_image_key(image_key_file, layout.account_wxid)
            resolver = ImageResolver(
                ImageIndex(layout.attach_dir, layout.account_dir),
                image_key,
                mode="auto",
            )
            total = 0
            failed = 0
            for index, username in enumerate(selected, start=1):
                if self.cancel_event.is_set() or self.closing:
                    break
                session = sessions.get(username)
                label = session.display_name if session else username
                try:
                    messages = list(repo.iter_messages(username, limit=limit, ascending=True))
                    for message in messages:
                        resolver.resolve(message)
                    target = out_dir if len(selected) == 1 else out_dir / sanitize(label)
                    result = export_session(
                        messages,
                        out_dir=target,
                        display_name=label,
                        session_username=username,
                        formats=formats,
                        split="auto",
                        tz=None,
                        image_mode="auto",
                        overwrite="force",
                    )
                    total += result.records
                    for error in result.errors:
                        self._post(self._append_log, f"错误: {error}")
                    self.root.after(
                        0, self._log_progress, index, len(selected), label, len(messages)
                    )
                except Exception as exc:
                    failed += 1
                    self._post(self._append_log, f"会话 {label} 导出失败: {exc}")
            if not self.closing:
                self._post(self._export_done, total, out_dir, failed)
        except Exception as exc:
            self._post(self._failed, str(exc), False)

    def _log_progress(self, index: int, total: int, name: str, count: int) -> None:
        self._append_log(f"[{index}/{total}] {name}: {count} 条")

    def _export_done(self, total: int, out_dir: Path, failed: int) -> None:
        self._set_busy(False)
        if failed:
            self._set_status(f"导出完成：{total} 条，{failed} 个会话失败，见日志", "#ef6c00")
        else:
            self._set_status(f"导出完成：{total} 条 → {out_dir}", "#2e7d32")
        self._append_log(f"完成，共 {total} 条，输出目录: {out_dir}")
        if failed:
            messagebox.showwarning(
                "部分完成", f"已导出 {total} 条消息\n{failed} 个会话失败，详情见日志\n{out_dir}"
            )
        else:
            messagebox.showinfo("完成", f"已导出 {total} 条消息\n{out_dir}")

    def open_output(self) -> None:
        path = Path(self.out_var.get().strip() or "wce-exports")
        try:
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))


def main(config: dict | None = None) -> int:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:  # pragma: no cover - older Windows
            pass
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # e.g. no display
        raise SystemExit(f"无法启动图形界面: {exc}") from exc
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    style.configure("Primary.TButton", font=("Microsoft YaHei", 10, "bold"))
    ExportApp(root, config=config)
    root.mainloop()
    return 0
