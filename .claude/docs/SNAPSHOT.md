# SNAPSHOT.md — 项目状态快照

> 最后更新: 2026-10-21 | 基线测试: 246 passed (无网络) + Android testDebugUnitTest 31 例

## 项目概览

**oit-portal** — 鄂尔多斯应用技术学院校园网静默自动登录 + 保活工具。Python 3.9+，单代码库多端共用（Windows 计划任务 / Android Termux / Linux systemd），另有**路线B Android 原生 App**（`android/`，Kotlin + Compose + Chaquopy 复用 Python 核心，WIP 未编译未真机验证）。

核心机制：登录协议不写死，由 `oit-portal capture` 抓包向导自动发现，写入用户配置目录 `protocol.json`，运行时合并进 `sso.py` / `eportal.py` 顶部的 `CAPTURED` 常量块（占位标签 `<CAPTURE:Cx.y>` 对应 `docs/protocol-notes.md` 编号）。

## 技术栈

| 项 | 值 |
|---|---|
| 语言 | Python 3.9+ |
| 依赖 | requests, pycryptodome (可选 AES), tomli (<3.11) |
| 测试 | pytest，246 用例全部无网络（FakeSession + fixture 状态机 + Android 静态契约测试）；Android 另有 31 例 ViewModel JUnit 单测 |
| 打包 | pyproject.toml + setuptools，console_scripts: oit-portal |
| 格式化 | 无强制工具，遵循现有代码风格 |

## Git 状态

- 分支: main（干净）
- 最近提交:
  - `2d80439` fix(android): stage Python sources for debug build
  - `f821231` wip(android): normalize mobile SSO redirects and preserve auth code
  - `8cfe943` wip(android): fail closed on uncertain mobile password encryption
  - `4368b1d` wip(android): resolve first-run SSO form without protocol file
  - `2333cb3` feat(android): 建立 Compose 应用骨架（路线B 起点，2026-10-18）

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
├── mobile_bridge.py        # 路线B 移动端桥接（脱敏探测/单次登录，无 capture/daemon）
├── mobile_sso.py           # 移动端首装 SSO 适配器（不读 protocol.json，fail-closed 加密）
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
tests/                      # 19 个测试文件（含 test_mobile_* 与 test_android_* 契约测试）
android/                    # 路线B 原生 App（Kotlin + Compose + Chaquopy，WIP 未编译）
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

- **阶段**: 协议自配置机制已完整落地并通过该校实测；Linux（systemd）支持已落地
- **进行中**: 路线B Android 原生 App（2026-10-18 起，12 个提交）——Compose 骨架 + Chaquopy 桥接 + 手动登录已接线；capture/自动重连/凭据存储未实现，Gradle Wrapper 未生成，未编译未真机验证（现状清单见 android/README.md）
- **待实机验证**: Jetson Nano 端到端部署（install_linux.sh）
- **阻塞**: 无

## 安全红线（改代码前自查）

1. 配置文件不入库（.gitignore 已屏蔽 config.toml / credentials.toml / session.json / *.log / *.har）
2. 日志脱敏：密码/cookie/token 只能经 `log.fingerprint()`（前 4 位 + 长度）
3. 所有 `requests.Session` 必须 `trust_env = False`
4. 密码只存 `credentials.toml`（0600）或 `OIT_PORTAL_PASSWORD` 环境变量
