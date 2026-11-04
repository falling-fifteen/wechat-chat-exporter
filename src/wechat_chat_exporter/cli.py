"""Command-line interface."""

from __future__ import annotations

import argparse
import datetime
import json
import shutil
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import __version__
from .config import CONFIG_NAME, apply_config, finalize_args
from .crypto.key_source import load_image_key, load_key
from .db.contacts import ContactResolver
from .db.decrypt import decrypt_layout, make_work_dir
from .db.discovery import find_layout
from .db.repository import MessageRepository
from .errors import UsageError, WxError
from .export.naming import sanitize
from .export.runner import export_session
from .logging import get_logger, setup_logging
from .media.index import ImageIndex
from .media.resolver import ImageResolver
from .model.session import Session

log = get_logger()


def _date_bound(value: str | None, *, end: bool, tz=None) -> int | None:
    if not value:
        return None
    try:
        day = datetime.date.fromisoformat(value)
    except ValueError as exc:
        raise UsageError(f"日期格式应为 YYYY-MM-DD: {value}") from exc
    if end:
        day = day + datetime.timedelta(days=1)
        return int(datetime.datetime.combine(day, datetime.time(), tzinfo=tz).timestamp()) - 1
    return int(datetime.datetime.combine(day, datetime.time(), tzinfo=tz).timestamp())


def _tz(name: str | None):
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise UsageError(f"未知时区: {name}") from exc


def _common_paths(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db-dir", help="微信 db_storage 目录或其上级目录")
    parser.add_argument("--key-file", help="包含 64 位数据库密钥的文件")
    parser.add_argument("--config", help=f"JSON 配置文件（默认自动读取 ./{CONFIG_NAME}）")
    parser.add_argument("--key-stdin", action="store_true", default=None, help="从 stdin 读取密钥")
    parser.add_argument(
        "--strict-hmac", action="store_true", default=None, help="HMAC 校验失败即中止"
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        default=None,
        help="保留解密临时目录（含明文数据库）",
    )
    parser.add_argument("--work-dir", help="指定临时工作目录")
    parser.add_argument("--verbose", action="store_true", default=None)


def _load_key(args: argparse.Namespace) -> bytes:
    return load_key(args.key_file, key_stdin=args.key_stdin, prompt=True)


def _warn_wal(layout) -> None:
    if layout.wal_bytes:
        log.warning(
            "检测到未 checkpoint 的 WAL 文件（%s），最新消息可能缺失。建议退出微信后重新运行。",
            ", ".join(layout.wal_files),
        )


def _session_matches(sessions: list[Session], selector: str) -> list[Session]:
    exact = [s for s in sessions if s.username == selector]
    if exact:
        return exact[:1]
    by_name = [s for s in sessions if s.display_name == selector]
    if by_name:
        return by_name[:1]
    needle = selector.casefold()
    fuzzy = [
        s
        for s in sessions
        if needle in s.display_name.casefold() or needle in s.username.casefold()
    ]
    if fuzzy:
        return fuzzy
    if selector.startswith("wxid_") or selector.endswith("@chatroom"):
        return [Session(username=selector)]
    raise UsageError(f"找不到会话: {selector}")


def _select_sessions(
    repo: MessageRepository, contacts: ContactResolver, selector: str
) -> list[Session]:
    sessions = contacts.sessions()
    if selector == "all":
        selected = [s for s in sessions if repo.count(s.username) > 0]
        if not selected:
            raise UsageError("没有找到任何有消息的会话")
        return selected

    path = Path(selector)
    if path.exists() and path.is_file():
        names = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]
        out: list[Session] = []
        for name in filter(None, names):
            out.extend(_session_matches(sessions, name)[:1])
        if not out:
            raise UsageError("会话文件里没有可用的会话")
        return out

    matches = _session_matches(sessions, selector)
    if len(matches) > 1:
        preview = ", ".join(f"{m.display_name}({m.username})" for m in matches[:10])
        raise UsageError(f"匹配到多个会话，请使用 wxid 精确指定：{preview}")
    return matches


def cmd_doctor(args: argparse.Namespace) -> int:
    layout = find_layout(args.db_dir)
    print(f"db_storage: {layout.db_storage}")
    print(f"账号: {layout.account_wxid or '(未识别)'}")
    print(f"消息分片: {len(layout.shards)}")
    for shard in layout.shards:
        print(f"  - {shard.name}  {shard.stat().st_size / 1024 / 1024:.1f} MB")
    if layout.session_db:
        print(f"session.db: {layout.session_db.name}")
    if layout.contact_db:
        print(f"contact.db: {layout.contact_db.name}")
    if layout.wal_bytes:
        print(
            f"WARNING: 未 checkpoint 的 WAL: "
            f"{', '.join(layout.wal_files)} ({layout.wal_bytes} bytes)"
        )
    else:
        print("WAL: 无未提交内容")

    key = _load_key(args)
    work = make_work_dir(args.work_dir)
    try:
        decrypted = decrypt_layout(layout, key, work, strict_hmac=args.strict_hmac)
        failed = sum(stats.hmac_failed for _, stats in decrypted.stats)
        print(f"解密: {len(decrypted.shards)} 个消息分片成功")
        if failed:
            print(f"HMAC: {failed} 页未通过（已按头部校验继续）")
        contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
        sessions = contacts.sessions()
        print(f"会话: {len(sessions)}")
        repo = MessageRepository(decrypted, layout.account_wxid, contacts)
        with_messages = sum(1 for s in sessions if repo.count(s.username) > 0)
        print(f"有消息的会话: {with_messages}")
        return 0
    finally:
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"临时目录已保留: {work}")


