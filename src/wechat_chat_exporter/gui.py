"""Minimal Tkinter desktop UI for wechat-chat-exporter.

Run with ``wce gui``.  The GUI is a thin layer over the same library used by
the CLI: it never extracts keys and never opens a network socket.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import tkinter as tk
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


class ExportApp:
    def __init__(self, root: tk.Tk, config: dict | None = None) -> None:
        self.root = root
        self.root.title(f"wechat-chat-exporter v{__version__}")
        self.root.geometry("920x680")
        self.root.minsize(820, 600)

        self.config_data = config or {}
        self.layout: DataLayout | None = None
        self.decrypted: DecryptedLayout | None = None
        self.work_dir: Path | None = None
        self.repo: MessageRepository | None = None
        self.sessions: dict[str, Session] = {}
        self.busy = False

        self.db_var = tk.StringVar(value=str(self.config_data.get("db_dir", "")))
        self.key_var = tk.StringVar(value=str(self.config_data.get("key_file", "")))
        self.paste_var = tk.StringVar()
        self.show_key_var = tk.BooleanVar(value=False)
        self.out_var = tk.StringVar(
            value=str(self.config_data.get("out", str(Path.home() / "wce-exports")))
        )
        self.limit_var = tk.StringVar(value=str(self.config_data.get("limit") or ""))
        self.status_var = tk.StringVar(value="请选择微信数据目录，并提供密钥（文件或直接粘贴）")
        configured = {
            part.strip().lower()
            for part in str(self.config_data.get("formats", "")).split(",")
            if part.strip()
        }
        self.formats = {
            name: tk.BooleanVar(
                value=(name in configured) if configured else name in ("csv", "html")
            )
            for name in ("csv", "xlsx", "html", "pdf", "docx")
        }
        self.image_key_file = str(self.config_data.get("image_key_file", ""))

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill=tk.X, padx=10, pady=(10, 0))

        self._path_row(top, 0, "微信数据目录", self.db_var, self._pick_db)
        self._path_row(top, 1, "密钥文件", self.key_var, self._pick_key)
        self._path_row(top, 2, "输出目录", self.out_var, self._pick_out)

        ttk.Label(top, text="或直接粘贴 64 位密钥", width=16).grid(
            row=3, column=0, sticky="w", pady=3
        )
        self.key_entry = ttk.Entry(top, textvariable=self.paste_var, show="•")
        self.key_entry.grid(row=3, column=1, sticky="ew", pady=3)
        key_tools = ttk.Frame(top)
        key_tools.grid(row=3, column=2, sticky="w", padx=(6, 0))
        ttk.Checkbutton(
            key_tools, text="显示", variable=self.show_key_var, command=self._toggle_key
        ).pack(side=tk.LEFT)
        ttk.Button(key_tools, text="说明", command=self._show_key_help, width=5).pack(
            side=tk.LEFT, padx=(4, 0)
        )

        actions = ttk.Frame(top)
        actions.grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))
        self.load_btn = ttk.Button(actions, text="读取会话", command=self.load_sessions)
        self.load_btn.pack(side=tk.LEFT, padx=2)
        ttk.Button(actions, text="自动查找数据目录", command=self._auto_find_db).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(actions, text="数据目录说明", command=self._show_data_help).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Button(actions, text="使用说明 / Q&A", command=self._show_faq).pack(
            side=tk.LEFT, padx=2
        )
        ttk.Label(actions, text="最新条数（留空=全部）").pack(side=tk.LEFT, padx=(16, 4))
        ttk.Entry(actions, textvariable=self.limit_var, width=10).pack(side=tk.LEFT)

        ttk.Label(
            self.root,
            text=(
                "数据目录一般位于「文档\\xwechat_files\\<你的wxid>\\db_storage」，"
                "也可以在微信左下角 设置 → 文件管理 → 打开文件夹 找到 xwechat_files。"
                "选择 db_storage 或它的上级目录都可以。"
            ),
            foreground="#666",
            wraplength=880,
            justify=tk.LEFT,
        ).pack(fill=tk.X, padx=10, pady=(6, 0))

        mid = ttk.Frame(self.root)
        mid.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)

        cols = ("name", "count", "kind")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="extended")
        self.tree.heading("name", text="会话")
        self.tree.heading("count", text="条数")
        self.tree.heading("kind", text="类型")
        self.tree.column("name", width=560)
        self.tree.column("count", width=100, anchor="e")
        self.tree.column("kind", width=80, anchor="center")
        scroll = ttk.Scrollbar(mid, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        bottom = ttk.Frame(self.root)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 8))
        ttk.Label(bottom, text="导出格式").pack(side=tk.LEFT)
        for name, var in self.formats.items():
            ttk.Checkbutton(bottom, text=name.upper(), variable=var).pack(side=tk.LEFT, padx=3)
        self.export_btn = ttk.Button(bottom, text="开始导出", command=self.start_export)
        self.export_btn.pack(side=tk.RIGHT, padx=2)
        self.open_btn = ttk.Button(bottom, text="打开输出目录", command=self.open_output)
        self.open_btn.pack(side=tk.RIGHT, padx=2)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=10)
        ttk.Label(self.root, textvariable=self.status_var, anchor="w").pack(
            fill=tk.X, padx=10, pady=(4, 0)
        )

        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=10, pady=(4, 10))
        self.log = tk.Text(log_frame, height=7, state=tk.DISABLED, wrap=tk.WORD)
        log_scroll = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def _path_row(
        self, parent: ttk.Frame, row: int, label: str, var: tk.StringVar, command
    ) -> None:
        ttk.Label(parent, text=label, width=12).grid(row=row, column=0, sticky="w", pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", pady=3)
        ttk.Button(parent, text="浏览", command=command, width=8).grid(
            row=row, column=2, padx=(6, 0), pady=3
        )
        parent.columnconfigure(1, weight=1)

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

    def _auto_find_db(self) -> None:
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
        for root in roots:
            if not root.is_dir():
                continue
            if (root / "db_storage").is_dir() and root not in found:
                found.append(root)
            try:
                for child in root.iterdir():
                    if child.is_dir() and (child / "db_storage").is_dir() and child not in found:
                        found.append(child)
            except OSError:
                continue
        if len(found) == 1:
            self.db_var.set(str(found[0]))
            self.status_var.set("已自动找到数据目录，请确认后读取会话")
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
                "进入 xwechat_files 后选择 wxid_ 开头的账号目录。",
            )

    def _show_data_help(self) -> None:
        messagebox.showinfo(
            "微信数据目录是什么",
            "微信把聊天记录、联系人和图片存在一个叫 db_storage 的文件夹里。\n\n"
            "怎么找：\n"
            "1. 打开微信电脑版\n"
            "2. 左下角 设置 → 文件管理 → 打开文件夹\n"
            "3. 进入 xwechat_files\n"
            "4. 里面通常有一个 wxid_ 开头的文件夹\n"
            "5. 进入后能看到 db_storage 文件夹\n\n"
            "在本工具里选择 db_storage，或者选择它上一级的 wxid_ 文件夹，"
            "两种都可以。\n\n"
            "如果你改过微信的存储位置，以 设置 → 文件管理 里显示的路径为准。",
        )

    def _show_key_help(self) -> None:
        messagebox.showinfo(
            "什么是数据库密钥",
            "微信的聊天数据库是加密的，需要一串 64 位的十六进制密钥才能读取。\n\n"
            "它不是你的微信登录密码，也不是手机号。\n\n"
            "本工具不会从微信进程里自动提取密钥。你可以：\n"
            "1. 如果之前用可信工具导出过 key.txt，直接选择该文件；\n"
            "2. 如果你手里已经有 64 位密钥，直接粘贴到输入框；\n"
            "3. 如果两者都没有，需要先用你信任的密钥导出工具，"
            "在你自己拥有并授权的设备上取得密钥。\n\n"
            "详细说明见项目里的 docs/getting-key.md。\n\n"
            "请勿使用来历不明的程序，也不要用它读取他人的聊天记录。",
        )

    def _show_faq(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("使用说明 / Q&A")
        win.geometry("780x640")
        frame = ttk.Frame(win)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text = tk.Text(
            frame,
            wrap=tk.WORD,
            padx=12,
            pady=10,
            font=("Microsoft YaHei", 10),
            spacing1=2,
            spacing3=6,
        )
        scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        text.configure(yscrollcommand=scroll.set)
        text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        text.insert("1.0", self._faq_text())
        text.configure(state=tk.DISABLED)

    @staticmethod
    def _faq_text() -> str:
        return f"""wechat-chat-exporter v{__version__} 使用说明

