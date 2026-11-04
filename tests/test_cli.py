from __future__ import annotations

import json
from pathlib import Path

from wechat_chat_exporter.cli import main


def test_doctor(account: Path, key_file: Path, capsys) -> None:
    code = main(["doctor", "--db-dir", str(account / "db_storage"), "--key-file", str(key_file)])
    out = capsys.readouterr().out
    assert code == 0
    assert "消息分片: 2" in out
    assert "会话: 1" in out


def test_sessions_json(account: Path, key_file: Path, capsys) -> None:
    code = main(
        ["sessions", "--db-dir", str(account / "db_storage"), "--key-file", str(key_file), "--json"]
    )
    out = capsys.readouterr().out
    assert code == 0
    rows = json.loads(out)
    assert rows[0]["username"] == "wxid_alice0001"
    assert rows[0]["messages"] == 6
    assert rows[0]["display"] == "Alice备注"


def test_export_and_validate(account: Path, key_file: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "out"
    code = main(
        [
            "export",
            "--db-dir",
            str(account / "db_storage"),
            "--key-file",
            str(key_file),
            "--session",
            "wxid_alice0001",
            "--formats",
            "csv,html",
            "--split",
            "none",
            "--out",
            str(out),
        ]
    )
    capsys.readouterr()
    assert code == 0
    assert (out / "Alice备注.csv").exists()
    assert (out / "Alice备注.html").exists()

    code = main(["validate", "--out", str(out), "--expect-count", "6"])
    capsys.readouterr()
    assert code == 0


def test_wrong_key_exit_code(account: Path, tmp_path: Path, capsys) -> None:
    bad = tmp_path / "bad.txt"
    bad.write_text("00" * 32, encoding="utf-8")
    code = main(["doctor", "--db-dir", str(account / "db_storage"), "--key-file", str(bad)])
    capsys.readouterr()
    assert code == 3


def test_config_drives_export(account: Path, key_file: Path, tmp_path: Path, capsys) -> None:
    out = tmp_path / "cfg-out"
    config = tmp_path / "wce.json"
    config.write_text(
        json.dumps(
            {
                "db_dir": str(account / "db_storage"),
                "key_file": str(key_file),
                "session": "wxid_alice0001",
                "out": str(out),
                "formats": "csv",
                "split": "none",
            }
        ),
        encoding="utf-8",
    )
    code = main(["export", "--config", str(config)])
    capsys.readouterr()
    assert code == 0
    assert (out / "Alice备注.csv").exists()


def test_init_writes_config(tmp_path: Path, monkeypatch, capsys) -> None:
    answers = iter(
        [
            str(tmp_path / "db_storage"),
            "key.txt",
            "all",
            str(tmp_path / "out"),
            "csv,html",
            "auto",
            "auto",
            "",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt: next(answers))
    output = tmp_path / "wce.json"
    code = main(["init", "--output", str(output)])
    capsys.readouterr()
    assert code == 0
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["db_dir"].endswith("db_storage")
    assert data["formats"] == "csv,html"
