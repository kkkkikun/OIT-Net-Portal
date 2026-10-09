"""AES 密码加密复现（CryptoJS 兼容）：ZeroPadding 语义 + base64 输出 + 往返。"""

import base64

import pytest

from oit_portal.auth.sso import _aes_encrypt

KEY = IV = "563a38b893f98998"  # 用户学校实测密钥


def test_zero_padding_block_semantics():
    """CryptoJS ZeroPadding：已对齐不补整块（区别于 PKCS7）。"""
    out = _aes_encrypt("0123456789abcde", KEY, IV, "aes_cbc", "zero")  # 15 字节 → 补 1
    assert len(base64.b64decode(out)) == 16
    out16 = _aes_encrypt("0123456789abcdef", KEY, IV, "aes_cbc", "zero")  # 恰 16 字节
    assert len(base64.b64decode(out16)) == 16              # 不追加整块
    out17 = _aes_encrypt("0123456789abcdefg", KEY, IV, "aes_cbc", "zero")  # 17 → 补 15
    assert len(base64.b64decode(out17)) == 32


def test_pkcs7_always_pads():
    from Crypto.Cipher import AES
    out = _aes_encrypt("0123456789abcdef", KEY, IV, "aes_cbc", "pkcs7")
    raw = base64.b64decode(out)
    assert len(raw) == 32
    dec = AES.new(KEY.encode(), AES.MODE_CBC, IV.encode()).decrypt(raw)
    assert dec[-1] == 16  # 解密后可见 PKCS7 补了 16 个 0x10


def test_roundtrip_decrypt():
    """用相同 key/iv 解密应还原明文（验证加密格式与 CryptoJS 输出兼容）。"""
    from Crypto.Cipher import AES
    plaintext = "my-secret-P@ss"
    out = _aes_encrypt(plaintext, KEY, IV, "aes_cbc", "zero")
    raw = base64.b64decode(out)
    dec = AES.new(KEY.encode(), AES.MODE_CBC, IV.encode()).decrypt(raw)
    assert dec.rstrip(b"\x00").decode("utf-8") == plaintext


def test_ecb_mode():
    from Crypto.Cipher import AES
    import base64 as b64
    plaintext = "ecb-mode-test"
    out = _aes_encrypt(plaintext, KEY, IV, "aes_ecb", "zero")
    raw = b64.b64decode(out)
    assert len(raw) == 16
    dec = AES.new(KEY.encode(), AES.MODE_ECB).decrypt(raw)
    assert dec.rstrip(b"\x00").decode() == plaintext


def test_deterministic():
    assert (_aes_encrypt("x", KEY, IV, "aes_cbc", "zero")
            == _aes_encrypt("x", KEY, IV, "aes_cbc", "zero"))


def test_bad_key_length_raises():
    from oit_portal.auth.models import ProtocolMismatch
    with pytest.raises(ProtocolMismatch):
        _aes_encrypt("x", "short", IV, "aes_cbc", "zero")
