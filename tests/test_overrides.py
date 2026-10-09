"""protocol.json 覆盖机制。"""

import json
from types import SimpleNamespace

from oit_portal.protocol_overrides import apply_overrides


def test_missing_file_is_noop(tmp_path):
    ns = SimpleNamespace(a=1)
    assert apply_overrides(ns, "sso", tmp_path / "none.json") == []
    assert ns.a == 1


def test_apply_known_keys_only(tmp_path):
    p = tmp_path / "protocol.json"
    p.write_text(json.dumps({"sso": {"login_endpoint": "/auth/login",
                                     "password_encrypt": "rsa",
                                     "bogus_key": "x"},
                             "eportal": {"online_mode": "direct"}}), encoding="utf-8")
    sso = SimpleNamespace(login_endpoint="old", password_encrypt="none")
    applied = apply_overrides(sso, "sso", p)
    assert applied == ["login_endpoint", "password_encrypt"]
    assert sso.login_endpoint == "/auth/login" and sso.password_encrypt == "rsa"

    eportal = SimpleNamespace(online_mode="sso_pass")
    assert apply_overrides(eportal, "eportal", p) == ["online_mode"]
    assert eportal.online_mode == "direct"


def test_broken_file_is_ignored(tmp_path):
    p = tmp_path / "protocol.json"
    p.write_text("{not json", encoding="utf-8")
    ns = SimpleNamespace(a=1)
    assert apply_overrides(ns, "sso", p) == []
    assert ns.a == 1


def test_section_absent_is_noop(tmp_path):
    p = tmp_path / "protocol.json"
    p.write_text(json.dumps({"eportal": {}}), encoding="utf-8")
    ns = SimpleNamespace(a=1)
    assert apply_overrides(ns, "sso", p) == []
