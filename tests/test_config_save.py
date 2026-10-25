from __future__ import annotations

import pytest

from oit_portal.config import load_config, save_account


def test_save_account_preserves_other_settings_and_separates_password(tmp_path):
    config = tmp_path / "config.toml"
    credentials = tmp_path / "nested" / "credentials.toml"
    config.write_text(
        '[account]\nusername = "old"\n\n[probe]\nonline_interval_sec = 123\n',
        encoding="utf-8",
    )

    save_account(config, credentials, " 20230001 ", 'p"a\\ss\n密码')

    assert 'username = "20230001"' in config.read_text(encoding="utf-8")
    assert "online_interval_sec = 123" in config.read_text(encoding="utf-8")
    assert "p\"a" not in config.read_text(encoding="utf-8")
    cfg = load_config(config, credentials)
    assert cfg.username == "20230001"
    assert cfg.password == 'p"a\\ss\n密码'
    assert cfg.probe.online_interval_sec == 123


def test_save_account_adds_missing_section(tmp_path):
    config = tmp_path / "config.toml"
    credentials = tmp_path / "credentials.toml"
    config.write_text("[advanced]\ntimeout_sec = 9\n", encoding="utf-8")

    save_account(config, credentials, "student", "secret")

    cfg = load_config(config, credentials)
    assert cfg.username == "student"
    assert cfg.advanced.timeout_sec == 9


@pytest.mark.parametrize("username,password", [("", "secret"), ("user", "")])
def test_save_account_rejects_empty_values(tmp_path, username, password):
    with pytest.raises(ValueError, match="不能为空"):
        save_account(tmp_path / "config.toml", tmp_path / "credentials.toml",
                     username, password)
    assert not (tmp_path / "credentials.toml").exists()
