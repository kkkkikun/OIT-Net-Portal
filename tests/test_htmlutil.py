"""HTML 解析工具：表单字段提取、RSA 公钥发现、验证码检测。"""

from oit_portal import htmlutil

# 典型统一身份认证登录页（结构参考 CAS/自研 SSO 常见形态）
LOGIN_PAGE = """
<html><body>
<form id="loginForm" action="/auth/user/login" method="post">
  <input type="text" name="username" placeholder="学号/工号">
  <input type="password" name="password">
  <input type="hidden" name="lt" value="LT-1024-ticket">
  <input type="hidden" name="execution" value="e1s1">
  <input type="hidden" name="_eventId" value="submit">
  <button type="submit">登 录</button>
</form>
<script src="/static/js/login.js"></script>
</body></html>
"""

CAPTCHA_PAGE = """
<form action="/login">
  <input name="account"><input type="password" name="pwd">
  <img src="/captcha/image.jsp" id="vcodeImg">
  <input name="validcode">
</form>
"""

PEM_KEY = "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqTEST\n-----END PUBLIC KEY-----"
# 真实形态：单串完整 base64 公钥（约 160 字符）
JS_RSA_PAGE = ('<script>var publicKey = "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQC7TEST'
               '0123456789abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ";</script>')


def test_form_action():
    assert htmlutil.form_action(LOGIN_PAGE) == "/auth/user/login"


def test_inputs_parse():
    fields = htmlutil.inputs(LOGIN_PAGE)
    names = [n for n, _v, _t in fields]
    assert names == ["username", "password", "lt", "execution", "_eventId"]
    by_name = dict((n, v) for n, v, _t in fields)
    assert by_name["lt"] == "LT-1024-ticket"
    types = {n: t for n, _v, t in fields}
    assert types["password"] == "password"
    assert types["lt"] == "hidden"


def test_hidden_values_refresh():
    fresh = htmlutil.hidden_values(
        LOGIN_PAGE.replace("LT-1024-ticket", "LT-2048-new"), ["lt", "execution", "absent"])
    assert fresh == {"lt": "LT-2048-new", "execution": "e1s1"}


def test_find_rsa_key_pem():
    key, source = htmlutil.find_rsa_key(f"var x=1; {PEM_KEY};")
    assert key == PEM_KEY
    assert "PEM" in source


def test_find_rsa_key_js_var():
    key, source = htmlutil.find_rsa_key(JS_RSA_PAGE)
    assert key.startswith("MIGfMA0GCSqGSIb3")
    assert "JS" in source


def test_find_rsa_key_absent():
    assert htmlutil.find_rsa_key(LOGIN_PAGE)[0] is None


def test_captcha_detection():
    has, reason = htmlutil.looks_like_captcha(CAPTCHA_PAGE)
    assert has and reason


def test_no_captcha_on_plain_form():
    assert htmlutil.looks_like_captcha(LOGIN_PAGE) == (False, "")


def test_script_sources():
    assert htmlutil.script_sources(LOGIN_PAGE) == ["/static/js/login.js"]


# 用户学校登录页的真实内联加密脚本（2026-10-09 抓包报告）
VUE_ENCRYPT_SCRIPT = """
Vue.prototype.$encrypt = function(str) {
    key = CryptoJS.enc.Utf8.parse('563a38b893f98998d4917875837ee800'.substr(0,16));
    iv = CryptoJS.enc.Utf8.parse('563a38b893f98998d4917875837ee800'.substr(0,16));
    var encrypted = CryptoJS.AES.encrypt(str, key, {
        iv: iv,
        mode: CryptoJS.mode.CBC,
        padding: CryptoJS.pad.ZeroPadding
    });
    return encrypted;
}
"""


def test_find_aes_from_real_page_script():
    aes = htmlutil.find_aes(VUE_ENCRYPT_SCRIPT)
    assert aes is not None
    assert aes["key"] == "563a38b893f98998"
    assert aes["iv"] == "563a38b893f98998"
    assert aes["mode"] == "CBC"
    assert aes["padding"] == "zero"


def test_find_aes_pkcs7_variant():
    aes = htmlutil.find_aes(
        "k=CryptoJS.enc.Utf8.parse('0123456789abcdef');"
        "CryptoJS.AES.encrypt(s,k,{mode:CryptoJS.mode.ECB,"
        "padding:CryptoJS.pad.Pkcs7})")
    assert aes["key"] == "0123456789abcdef"
    assert aes["iv"] == "0123456789abcdef"  # 仅一个 parse 时 iv 同 key
    assert aes["mode"] == "ECB"
    assert aes["padding"] == "pkcs7"


def test_find_aes_absent_without_marker():
    assert htmlutil.find_aes(LOGIN_PAGE) is None
