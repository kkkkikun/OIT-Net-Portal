"""配置与凭据加载：默认值 < config.toml < 环境变量（OIT_PORTAL_USERNAME / OIT_PORTAL_PASSWORD）。"""

from __future__ import annotations

import ipaddress
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

try:  # Python 3.11+ 内置；3.10 用 tomli（见 requirements.txt）
    import tomllib as _toml
except ImportError:  # pragma: no cover
    try:
        import tomli as _toml
    except ImportError:
        _toml = None

ENV_USERNAME = "OIT_PORTAL_USERNAME"
ENV_PASSWORD = "OIT_PORTAL_PASSWORD"

DEFAULT_PROBE_URLS = [
    "http://connect.rom.miui.com/generate_204",
    "http://captive.apple.com/hotspot-detect.html",
    "http://www.qualcomm.cn/generate_204",
]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class ProbeConfig:
    urls: list[str] = field(default_factory=lambda: list(DEFAULT_PROBE_URLS))
    online_interval_sec: int = 60        # 稳定在线时的巡检间隔
    post_online_interval_sec: int = 15   # 上线后短窗内的密集复查
    post_online_window_sec: int = 300
    offline_interval_sec: int = 30        # 无网络时仅探测的间隔
    recovery_burst_sec: int = 60          # 网络恢复后 burst 探测窗口
    recovery_burst_interval_sec: int = 5  # burst 期间探测间隔
    wifi_ssid: str = ""                   # 校园网 SSID（Termux 专用，触发 burst）
    jitter_ratio: float = 0.2            # 间隔 ±20% 抖动


@dataclass
class RetryConfig:
    max_attempts: int = 5                # 连续失败告警阈值
    backoff_base_sec: int = 5            # 5→10→20→40→80
    backoff_cap_sec: int = 300
    deep_backoff_sec: int = 600          # 告警后的深度退避
    min_relogin_interval_sec: int = 300  # 两次账密登录的最小间隔（防风暴）


@dataclass
class KeepaliveConfig:
    traffic_keepalive: bool = False      # 依抓包结论（C4.3/C4.4）决定是否开启
    keepalive_url: str = ""              # <CAPTURE:C-4> 心跳或轻量资源 URL
    keepalive_interval_sec: int = 180


@dataclass
class AdvancedConfig:
    user_agent: str = DEFAULT_USER_AGENT
    timeout_sec: int = 8
    eportal_host: str = "172.16.11.54"
    bypass_vpn: bool = False            # 认证请求绑定物理网卡，不经过系统 VPN 路由
    direct_source_ip: str = ""          # 物理网卡 IPv4；空 = 自动识别


@dataclass
class Config:
    username: str | None = None
    password: str | None = None
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    keepalive: KeepaliveConfig = field(default_factory=KeepaliveConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    config_path: Path | None = None
    credentials_path: Path | None = None


def _apply_section(target: object, data: dict) -> list[str]:
    """把 TOML 小节写进 dataclass，返回未知键（用于告警）。"""
    unknown = []
    for key, value in data.items():
        if hasattr(target, key):
            setattr(target, key, value)
        else:
            unknown.append(key)
    return unknown


def load_config(config_path: Path | None = None,
                credentials_path: Path | None = None) -> Config:
    cfg = Config(config_path=config_path, credentials_path=credentials_path)

    def _load_toml(path: Path | None) -> dict:
        if path is None or not path.is_file() or _toml is None:
            return {}
        with open(path, "rb") as fh:
            return _toml.load(fh)

    data = _load_toml(config_path)
    if "account" in data:
        cfg.username = data["account"].get("username", cfg.username)
    if "probe" in data:
        _apply_section(cfg.probe, data["probe"])
    if "retry" in data:
        _apply_section(cfg.retry, data["retry"])
    if "keepalive" in data:
        _apply_section(cfg.keepalive, data["keepalive"])
    if "advanced" in data:
        _apply_section(cfg.advanced, data["advanced"])

    # 凭据独立文件，与配置分离
    creds = _load_toml(credentials_path)
    password = creds.get("password")

    # 环境变量覆盖
    cfg.username = os.environ.get(ENV_USERNAME, cfg.username)
    cfg.password = os.environ.get(ENV_PASSWORD, password)

    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    if cfg.probe.online_interval_sec <= 0 or cfg.probe.offline_interval_sec <= 0:
        raise ValueError("探测间隔必须为正数（probe.online_interval_sec / offline_interval_sec）")
    if not 0 <= cfg.probe.jitter_ratio <= 1:
        raise ValueError("probe.jitter_ratio 必须在 [0, 1] 之间")
    if not cfg.probe.urls:
        raise ValueError("probe.urls 不能为空")
    if cfg.retry.backoff_base_sec <= 0 or cfg.retry.max_attempts <= 0:
        raise ValueError("retry 参数必须为正数")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _update_toml_section(path: Path, section_name: str, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = (path.read_text(encoding="utf-8") if path.is_file() else "").splitlines(keepends=True)
    section = None
    section_start = None
    found = set()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*\[([^]]+)\]", line)
        if match:
            section = match.group(1).strip()
            if section == section_name and section_start is None:
                section_start = index
            continue
        if section != section_name:
            continue
        key = re.match(r"^\s*([A-Za-z0-9_-]+)\s*=", line)
        if key and key.group(1) in values:
            name = key.group(1)
            lines[index] = f"{name} = {values[name]}\n"
            found.add(name)
    missing = [(key, value) for key, value in values.items() if key not in found]
    if section_start is None:
        lines[0:0] = [f"[{section_name}]\n",
                      *(f"{key} = {value}\n" for key, value in missing), "\n"]
    else:
        lines[section_start + 1:section_start + 1] = [
            f"{key} = {value}\n" for key, value in missing]
    path.write_text("".join(lines), encoding="utf-8")


def save_account(config_path: Path, credentials_path: Path,
                 username: str, password: str) -> None:
    username = username.strip()
    if not username or not password:
        raise ValueError("账号和密码不能为空")
    _update_toml_section(config_path, "account", {"username": _toml_string(username)})
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    credentials_path.write_text(
        f"password = {_toml_string(password)}\n", encoding="utf-8")
    if os.name != "nt":
        credentials_path.chmod(0o600)


def save_network_settings(config_path: Path, bypass_vpn: bool,
                          direct_source_ip: str = "") -> None:
    source_ip = direct_source_ip.strip()
    if source_ip:
        try:
            address = ipaddress.IPv4Address(source_ip)
        except ipaddress.AddressValueError as exc:
            raise ValueError("物理网卡地址必须是有效的 IPv4 地址") from exc
        if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast:
            raise ValueError("物理网卡地址不能是回环、链路本地或组播地址")
    _update_toml_section(config_path, "advanced", {
        "bypass_vpn": "true" if bypass_vpn else "false",
        "direct_source_ip": _toml_string(source_ip),
    })