def cmd_sessions(args: argparse.Namespace) -> int:
    layout = find_layout(args.db_dir)
    _warn_wal(layout)
    key = _load_key(args)
    work = make_work_dir(args.work_dir)
    try:
        decrypted = decrypt_layout(layout, key, work, strict_hmac=args.strict_hmac)
        contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
        sessions = contacts.sessions()
        repo = MessageRepository(decrypted, layout.account_wxid, contacts)
        rows = []
        for session in sessions:
            count = repo.count(session.username)
            if count == 0:
                continue
            rows.append(
                {
                    "username": session.username,
                    "display": session.display_name,
                    "messages": count,
                    "group": session.is_group,
                    "last_timestamp": session.last_timestamp,
                }
            )
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            for row in rows:
                kind = "群" if row["group"] else "聊"
                print(f"{row['messages']:>8}  [{kind}] {row['display']}  ({row['username']})")
        return 0
    finally:
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"临时目录已保留: {work}")


def cmd_export(args: argparse.Namespace) -> int:
    args.out = Path(args.out)
    layout = find_layout(args.db_dir)
    _warn_wal(layout)
    if args.strict_wal and layout.wal_bytes:
        raise WxError("存在未 checkpoint 的 WAL；按 --strict-wal 中止")

    key = _load_key(args)
    tz = _tz(args.timezone)
    since = _date_bound(args.since, end=False, tz=tz)
    until = _date_bound(args.until, end=True, tz=tz)

    work = make_work_dir(args.work_dir)
    try:
        decrypted = decrypt_layout(layout, key, work, strict_hmac=args.strict_hmac)
        contacts = ContactResolver(decrypted.session_db, decrypted.contact_db)
        me = args.me or layout.account_wxid
        repo = MessageRepository(decrypted, me, contacts, me_label=args.label_me)
        selected = _select_sessions(repo, contacts, args.session)
        log.info("准备导出 %d 个会话", len(selected))

        image_key = load_image_key(args.image_key_file, layout.account_wxid)
        index = ImageIndex(layout.attach_dir, layout.account_dir)
        resolver = None
        if args.image_mode != "none":
            resolver = ImageResolver(index, image_key, mode=args.image_mode)

        formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
        failed = 0
        total_records = 0
        for session in selected:
            log.info("读取会话: %s", session.display_name or session.username)
            try:
                messages = list(
                    repo.iter_messages(
                        session.username,
                        since=since,
                        until=until,
                        limit=args.limit,
                        ascending=True,
                        exclude_system=args.exclude_system,
                    )
                )
            except Exception as exc:
                failed += 1
                log.error("读取失败 %s: %s", session.username, exc)
                continue
            if not messages:
                log.warning("跳过空会话: %s", session.display_name or session.username)
                continue
            if args.dry_run:
                print(f"{session.display_name or session.username}: {len(messages)} 条")
                total_records += len(messages)
                continue
            if resolver is not None:
                for msg in messages:
                    resolver.resolve(msg)
            out_dir = args.out
            if len(selected) > 1:
                out_dir = args.out / sanitize(session.display_name or session.username)
            result = export_session(
                messages,
                out_dir=out_dir,
                display_name=session.display_name or session.username,
                session_username=session.username,
                formats=formats,
                split=args.split,
                tz=tz,
                image_mode=args.image_mode,
                overwrite=args.overwrite,
                pdf_font=args.pdf_font,
                me_label=args.label_me,
            )
            total_records += result.records
            if result.errors:
                failed += 1
                for err in result.errors:
                    log.error("%s", err)
            log.info(
                "完成 %s: %d 条，%d 个文件，跳过 %d",
                session.display_name or session.username,
                result.records,
                len(result.files),
                len(result.skipped),
            )
        print(f"总计 {total_records} 条消息")
        if failed and failed >= len(selected):
            return 5
        return 4 if failed else 0
    finally:
        if not args.keep_work:
            shutil.rmtree(work, ignore_errors=True)
        else:
            print(f"临时目录已保留: {work}")


