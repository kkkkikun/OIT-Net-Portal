"""认证网络会话：禁用环境代理，并可绑定物理网卡绕过 VPN 路由。"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
import sys

import requests
from requests.adapters import HTTPAdapter

from .config import Config
from .log import get_logger

logger = get_logger()

_VPN_NAMES = (
    "tun", "tap", "wireguard", "wg", "ppp", "vpn", "tailscale", "zerotier",
    "openvpn", "clash", "sing-box", "wsl", "hyper-v", "vmware", "virtualbox",
    "loopback", "bluetooth", "docker", "virbr", "veth", "br-",
)
_PHYSICAL_NAMES = ("wlan", "wi-fi", "wifi", "无线", "ethernet", "以太网", "eth", "enp", "eno", "ens", "enx")


def validate_source_ip(value: str) -> str:
    try:
        address = ipaddress.IPv4Address(value.strip())
    except ipaddress.AddressValueError as exc:
        raise ValueError("物理网卡地址必须是有效的 IPv4 地址") from exc
    if address.is_unspecified or address.is_loopback or address.is_link_local or address.is_multicast:
        raise ValueError("物理网卡地址不能是 0.0.0.0、回环、链路本地或组播地址")
    return str(address)


def _usable_address(value: str) -> str | None:
    try:
        return validate_source_ip(value)
    except ValueError:
        return None


def _physical_name(name: str) -> bool:
    lowered = name.lower()
    return (any(hint in lowered for hint in _PHYSICAL_NAMES)
            and not any(hint in lowered for hint in _VPN_NAMES))


def _linux_source_ip() -> str | None:
    try:
        addresses = subprocess.run(
            ["ip", "-j", "address", "show"], capture_output=True, text=True,
            timeout=3, check=False,
        )
        routes = subprocess.run(
            ["ip", "-j", "route", "show", "default"], capture_output=True,
            text=True, timeout=3, check=False,
        )
        if addresses.returncode != 0:
            return None
        interfaces = json.loads(addresses.stdout)
        default_devices = ({item.get("dev") for item in json.loads(routes.stdout)}
                           if routes.returncode == 0 else set())
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        return None

    candidates = []
    for interface in interfaces:
        name = interface.get("ifname", "")
        if not _physical_name(name) or "UP" not in interface.get("flags", []):
            continue
        for info in interface.get("addr_info", []):
            if info.get("family") != "inet" or info.get("scope") != "global":
                continue
            address = _usable_address(info.get("local", ""))
            if address:
                candidates.append((name not in default_devices, name, address))
    return min(candidates)[2] if candidates else None


def _windows_source_ip() -> str | None:
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    candidates = []
    for block in re.split(r"\r?\n\r?\n", result.stdout):
        heading = block.splitlines()[0] if block.splitlines() else ""
        if not _physical_name(heading):
            continue
        match = re.search(
            r"IPv4[^\r\n:]*:\s*((?:\d{1,3}\.){3}\d{1,3})", block, re.I)
        gateway = re.search(r"(?:Gateway|网关)[^\r\n]*((?:\d{1,3}\.){3}\d{1,3})", block, re.I)
        address = _usable_address(match.group(1)) if match else None
        if address and gateway:
            candidates.append((0 if any(x in heading.lower() for x in ("wi-fi", "wifi", "wlan")) else 1,
                               heading, address))
    return min(candidates)[2] if candidates else None


def physical_source_ip() -> str | None:
    if sys.platform == "win32":
        return _windows_source_ip()
    if sys.platform == "linux":
        return _linux_source_ip()
    return None


class SourceAddressAdapter(HTTPAdapter):
    def __init__(self, source_ip: str, *args, **kwargs):
        self.source_ip = validate_source_ip(source_ip)
        super().__init__(*args, **kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs["source_address"] = (self.source_ip, 0)
        return super().init_poolmanager(connections, maxsize, block, **pool_kwargs)


def create_session(cfg: Config) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = cfg.advanced.user_agent
    session.trust_env = False
    if not cfg.advanced.bypass_vpn:
        return session

    source_ip = cfg.advanced.direct_source_ip.strip()
    if source_ip:
        source_ip = validate_source_ip(source_ip)
    else:
        source_ip = physical_source_ip() or ""
    if not source_ip:
        logger.warning("已启用 VPN 直连，但未识别到物理网卡 IPv4；本次使用系统默认路由")
        return session
    session.mount("http://", SourceAddressAdapter(source_ip))
    session.mount("https://", SourceAddressAdapter(source_ip))
    logger.info("校园网认证请求绑定物理网卡 IPv4=%s", source_ip)
    return session
