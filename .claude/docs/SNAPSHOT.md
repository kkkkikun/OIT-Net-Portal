# SNAPSHOT.md — 项目状态快照

> 最后更新: 2026-10-16 | 基线测试: 114 passed (无网络)

## 项目概览

**oit-portal** — 鄂尔多斯应用技术学院校园网静默自动登录 + 保活工具。Python 3.9+，单代码库三端共用（Windows 计划任务 / Android Termux / Linux systemd）。

核心机制：登录协议不写死，由 `oit-portal capture` 抓包向导自动发现，写入用户配置目录 `protocol.json`，运行时合并进 `sso.py` / `eportal.py` 顶部的 `CAPTURED` 常量块（占位标签 `<CAPTURE:Cx.y>` 对应 `docs/protocol-notes.md` 编号）。

## 技术栈

| 项 | 值 |
|---|---|
| 语言 | Python 3.9+ |
| 依赖 | requests, pycryptodome (可选 AES), tomli (<3.11) |
| 测试 | pytest，114 用例全部无网络（FakeSession + fixture 状态机） |
| 打包 | pyproject.toml + setuptools，console_scripts: oit-portal |
| 格式化 | 无强制工具，遵循现有代码风格 |

## Git 状态

- 分支: main（干净）
- 最近提交:
  - `337fa06` feat(daemon): 网络恢复 burst 探测 + WiFi SSID 触发
  - `ccc2b3c` fix(termux): 日志两级降级
  - `7e356ca` fix(termux): 日志文件不可写时不再崩
  - `a394952` fix(paths): Termux 状态目录改 ~/.config/oit-portal/logs/
  - `f596fac` capture 向导支持 form 无 action / Vue 隐藏密码字段

## 目录结构

```
oit_portal/
├── cli.py                  # CLI 入口: status/once/daemon/stop/login-info/capture
├── capture.py              # 抓包向导（_HEURISTIC_ENDPOINTS 等 fallback 常量）
├── discover.py             # 入口链路发现（302 / meta refresh / JS 三跳）
├── probe.py                # 三态探测 online/captive/offline，多探测点双确认
├── daemon.py               # 常驻守护（探活 + 保活 + 退避 + WiFi SSID 触发）
├── keepalive.py            # 心跳
├── htmlutil.py             # HTML/内联 JS 解析（find_aes / form_action / analyze_form）
├── protocol_overrides.py   # protocol.json 合并进 CAPTURED（仅替换已有键）
├── config.py / log.py / paths.py
├── auth/
│   ├── flow.py             # AuthFlow.ensure_online 编排
│   ├── sso.py              # SSO 账密登录（CAPTURED 块在顶部）
│   ├── eportal.py          # ePortal login_sso.jsp 上线检查（CAPTURED 块同）
│   ├── models.py           # AuthError / PortalChallenge / OnlineResult
│   └── session_store.py    # SSO cookie 落盘免密复用 (session.json)
└── platform/
    ├── windows.py          # 计划任务细节
    └── termux.py           # Termux 启动/守护 + 电池豁免
tests/                      # 13 个测试文件
scripts/                    # install_windows.ps1 / install_termux.sh / install_linux.sh
                            # uninstall_linux.sh / oit-portal.service.template / boot template
docs/                       # protocol-notes.md / capture-guide.md / 双端部署文档
openspec/                   # OpenSpec 规范体系（specs/ + changes/）
```

## 关键文件速查

| 场景 | 文件 |
|---|---|
| 改协议字段 | `oit_portal/auth/sso.py` + `eportal.py` 顶部 CAPTURED 块 + `docs/protocol-notes.md` |
| 改抓包向导 | `oit_portal/capture.py` + `tests/test_capture_wizard.py` + `docs/capture-guide.md` |
| 改入口跳转 | `oit_portal/discover.py` + `tests/test_discover.py` |
| 改路径/守护 | `oit_portal/paths.py` + `platform/` + `docs/{windows,termux}-setup.md` |
| 改表单解析 | `oit_portal/htmlutil.py` + `tests/test_htmlutil.py` |

## 当前工作

- **阶段**: 协议自配置机制已完整落地并通过该校实测（form 无 action、Vue 隐藏密码字段已支持）
- **进行中**: Linux（systemd）支持已落地（daemon SSID 扩展 + install/uninstall 脚本 + service 模板 + docs/linux-setup.md），待 Jetson Nano 实机端到端验证
- **阻塞**: 无

## 安全红线（改代码前自查）

1. 配置文件不入库（.gitignore 已屏蔽 config.toml / credentials.toml / session.json / *.log / *.har）
2. 日志脱敏：密码/cookie/token 只能经 `log.fingerprint()`（前 4 位 + 长度）
3. 所有 `requests.Session` 必须 `trust_env = False`
4. 密码只存 `credentials.toml`（0600）或 `OIT_PORTAL_PASSWORD` 环境变量
