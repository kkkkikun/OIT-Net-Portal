# Linux 一键安装与离线包

适用于使用 systemd 的 Linux 发行版，首发目标为 Ubuntu 22.04 / Python 3.10，包括 Jetson Nano（aarch64）。守护进程以 **systemd 系统服务**运行：开机自启、崩溃自动重启，无需登录桌面。

## 推荐：离线安装包

根据设备 CPU 架构下载对应压缩包：

- 普通 Intel/AMD 电脑或虚拟机：`oit-portal-linux-x86_64.tar.gz`
- Jetson Nano 等 ARM64 设备：`oit-portal-linux-aarch64.tar.gz`

以使用校园网的普通用户执行：

```bash
tar -xzf oit-portal-linux-x86_64.tar.gz   # ARM64 换成对应文件名
cd oit-portal-linux-x86_64
./install.sh
```

安装器会依次完成：

1. 检查 systemd、Python 和 venv，拒绝 root 直跑。
2. 在 `~/.local/share/oit-portal/venv` 创建独立环境，使用包内 wheelhouse **离线安装全部依赖**。
3. 复制默认配置，通过交互式 `configure` 输入账号密码；密码不回显，凭据文件权限为 0600。
4. 注册并启动 `oit-portal.service`，创建 `~/.local/bin/oit-portal` 命令入口。
5. 检查服务并试跑一次登录。没有连接校园网时可使用 `./install.sh --skip-login` 跳过试登。

目标机只需 Python 和 venv，不需要联网下载 pip 依赖。Ubuntu/Debian 缺少前置组件时：

```bash
sudo apt install python3 python3-venv
```

> 离线包中的部分 wheel 与 Python 小版本相关。请使用与包内 `BUILD-INFO` 的 `build_python` 相同 Python 主/次版本；当前基线为 Python 3.10。安装器会提前检查并给出明确错误。重复运行安装脚本可升级应用，已有账号密码可直接回车保留。

## 验证与日常使用

```bash
systemctl status oit-portal           # active (running)
oit-portal status                     # online / captive / offline
journalctl -u oit-portal -n 20        # 最近服务日志
```

- 重启设备后服务自动运行，无需登录桌面。
- 文件日志：`~/.config/oit-portal/logs/oit-portal.log`
- 如果找不到 `oit-portal`，把 `~/.local/bin` 加入 PATH，或直接使用 `~/.local/bin/oit-portal`。
- 首次协议适配仍需按 [抓包指南](capture-guide.md) 操作；校园网要求验证码时按 `oit-portal login-info` 引导人工登录。

## 修改账号与服务管理

```bash
oit-portal configure                  # 修改账号密码，回车保留原值
sudo systemctl restart oit-portal     # 修改后重启服务
sudo systemctl stop oit-portal        # 停止；start 可恢复
systemctl is-enabled oit-portal       # 查看开机自启状态
```

账号写入 `~/.config/oit-portal/config.toml`，密码独立写入 `credentials.toml`。配置命令会正确转义引号、反斜杠和非 ASCII 字符，不需要手工用 sed 修改。

## VPN 下使用物理网卡认证

新安装配置默认启用 `bypass_vpn`。认证 Session 会把 HTTP/HTTPS socket 绑定到物理网卡 IPv4，其他流量继续走 VPN，不修改系统路由，也不需要 root：

```toml
[advanced]
bypass_vpn = true
direct_source_ip = ""  # 空 = 自动识别；也可填 "172.18.10.25"
```

用 `ip address` 和 `ip route` 找到校园 Wi‑Fi/有线接口地址；不要选择 `tun`、`tap`、`wg`、`ppp` 等 VPN 接口。修改后执行 `sudo systemctl restart oit-portal`。切换网卡或 DHCP 地址变化后需要重启服务。

自动识别失败时日志会提示并回退系统默认路由，此时请手动填写 `direct_source_ip`。VPN 的 kill switch、强制全隧道或管理员限制仍可能阻止直连；工具不会关闭 VPN 或绕过其安全策略。

## 卸载

在解压后的安装包目录执行：

```bash
./uninstall.sh           # 停服务、删应用和命令入口，保留配置/凭据/日志
./uninstall.sh --purge   # 连同配置、凭据、会话和日志一起删除
```

请以原安装用户运行，不要使用 root。卸载也会清理旧版 `pip --user` 安装。

## 从源码安装

需要 Python >=3.9、venv 和构建阶段网络。与离线包相同，运行环境固定在用户目录，不使用 `pip --user`，不会污染系统 Python：

```bash
cd ~/OIT-Net-Portal
bash scripts/install_linux.sh
```

## 构建自己的离线包

在目标架构的 Linux 环境执行：

```bash
bash scripts/build_linux.sh
```

构建阶段需要联网下载 wheel 或已有完整 pip 缓存，产物为：

```text
dist/oit-portal-linux-<arch>.tar.gz
dist/oit-portal-linux-<arch>.tar.gz.sha256
```

- x86_64 包在 x86_64 Linux 构建。
- Jetson/aarch64 包在 Jetson 或其他 aarch64 Linux 原生构建；不要用 x86 包冒充 ARM 包。
- 建议使用目标系统的 Python 版本构建，当前验证基线为 Ubuntu 22.04 / Python 3.10。
- 可通过标准 `PIP_INDEX_URL` 环境变量临时选择可用镜像，无需修改脚本。
- 包内只有安装脚本、service 模板、配置模板、说明和 wheelhouse，不包含真实凭据、会话、日志或 Git 历史。

## WiFi SSID 触发加速（可选）

编辑 `~/.config/oit-portal/config.toml`：

```toml
[probe]
wifi_ssid = "你的校园网SSID"
```

然后 `sudo systemctl restart oit-portal`。SSID 读取链为 `nmcli` → `iwgetid`，两者都没有时该功能静默失效，不影响常规探测。可提前运行 `nmcli -t -f ACTIVE,SSID dev wifi` 确认能读到 `yes:SSID`。

## 常见问题

| 现象 | 处理 |
|------|------|
| 提示 Python 小版本不匹配 | 使用 `BUILD-INFO` 对应版本，或在目标机器从源码重新构建/安装 |
| 无法创建 venv | Ubuntu/Debian 执行 `sudo apt install python3-venv` 后重试 |
| 服务反复重启 | `journalctl -u oit-portal -n 50` 查看错误；修复后 `sudo systemctl reset-failed oit-portal` |
| 修改密码不生效 | `oit-portal configure` 后执行 `sudo systemctl restart oit-portal` |
| `nmcli: command not found` | 只影响 SSID 加速，可安装 `network-manager` 或忽略 |
| 想确认崩溃自愈 | `sudo systemctl kill --signal=SIGKILL oit-portal`；5 秒内应恢复，`systemctl show -p NRestarts oit-portal` 次数增加 |
| Jetson 时间异常 | Jetson Nano 无 RTC，断电久后可能时钟漂移；用 `timedatectl` 检查并配置 NTP |
