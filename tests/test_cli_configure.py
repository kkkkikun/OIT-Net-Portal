from __future__ import annotations

import os
from pathlib import Path

from oit_portal.cli import EXIT_ERROR, EXIT_OK, cmd_configure
from oit_portal.config import Config, load_config
from oit_portal.paths import AppPaths


def make_paths(tmp_path: Path) -> AppPaths:
    return AppPaths(
        home=tmp_path,
        config=tmp_path / "config.toml",
        credentials=tmp_path / "credentials.toml",
        session=tmp_path / "session.json",
        log_dir=tmp_path / "logs",
        log_file=tmp_path / "logs" / "oit-portal.log",
        lock=tmp_path / "app.lock",
        pid=tmp_path / "app.pid",
    )


def test_configure_saves_special_characters_without_logging_password(
        tmp_path, monkeypatch, capsys):
    paths = make_paths(tmp_path)
    secret = 'p"a\\ss\n密码'
    monkeypatch.setattr("builtins.input", lambda _prompt: "20230001")
    monkeypatch.setattr("getpass.getpass", lambda _prompt: secret)

    assert cmd_configure(Config(), paths) == EXIT_OK

    cfg = load_config(paths.config, paths.credentials)
    assert cfg.username == "20230001"
    assert cfg.password == secret
    assert secret not in capsys.readouterr().out
    if os.name != "nt":
        assert paths.credentials.stat().st_mode & 0o777 == 0o600


def test_configure_blank_input_preserves_existing_account(tmp_path, monkeypatch):
    paths = make_paths(tmp_path)
    cfg = Config(username="old-user", password="old-password")
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "")

    assert cmd_configure(cfg, paths) == EXIT_OK

    saved = load_config(paths.config, paths.credentials)
    assert saved.username == "old-user"
    assert saved.password == "old-password"


def test_configure_rejects_missing_credentials(tmp_path, monkeypatch, capsys):
    paths = make_paths(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    monkeypatch.setattr("getpass.getpass", lambda _prompt: "")

    assert cmd_configure(Config(), paths) == EXIT_ERROR
    assert "不能为空" in capsys.readouterr().err
    assert not paths.credentials.exists()
