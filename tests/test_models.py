"""PortalChallenge 解析：加密参数原样透传，不做解读。"""

import pytest

from oit_portal.auth.models import ProtocolMismatch, PortalChallenge

from conftest import AUTHORIZE_URL, EPORTAL_CODE_URL


def test_parse_authorize_redirect():
    ch = PortalChallenge.from_redirect(AUTHORIZE_URL)
    assert ch.client_id == "b50485d1-test"
    assert ch.eportal_base == "http://172.16.11.54"
    # 加密参数原样保留（含 t=wireless-v2）
    assert "wlanuserip=deadbeef" in ch.eportal_querystring
    assert "t=wireless-v2" in ch.eportal_querystring


def test_eportal_sso_url_building():
    ch = PortalChallenge.from_redirect(AUTHORIZE_URL)
    assert ch.eportal_sso_url("CODE123") == EPORTAL_CODE_URL


def test_missing_client_id_rejected():
    bad = "http://open.oit.edu.cn:8090/auth/oauth/authorize?response_type=code"
    with pytest.raises(ProtocolMismatch):
        PortalChallenge.from_redirect(bad)


def test_non_authorize_url_rejected():
    with pytest.raises(ProtocolMismatch):
        PortalChallenge.from_redirect("http://example.com/portal")


def test_none_location_rejected_with_clear_message():
    """注入式认证页（无 302 Location）传入 None 应给出明确错误而非晦涩 TypeError。"""
    with pytest.raises(ProtocolMismatch, match="注入式"):
        PortalChallenge.from_redirect(None)
    with pytest.raises(ProtocolMismatch, match="注入式"):
        PortalChallenge.from_redirect("")
