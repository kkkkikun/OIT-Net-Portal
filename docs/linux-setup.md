# Linux（systemd）部署指南

适用于 systemd 的 Linux 发行版（以 Jetson Nano / Ubuntu 22.04 aarch64 为目标实测平台）。
守护进程以 **systemd 系统服务**运行：开机自启、崩溃自动重启，无需登录。

## 前置要求

1. systemd（`systemctl --version` 有输出即可）
2. Python >= 3.9（Ubuntu 22.04 自带 3.10 ✅；没有则 `sudo apt install python3 python3-pip`）
3. sudo 权限（仅安装/卸载 systemd unit 时需要；装包、配置、凭据都写在用户目录，不需要 sudo）
4. 可选（WiFi SSID 触发加速用）：`sudo apt install network-manager wireless-tools`

## 安装步骤

```bash
# 1. 以「运行 daemon 的目标普通用户」身份进入项目目录
cd ~/OIT-Net-Portal

# 2. 一键安装（装包 + 写配置/凭据 + 装 systemd 服务 + 试跑）
bash scripts/install_linux.sh
```

安装脚本会依次：检查 python3/pip → `pip install --user .`（不碰系统 site-packages）→
生成 `~/.config/oit-portal/config.toml`（询问账号）→ 写 `credentials.toml`（询问密码，600 权限）→
`sudo tee` systemd unit 到 `/etc/systemd/system/oit-portal.service` 并 `enable --now` → 试跑一次 `oit-portal once`。

> **请勿以 root 运行安装脚本**——脚本会拒绝。daemon 以执行脚本的用户身份运行
> （`User=` 写入 unit），配置/凭据也在该用户目录下；root 直跑会让 `pip --user`
> 落到 `/root/.local` 造成属主错乱。

## 验证

```bash
systemctl status oit-portal           # active (running)
journalctl -u oit-portal -n 20        # 最近日志（应见「daemon 启动」，无密码/cookie 明文）
oit-portal status                     # online / captive / offline 三态
```

- **重启设备**：2 分钟内服务自动 active 并完成校园网登录（无需登录桌面）
- 日志双写：stdout/stderr → journald；文件日志 → `~/.config/oit-portal/logs/oit-portal.log`

## 加速校园网识别（可选，WiFi 场景）

`config.toml` 的 `[probe]` 段：

```toml
[probe]
wifi_ssid = "你的校园网SSID"        # 连上该 SSID 时 3s 内触发 burst 重登；空=关闭
```

SSID 读取链：`nmcli`（NetworkManager）→ `iwgetid`（wireless-tools）→ 都没有则该功能静默失效，
**不影响登录**（与 Termux 下不装 termux-api 的行为一致）。可用
`nmcli -t -f ACTIVE,SSID dev wifi` 先确认能读到 `yes:SSID` 行再配置。

## 管理与卸载

```bash
sudo systemctl restart oit-portal     # 改配置/密码后重启生效
sudo systemctl stop oit-portal        # 停止（systemctl start 恢复）
systemctl is-enabled oit-portal       # 开机自启状态

bash scripts/uninstall_linux.sh               # 停服务 + 删 unit + 卸载包（保留配置）
bash scripts/uninstall_linux.sh --purge       # 连同 ~/.config/oit-portal 一起删
```

## 常见问题

| 现象 | 处理 |
|------|------|
| 服务 `inactive (dead)` 且手动跑过 daemon | 两者靠文件锁互斥：先 `oit-portal stop`，再 `sudo systemctl restart oit-portal` |
| 服务反复重启 | `journalctl -u oit-portal -n 50` 看报错；修复后 `sudo systemctl reset-failed oit-portal` |
| 改了密码不生效 | 改 `credentials.toml` 后 `sudo systemctl restart oit-portal` |
| `nmcli: command not found` | 只影响 SSID 触发加速；`sudo apt install network-manager` 或忽略 |
| 想确认崩溃自愈 | `sudo systemctl kill --signal=SIGKILL oit-portal` → 5s 内应自动恢复（`systemctl show -p NRestarts oit-portal` 次数 +1） |
| 时间不对导致 TLS/会话异常 | Jetson Nano 无 RTC，断电久后时钟漂移：`timedatectl` 确认，配 NTP 或先联网校时 |
| 需要验证码时 | `oit-portal login-info` 查看人工登录引导，浏览器登一次后 daemon 自动收割会话 |
