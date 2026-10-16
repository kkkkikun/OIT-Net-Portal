<p align="center">
  <img src="assets/logo.svg" width="150" alt="OIT-Net-Portal logo">
</p>

<h1 align="center">OIT-Net-Portal</h1>

<p align="center">
  <strong>鄂尔多斯应用技术学院校园网 · 静默自动登录 + 保持登录态</strong>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&logoColor=white" alt="Python 3.9+"></a>
  <img src="https://img.shields.io/badge/tests-114%20passed-brightgreen" alt="114 tests passed">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License"></a>
</p>

<p align="center">
  <strong>Windows 计划任务</strong> · <strong>Android Termux</strong> · <strong>Linux systemd</strong> — 单 Python 代码库三端共用
</p>

```
探测(generate_204) ──在线──► 巡逻等待(60s±20%)
      │302劫持
解析挑战(加密参数透传) ─► SSO会话复用(免密) ─失败─► 账密登录 ─► ePortal上线 ─► 复测确认
```

## ✨ 特性

- **协议抓包自配置**：登录协议不写死，`oit-portal capture` 向导一键自动发现（SSO 端点 / AES 加密 / ePortal 上线方式），写入用户目录 `protocol.json`
- **全链路自动化**：探测 → SSO OAuth 免密复用 / 账密登录 → 锐捷 ePortal 上线 → 复测确认 → 轮询保活
- **三端后台守护**：断网自动重连、指数退避、网络恢复 burst 探测、WiFi SSID 触发加速
- **安全设计**：密码独立存放（0600）、日志脱敏（4 位指纹）、直连不代理、敏感文件不入库

## 🚀 快速开始

```bash
pip install -e .
oit-portal capture     # 首次：协议自配置（校内未登录状态运行，约 2 分钟）
oit-portal status      # online / captive / offline 三态探测
python -m pytest       # 114 个用例（无网络）
```

### 各平台一键部署

| 平台 | 命令 | 自启方式 | 文档 |
|------|------|----------|------|
| **Windows** | `scripts\install_windows.ps1` | 计划任务（登录自启 + 崩溃重启） | [windows-setup](docs/windows-setup.md) |
| **Android Termux** | `bash scripts/install_termux.sh` | Termux:Boot + 电池豁免 | [termux-setup](docs/termux-setup.md) |
| **Linux (systemd)** | `bash scripts/install_linux.sh` | 系统服务（开机自启 + 崩溃自愈） | [linux-setup](docs/linux-setup.md) |

## 📖 命令一览

| 命令 | 作用 |
|------|------|
| `oit-portal capture` | **一键抓包向导**：自动发现登录协议并自配置（首次使用先跑这个，[指南](docs/capture-guide.md)） |
| `oit-portal status` | 探测当前状态（online / captive / offline） |
| `oit-portal once` | 完整登录一次（退出码 0 成功 / 1 失败 / 2 无网络） |
| `oit-portal daemon` | 常驻守护：自动登录 + 保活 + 退避重试 |
| `oit-portal stop` | 停止守护 |
| `oit-portal login-info` | 验证码/会话失效时的人工登录引导 |

## ⚙️ 保活策略

| 状态 | 行为 |
|------|------|
| 在线（稳定） | 60s ± 20% 巡检 |
| 刚上线 5 分钟内 | 15s 密集复查（捕获快速被踢） |
| 登录失败 | 指数退避 5→10→20→40s；连续 5 次失败 → 深度退避 600s + ERROR 告警 |
| 无网络 | 30s 仅探测（不消耗登录尝试） |
| 网络恢复 / 连上校园网 SSID | burst 窗口 5s 探测一次，秒级重登 |
| 账密重登 | 最小间隔 300s（防风控风暴） |

## 🔒 配置与安全

- 配置 `~/.config/oit-portal/config.toml`（Windows: `%APPDATA%\oit-portal\`），模板见 [`config.example.toml`](config.example.toml)
- **密码不放配置文件**：独立 `credentials.toml`（0600 权限）或环境变量 `OIT_PORTAL_PASSWORD`
- 日志永不记录明文密码与完整 cookie（只记 4 位指纹）；`session.json` 持久化 SSO 会话实现免密复用
- 协议确认状态清单见 [docs/protocol-notes.md](docs/protocol-notes.md)；向导失败时按[兜底流程](docs/capture-guide.md)提交脱敏报告

## ⚠️ 免责声明

本项目仅供**个人学习研究**与便捷接入本人已获授权的校园网，不含任何绕过、破解行为；
登录使用的账号密码为你本人凭据。请遵守学校网络使用规定；因使用本工具造成的任何后果由使用者自行承担。

## 许可

MIT
