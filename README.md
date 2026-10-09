# OIT-Net-Portal

鄂尔多斯应用技术学院校园网**静默自动登录 + 保持登录态**工具。

- **Windows**：计划任务自启 + 后台守护，断网自动重连
- **安卓**：Termux + Termux:Boot，开机/联网自动登录
- 单 Python 代码库双端共用；探测 → SSO OAuth 免密/账密 → 锐捷 ePortal 上线 → 轮询保活

```
探测(generate_204) ──在线──► 巡逻等待(60s±20%)
      │302劫持
解析挑战(加密参数透传) ─► SSO会话复用(免密) ─失败─► 账密登录 ─► ePortal上线 ─► 复测确认
```

## 当前状态

| 阶段 | 状态 |
|------|------|
| 阶段 0 协议抓取（**需要你完成**） | 🔶 一键向导 `oit-portal capture`（校内未登录状态运行，约 2 分钟，[指南](docs/capture-guide.md)）；已知：无验证码 ✅、cookie 可复用（>5h，次日失效）✅ |
| 阶段 1 核心 CLI（status / once） | ✅ 已实现（协议细节待抓包填充） |
| 阶段 2 守护与保活（daemon / stop） | ✅ 已实现 |
| 阶段 3 双端部署脚本与文档 | ✅ 已实现（Windows 侧脚本待实机验证） |
| 单元测试（27 用例，无网络依赖） | ✅ 全绿 `python -m pytest` |

> **重要**：登录协议细节（SSO 表单端点、密码加密方式、ePortal 上线方式等）由
> `oit-portal capture` 向导自动发现并写入 `protocol.json`（无则回退到
> `oit_portal/auth/sso.py` / `eportal.py` 顶部 `CAPTURED` 常量块的占位值）。
> 向导失败时按 [docs/capture-guide.md](docs/capture-guide.md) 兜底流程把脱敏报告发给维护者。
> 确认状态清单见 [docs/protocol-notes.md](docs/protocol-notes.md)。

## 快速开始

### 开发机（先跑测试与三态探测）

```bash
pip install -e .
oit-portal status    # online / captive / offline
python -m pytest     # 27 个用例
```

### Windows

见 [docs/windows-setup.md](docs/windows-setup.md)：`scripts\install_windows.ps1` 一键装（询问账密、注册计划任务、立即启动）。

### 安卓 Termux

见 [docs/termux-setup.md](docs/termux-setup.md)：`bash scripts/install_termux.sh` 一键装 + 两步必做的电池豁免设置。

## 命令

| 命令 | 作用 |
|------|------|
| `oit-portal capture` | **一键抓包向导**：自动发现登录协议并自配置（首次使用先跑这个） |
| `oit-portal status` | 探测当前状态（online / captive / offline） |
| `oit-portal once` | 完整登录一次（退出码 0 成功 / 1 失败 / 2 无网络） |
| `oit-portal daemon` | 常驻守护：自动登录 + 保活 + 退避重试 |
| `oit-portal stop` | 停止守护 |
| `oit-portal login-info` | 验证码/会话失效时的人工登录引导 |

## 配置与安全

- 配置 `~/.config/oit-portal/config.toml`（Win: `%APPDATA%\oit-portal\`），模板见 `config.example.toml`
- **密码不放配置文件**：独立 `credentials.toml`（600 权限）或环境变量 `OIT_PORTAL_PASSWORD`
- 日志永不记录明文密码与完整 cookie（只记 4 位指纹）；`session.json` 持久化 SSO 会话实现免密复用

## 保活策略

| 状态 | 行为 |
|------|------|
| 在线（稳定） | 60s ± 20% 巡检 |
| 刚上线 5 分钟内 | 15s 密集复查（捕获快速被踢） |
| 登录失败 | 指数退避 5→10→20→40s；连续 5 次失败 → 深度退避 600s + ERROR 告警 |
| 无网络 | 30s 仅探测（不消耗登录尝试） |
| 账密重登 | 最小间隔 300s（防风控风暴） |

## 免责声明

本项目仅供**个人学习研究**与便捷接入本人已获授权的校园网，不含任何绕过、破解行为；
登录使用的账号密码为你本人凭据。请遵守学校网络使用规定；因使用本工具造成的任何后果由使用者自行承担。

## 许可

MIT