【支持版本】
- 已在 Windows 11 + 微信 4.2.0.11 上完整验证（单会话 107,985 条）
- 其他微信 4.x 尽力兼容；微信 3.x 不支持
- 微信升级后数据库结构或密钥机制可能变化。如果读取失败，先看下方日志，
  或运行 wce doctor 获取更详细的诊断信息。

【第一次使用】
1. 微信数据目录：选择 db_storage 文件夹，或它上一级的 wxid_ 文件夹。
   不知道在哪：微信左下角 设置 → 文件管理 → 打开文件夹 → xwechat_files。
   也可以直接点「自动查找数据目录」。
2. 密钥：选择 key.txt，或把 64 位密钥直接粘贴到「或直接粘贴 64 位密钥」。
3. 输出目录：导出文件放哪里。
4. 点「读取会话」，等待解密和统计完成。
5. 在列表里选中一个或多个会话，勾选需要的格式。
6. 点「开始导出」。完成后可以点「打开输出目录」。

【常见问题】
Q: 微信数据目录到底指什么？
A: 微信把聊天记录存在一个叫 db_storage 的文件夹里。它通常在
   文档\\xwechat_files\\<你的wxid>\\db_storage。选择 db_storage 或
   wxid_ 文件夹都可以。

Q: 密钥是什么？我没有。
A: 数据库是加密的，需要 32 字节（64 个十六进制字符）的密钥。它不是微信
   登录密码。本工具不自动从微信进程提取密钥；可以使用已有的 key.txt、
   直接粘贴密钥，或使用你自己信任的工具在本人设备上导出。
   详见 docs/getting-key.md。