def cmd_validate(args: argparse.Namespace) -> int:
    manifests = sorted(Path(args.out).rglob("manifest.json"))
    if not manifests:
        raise UsageError(f"在 {args.out} 下没有找到 manifest.json")
    total = 0
    problems: list[str] = []
    for manifest_path in manifests:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        total += int(data.get("records", 0))
        for item in data.get("files", []):
            path = manifest_path.parent / item["path"]
            if not path.exists() or path.stat().st_size == 0:
                problems.append(f"缺失或为空: {path}")
        for err in data.get("errors", []):
            problems.append(f"{manifest_path.parent.name}: {err}")
    if args.expect_count is not None and total != args.expect_count:
        problems.append(f"消息总数 {total} != 期望 {args.expect_count}")
    payload = {
        "manifests": len(manifests),
        "records": total,
        "problems": problems,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"manifest: {len(manifests)}, 消息: {total}, 问题: {len(problems)}")
        for problem in problems:
            print("  -", problem)
    return 0 if not problems else 4


def cmd_init(args: argparse.Namespace) -> int:
    def ask(prompt: str, default: str = "") -> str:
        suffix = f" [{default}]" if default else ""
        try:
            value = input(f"{prompt}{suffix}: ").strip()
        except EOFError as exc:
            raise UsageError("交互输入不可用；请改用命令行参数") from exc
        return value or default

    print("生成 wce.json。直接回车使用默认值或跳过。")
    data = {
        "db_dir": ask("微信 db_storage 路径"),
        "key_file": ask("密钥文件路径（可留空，运行时再输入）"),
        "session": ask("会话 wxid / 备注名 / all", "all"),
        "out": ask("导出目录", "./exports"),
        "formats": ask("格式（逗号分隔）", "csv,html"),
        "split": ask("拆分 auto/none/year/month", "auto"),
        "image_mode": ask("图片模式 none/placeholder/auto/inline/file", "auto"),
        "image_key_file": ask("image_key.json 路径（可留空）"),
    }
    if not data["db_dir"]:
        raise UsageError("db_storage 路径不能为空")
    output = Path(args.output)
    payload = {key: value for key, value in data.items() if value}
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"已写入 {output}")
    print(f"下一步: wce export --config {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wechat-chat-exporter",
        description="导出本机微信 4.x 聊天记录为 CSV / Excel / HTML / PDF / Word。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="检查数据目录、密钥和分片")
    _common_paths(doctor)
    doctor.set_defaults(func=cmd_doctor)

    sessions = sub.add_parser("sessions", help="列出有消息的会话")
    _common_paths(sessions)
    sessions.add_argument("--json", action="store_true")
    sessions.set_defaults(func=cmd_sessions)

    export = sub.add_parser("export", help="导出聊天记录")
    _common_paths(export)
    export.add_argument("--session", help="wxid、备注名、all 或会话列表文件")
    export.add_argument("--formats", help="csv,xlsx,html,pdf,docx,jsonl")
    export.add_argument("--out", help="输出目录")
    export.add_argument("--split", choices=["auto", "none", "year", "month"])
    export.add_argument("--limit", type=int, help="只导出最新 N 条")
    export.add_argument("--since", help="起始日期 YYYY-MM-DD")
    export.add_argument("--until", help="结束日期 YYYY-MM-DD（含当天）")
    export.add_argument("--timezone", help="如 Asia/Shanghai")
    export.add_argument("--me", help="自己的 wxid（默认从账号目录推导）")
    export.add_argument("--label-me")
    export.add_argument(
        "--exclude-system", action="store_true", default=None, help="不导出系统消息"
    )
    export.add_argument(
        "--image-mode",
        choices=["none", "placeholder", "auto", "inline", "file"],
    )
    export.add_argument("--image-key-file", help="可选 image_key.json")
    export.add_argument("--pdf-font", help="PDF 使用的中文字体文件")
    export.add_argument("--overwrite", choices=["skip", "force", "ask"])
    export.add_argument("--strict-wal", action="store_true", help="存在 WAL 时直接失败")
    export.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    export.set_defaults(func=cmd_export)

    validate = sub.add_parser("validate", help="校验导出结果")
    validate.add_argument("--out")
    validate.add_argument("--config", help=f"JSON 配置文件（默认自动读取 ./{CONFIG_NAME}）")
    validate.add_argument("--expect-count", type=int)
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=cmd_validate)

    init = sub.add_parser("init", help="交互式生成 wce.json")
    init.add_argument("--output", default=CONFIG_NAME, help="配置文件路径")
    init.set_defaults(func=cmd_init)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args = finalize_args(apply_config(args))
        setup_logging(getattr(args, "verbose", False))
        return int(args.func(args))
    except UsageError as exc:
        parser.error(str(exc))
        return 2
    except WxError as exc:
        log.error("%s", exc)
        return exc.exit_code
    except KeyboardInterrupt:
        log.error("已取消")
        return 130


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
