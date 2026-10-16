# References Spec — oit-portal

> 版本: 1.0.0 | 最后更新: 2026-10-16

## Purpose

记录项目依赖与外部参考资源，确保依赖可追溯、资源可获取。

## Requirements

### Requirement: 依赖版本记录

外部依赖 MUST 记录版本与用途。

#### Scenario: 添加新依赖

- **WHEN** 引入新依赖到 pyproject.toml
- **THEN** 更新下方依赖表：名称 / 版本约束 / 用途 / 官方链接

### Requirement: 外部资源记录

重要的外部文档与工具 MUST 登记。

#### Scenario: 参考新资源

- **WHEN** 参考了重要外部文档（协议分析、抓包工具文档等）
- **THEN** 追加到下方外部资源区

### Requirement: 项目分析文档索引

深度分析文档（.claude/analysis/）MUST 建立索引。

#### Scenario: 生成分析文档

- **WHEN** openspec-explorer 生成项目分析文档
- **THEN** 在下方索引区注册条目：主题 / 路径 / 概要

## 依赖表

| 依赖 | 版本约束 | 用途 | 链接 |
|---|---|---|---|
| requests | >=2.28 | HTTP 会话（探测/认证/心跳），所有 session 强制 trust_env=False | https://requests.readthedocs.io/ |
| pycryptodome | >=3.18 | 复现登录页 AES-128-CBC 前端加密（可选，缺失时优雅降级） | https://www.pycryptodome.org/ |
| tomli | >=2.0 (<3.11) | Python <3.11 时解析 config.toml / credentials.toml | https://github.com/hukkin/tomli |
| pytest | >=7 (dev) | 测试框架，85 用例无网络 | https://docs.pytest.org/ |

## 项目文档索引

| 文档 | 类型 | 内容 |
|---|---|---|
| `docs/protocol-notes.md` | 协议确认记录 | C1/C2/C3/C4 编号 + 待确认/已确认状态，改协议前必读 |
| `docs/capture-guide.md` | 用户文档 | 抓包向导使用说明 |
| `docs/windows-setup.md` | 部署文档 | Windows 计划任务安装 |
| `docs/termux-setup.md` | 部署文档 | Termux 安装 + 电池豁免 |
| `docs/linux-setup.md` | 部署文档 | systemd 系统服务 + WiFi SSID 触发 + 故障排查 |
| `scripts/install_windows.ps1` | 安装脚本 | Windows 一键装 |
| `scripts/install_termux.sh` | 安装脚本 | Termux 一键装 |
| `AGENTS.md` | 项目指令 | 仓库结构 / 协议纪律 / 安全约束 / 已知坑（已在仓库中维护，CLAUDE.md 索引指向它） |

## 外部资源

| 资源 | 链接 | 用途 |
|---|---|---|
| OpenSpec | https://github.com/Fission-AI/OpenSpec | spec 驱动的变更管理框架 |
| CodeGraph | https://github.com/colbymchenry/codegraph | 代码智能索引（加速探索与影响分析） |

## 分析文档索引

（暂无 — 由 openspec-explorer 生成后在此注册）