Q: 为什么别的工具只能导出 2400 条？
A: 那是依赖 DLL 的旧工具的单次查询上限。本工具直接解密所有
   message_*.db 分片并在 SQLite 里合并，不受该限制。

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
A: 先看界面下方日志；可以运行 wce doctor。反馈问题时不要附带密钥、
   聊天正文、数据库文件或完整个人路径。

【注意事项】
- 仅用于导出你本人或已获得明确授权的数据。
- 工具不会修改微信数据库，但请先退出微信以获得一致的快照。
- 导出他人聊天内容可能违反法律、平台条款和聊天参与者隐私。
"""

    # ------------------------------------------------------------- helpers
    def _append_log(self, text: str) -> None:
        self.log.configure(state=tk.NORMAL)
        self.log.insert(tk.END, text + "\n")
        self.log.see(tk.END)
        self.log.configure(state=tk.DISABLED)

    def _set_busy(self, busy: bool, text: str = "") -> None:
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.load_btn.configure(state=state)
        self.export_btn.configure(state=state)
        if busy:
            self.progress.start(12)
        else:
            self.progress.stop()
        if text:
            self.status_var.set(text)

    def _cleanup_session(self) -> None:
        if self.decrypted is not None:
            self.decrypted.cleanup()
            self.decrypted = None
        if self.work_dir is not None:
            shutil.rmtree(self.work_dir, ignore_errors=True)
            self.work_dir = None

    def _on_close(self) -> None:
        self._cleanup_session()
        self.root.destroy()

    # --------------------------------------------------------------- load
    def load_sessions(self) -> None:
        if self.busy:
            return
        db_dir = self.db_var.get().strip()
        key_file = self.key_var.get().strip()
        pasted_key = self.paste_var.get().strip()
        if not db_dir or (not key_file and not pasted_key):
            messagebox.showerror("缺少参数", "请先选择微信数据目录，并提供密钥文件或直接粘贴密钥")
            return
        self._set_busy(True, "正在解密数据库并统计会话...")
        self._cleanup_session()
        threading.Thread(
            target=self._load_worker,
            args=(db_dir, key_file, pasted_key),
            daemon=True,
        ).start()

    def _load_worker(self, db_dir: str, key_file: str, pasted_key: str) -> None:
        try:
            key = validate_key_hex(pasted_key) if pasted_key else load_key(key_file, prompt=False)
            layout = find_layout(db_dir)
            work = make_work_dir()
            decrypted = decrypt_layout(layout, key, work)
            contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
            repo = MessageRepository(decrypted, layout.account_wxid, contacts)
            rows = []
            for session in contacts.sessions():
                count = repo.count(session.username)
                if count:
                    rows.append((session, count))
            self.layout = layout
            self.decrypted = decrypted
            self.work_dir = work
            self.repo = repo
            self.root.after(0, lambda: self._show_sessions(rows))
        except Exception as exc:  # surface a readable message
            self.root.after(0, self._failed, str(exc))

    def _show_sessions(self, rows: list[tuple[Session, int]]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.sessions = {session.username: session for session, _ in rows}
        for session, count in rows:
            kind = "群" if session.is_group else "聊"
            self.tree.insert(
                "",
                tk.END,
                iid=session.username,
                values=(session.display_name or session.username, count, kind),
            )
        self._set_busy(False, f"找到 {len(rows)} 个有消息的会话，请选择后导出")
        self._append_log(f"会话加载完成：{len(rows)} 个")

    def _failed(self, message: str) -> None:
        self._set_busy(False, "失败")
        self._append_log("错误: " + message)
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
        self._set_busy(True, f"正在导出 {len(selected)} 个会话...")
        threading.Thread(
            target=self._export_worker,
            args=(selected, formats, out_dir, limit),
            daemon=True,
        ).start()

    def _export_worker(
        self, selected: list[str], formats: list[str], out_dir: Path, limit: int | None
    ) -> None:
        assert self.repo is not None
        assert self.decrypted is not None
        assert self.layout is not None
        try:
            image_key = load_image_key(self.image_key_file, self.layout.account_wxid)
            resolver = ImageResolver(
                ImageIndex(self.layout.attach_dir, self.layout.account_dir),
                image_key,
                mode="auto",
            )
            total = 0
            for index, username in enumerate(selected, start=1):
                session = self.sessions.get(username)
                label = session.display_name if session else username
                messages = list(self.repo.iter_messages(username, limit=limit, ascending=True))
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
                self.root.after(0, self._log_progress, index, len(selected), label, len(messages))
            self.root.after(0, self._export_done, total, out_dir)
        except Exception as exc:
            self.root.after(0, self._failed, str(exc))

    def _log_progress(self, index: int, total: int, name: str, count: int) -> None:
        self._append_log(f"[{index}/{total}] {name}: {count} 条")

    def _export_done(self, total: int, out_dir: Path) -> None:
        self._set_busy(False, f"导出完成：{total} 条 → {out_dir}")
        self._append_log(f"完成，共 {total} 条，输出目录: {out_dir}")
        messagebox.showinfo("完成", f"已导出 {total} 条消息\n{out_dir}")

    def open_output(self) -> None:
        path = Path(self.out_var.get().strip() or "wce-exports")
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("无法打开", str(exc))


def main(config: dict | None = None) -> int:
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # e.g. no display
        raise SystemExit(f"无法启动图形界面: {exc}") from exc
    ExportApp(root, config=config)
    root.mainloop()
    return 0
