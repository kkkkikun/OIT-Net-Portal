"""配置与凭据加载：默认值 < config.toml < 环境变量（OIT_PORTAL_USERNAME / OIT_PORTAL_PASSWORD）。"""

from __future__ import annotations

import os
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
    post_online_window_sec: int = 300    # 「刚上线」窗口时长
    offline_interval_sec: int = 30       # 无网络时仅探测的间隔
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
