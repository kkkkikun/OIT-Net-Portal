"""ePortal 上线判定：漏标 Content-Encoding 的 gzip 响应体兼容（学生网实测坑）。"""

import gzip

import requests

from oit_portal.auth.eportal import EportalAdapter

from conftest import make_config


def _resp(body: bytes, *, content_type: str = "text/html") -> requests.Response:
    resp = requests.Response()
    resp.status_code = 200
    resp._content = body
    resp.headers["Content-Type"] = content_type
    return resp


def _adapter(cfg) -> EportalAdapter:
    # _judge 不触网；apply_protocol_overrides=False 保证判定只依赖 CAPTURED 常量
    return EportalAdapter(session=None, cfg=cfg, apply_protocol_overrides=False)


def test_plain_utf8_success_page_still_judged_online(cfg=None):
    cfg = make_config()
    body = "认证成功！<script>var userIndex='aabb0011';var keepaliveInterval=0;</script>"
    result = _adapter(cfg)._judge(_resp(body.encode("utf-8")), mode="sso_pass")
    assert result.success
    assert result.user_index == "aabb0011"


def test_gzip_body_without_content_encoding_header_is_decoded():
    cfg = make_config()
    body = "认证成功！<script>var userIndex='ff00aa';</script>".encode("utf-8")
    # 学生网实测形态：gzip 压缩但无 Content-Encoding 头
    result = _adapter(cfg)._judge(_resp(gzip.compress(body)), mode="sso_pass")
    assert result.success
    assert result.user_index == "ff00aa"


def test_gzip_body_with_gbk_charset_is_decoded():
    cfg = make_config()
    body = "校园网认证成功，userIndex='00ff11'".encode("gb18030")
    result = _adapter(cfg)._judge(_resp(gzip.compress(body)), mode="sso_pass")
    assert result.success
    assert result.user_index == "00ff11"


def test_plain_failure_page_still_judged_failed():
    cfg = make_config()
    result = _adapter(cfg)._judge(_resp("账号已在线终端数超限".encode("utf-8")),
                                  mode="sso_pass")
    assert not result.success


def test_corrupt_gzip_body_does_not_crash():
    cfg = make_config()
    result = _adapter(cfg)._judge(
        _resp(b"\x1f\x8b\x08" + "损坏的压缩体".encode("utf-8")), mode="sso_pass")
    assert not result.success


def test_garbled_body_without_marker_judged_failed():
    """修复前形态回归：乱码且无标记 → FAILED（不伪造上线）。"""
    cfg = make_config()
    result = _adapter(cfg)._judge(_resp(b"\x00\x01binarygarbage\x02\x03"),
                                  mode="sso_pass")
    assert not result.success
