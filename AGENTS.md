# AGENTS.md — OIT-Net-Portal

校园网（鄂尔多斯应用技术学院）静默自动登录 + 保活工具。Python 3.9+，单代码库双端共用（Windows 计划任务 / Android Termux）。

## 仓库结构

| 路径 | 作用 |
|---|---|
| `oit_portal/cli.py` | CLI 入口，子命令：`status / once / daemon / stop / login-info / capture` |
| `oit_portal/capture.py` | 一键抓包向导，自动发现协议并写入 `protocol.json` |
| `oit_portal/discover.py` | 入口链路发现：统一处理 30x、`<meta refresh>`、JS `location.href=…` 三种跳转 |
| `oit_portal/probe.py` | 三态探测（online / captive / offline），多探测点双确认 |
| `oit_portal/auth/flow.py` | 编排：`AuthFlow.ensure_online` = SSO 复用 → 账密 → ePortal 上线 → 复测 |
| `oit_portal/auth/sso.py` | SSO 账密登录（含密码前端加密复现）。**协议常量在 `CAPTURED` 块** |
| `oit_portal/auth/eportal.py` | ePortal `login_sso.jsp` 上线检查。**协议常量在 `CAPTURED` 块** |
| `oit_portal/auth/models.py` | `AuthError` 层级（含 `retryable`）、`PortalChallenge`、`OnlineResult` |
| `oit_portal/auth/session_store.py` | SSO cookie 落盘免密复用（`session.json`，已 gitignore） |
| `oit_portal/protocol_overrides.py` | 把 `<配置目录>/protocol.json` 合并进 `CAPTURED` 命名空间（仅接受已有属性） |
| `oit_portal/daemon.py` | 常驻守护循环（探活 + 保活 + 退避） |
| `oit_portal/keepalive.py` | 心跳 |
| `oit_portal/htmlutil.py` | HTML/内联 JS 解析（找 AES key、表单字段、接口候选） |
| `oit_portal/platform/{windows,termux}.py` | 双端启动/守护细节 |
| `oit_portal/paths.py` | 跨平台路径解析（APPDATA / XDG / 便携模式 / `OIT_PORTAL_HOME`） |
| `oit_portal/log.py` | 日志：旋转文件 + 控制台；**永不记录明文密码与完整 cookie**（只用 `fingerprint()` 记 4 位） |
| `tests/` | 85 个用例（无网络）。`FakeSession` + 多种 fixture 状态机 |
| `scripts/install_windows.ps1` | Windows 一键装（注册计划任务 + 启动） |
| `scripts/install_termux.sh` | Termux 一键装 + 电池豁免 |
| `docs/protocol-notes.md` | 协议确认记录（待确认 / 已确认），协议变更先查这里 |
| `docs/capture-guide.md` | 抓包向导使用说明（用户文档） |

## 常用命令

```bash
pip install -e .                       # 开发安装（含 console_scripts: oit-portal）
oit-portal capture                     # 首次：协议自配置（校内未登录状态跑）
oit-portal status                      # 探测三态
oit-portal once                        # 完整跑一次登录流程（退出码 0/1/2/3 见 cli.py）
oit-portal daemon                      # 守护循环
oit-portal stop                         # 停 daemon
python -m pytest                       # 跑全部 85 个用例（无网络）
```

依赖：`requests`、`pycryptodome`（AES-128-CBC 复现，缺失时 `sso.py` 优雅降级）、`tomli`（仅 <3.11）。

## 协议自配置机制（核心约束）

登录协议不是写死，而是**抓一次自动发现**：

1. `oit_portal/auth/sso.py` 和 `eportal.py` 顶部各有一个 `CAPTURED = SimpleNamespace(...)` 常量块，**值用 `<CAPTURE:C2.1>` 这种占位标签** 标注未确认项（编号对应 `docs/protocol-notes.md` 的 C1/C2/C3/C4 章节）。
2. 用户跑 `oit-portal capture` → `capture.py` 自动跑一遍跳转链、解析、试登录 → 成功后把发现的字段写进 `<home>/protocol.json`。
3. 运行时 `protocol_overrides.apply_overrides(CAPTURED, "sso"|"eportal")` 合并 `protocol.json` 进 `CAPTURED`（仅替换已有键，未知键打 warning）。
4. `protocol.json` 文件本身**不入库**（通过路径解析在用户配置目录），改它不需要动 git。

**编辑协议相关代码的纪律**：
- 改 `sso.py` / `eportal.py` 顶部 `CAPTURED` 块时，**只改值、保持键名稳定**（未知键会被 overrides 忽略）。
- AES key/iv 必须**每次页面动态从内联脚本提取**（`htmlutil.find_aes`），不要把常量值写进 `protocol.json`——实测多次登录 key 都变。
- 已确认的协议项 → 在 `docs/protocol-notes.md` 对应行把状态改成 `✅ 已确认` + 日期，不要只改代码不更新文档。
- 改完 `sso.py` / `eportal.py` 的协议相关逻辑，**同步更新 `tests/test_capture_wizard.py` 或对应测试夹具**。

## 表单 action 解析（capture.py 关键约束）

`htmlutil.form_action()` 返回三种值，向导据此决定走哪条路：

| 返回值 | 含义 | 向导处理 |
|---|---|---|
| `"/some/url"` | `<form action="...">` 显式指定 | endpoint = urljoin(page_url, "/some/url") |
| `""` | **`<form>` 存在但无 action 属性**（浏览器原生行为：提交当前 URL）| endpoint = page_url（含原 query string）|
| `None` | 完全没有 `<form>` | 走 SPA JS 扫描分支 |

**这是用户学校实测的关键修复点**（2026-10-09 第二次抓包发现）：登录页 HTML 是 `<form method="POST">` 无 `action` 属性，**整个 authorize URL（含 `response_type=code&client_id=...&redirect_uri=...`）都要原样回传**。任何「猜测 action」的方案都会失败。

**Vue 密码字段也可能是 hidden**：用户学校的 password 不是 `<input type="password">`，而是 `<input name="password" type="hidden" v-model="password">`——Vue 的 `watch` 监听另一个 `<input v-model="password_">` 变化后调用 `encrypt()` 把密文塞进 hidden 字段。`analyze_form` 已实现 hidden `password` 字段的 fallback 识别。

**改表单相关代码前先读 `tests/test_analyze_form_form_without_action_defaults_to_page_url`**——这个测试直接用用户学校的 HTML 片段。

## 入口链路（discover.py）

真实环境实测有三种跳转都要跟：`Location`（302）、`<meta http-equiv="refresh">`、JS `location.href=...` / `location.replace(...)`。`follow_entry()` 统一处理：

- `redirect_url` 模式：从 AC 302 Location 开始
- `page_url + page_body` 模式：从 AC 200 注入页开始（**该校就是这种**——见 protocol-notes C1.1）
- 链路中遇到 `client_id` + `redirect_uri` 的 URL 顺手解析为 `PortalChallenge`
- 停止条件：含 `<form>` 的 200 页面，或跳数耗尽

**改这块代码前先读 `tests/test_discover.py`**——三种跳转路径各有覆盖用例。

## 抓包向导增强要点（capture.py）

随着实测迭代，向导已加很多 fallback。下次改这块前先看 `_HEURISTIC_ENDPOINTS` / `_WIDGET_*` 常量：

| 模块 | 作用 |
|---|---|
| `analyze_form()` | 表单解析（含 form-without-action 兜底、hidden 字段识别）|
| `scan_login_endpoints()` | 扫描页面内联 + 外链 JS 找接口候选（5 种 regex：axios/fetch/jQuery/路径关键字/URL 字面量）|
| `_HEURISTIC_ENDPOINTS` | 312 个常见 widget 组合（4 layers × 13 classes × 6 actions）+ 标准 OAuth2/SSO 路径 |
| `_looks_like_spa_catchall()` | POST 返回的 HTML 首段与登录页一致时识别为「SPA 路由兜底」并跳过 |
| `_extract_vue_templates()` | 提取 `<script type="text/x-template">` 块，form action 经常藏这里 |
| `_TOKEN_FIELD_HINTS` | 探测 `fingerprint` / `verify_token` / `verify_code` 等动态 token 字段名 |

`tests/test_capture_wizard.py` 覆盖：full success / online reject / transparent mode / injected JS chain / Vue SPA AES / wrong password / no real endpoint / jquery widget / real school scenario / form without action。

## 安全 / 隐私硬约束

1. **配置文件不能入库**：`.gitignore` 已屏蔽 `config.toml` / `credentials.toml` / `session.json` / `*.log` / `*.har`。任何「记录凭证」的代码改动都要重新审视 `.gitignore` 是否需要加新模式。
2. **日志脱敏**：所有日志里出现的密码、cookie、token，必须走 `log.fingerprint(secret)`（只打前 4 位 + 长度）。**不要**在 logger 调用里直接拼接原始 secret。
3. **HTTP 直连不代理**：`cli._make_session()` 强制 `session.trust_env = False`——探测/认证必须直连校园 AC，否则会被代理劫持逻辑搞混。
4. **密码不在主配置文件**：`credentials.toml`（0600 权限）或 `OIT_PORTAL_PASSWORD` 环境变量。模板见 `config.example.toml`。

## 跨平台路径

`paths.resolve_paths()` 优先级：`OIT_PORTAL_HOME` 环境变量 → 便携模式（与 `config.toml` 同目录）→ 平台默认（Win `%APPDATA%\oit-portal`，其余 `~/.config/oit-portal`，Termux 日志走 `XDG_STATE_HOME`）。

**改路径相关代码必须同时**：
- 检查 `is_termux()`（`TERMUX_VERSION` env）
- 检查便携模式分支（`sys.frozen` / 源码根目录）
- 不假定 `Path.home()` 可用（CI 环境可能没有）

## 已知坑

- **AES 加密每次 key 不同**——别做协议常量兜底要从页面 JS 提取；`htmlutil.find_aes` 已封装。
- **AES key 与 `__token__` 隐藏字段是同一字符串**——表单 `__token__` 值是 32 字符，AES key 取前 16 字符。
- **pycryptodome 缺失不要崩**——`sso.py` 要捕获 ImportError，给出可读提示并允许降级（见 git log `236d7fb`）。
- **注入式认证页不是 302**——daemon 的入口发现不要假设 `Location` header；200 + JS 跳转也要跟（见 git log `3ab4999`/`43a02c0`）。
- **`<form method=POST>` 无 action 属性 = 提交当前 URL**——这是用户学校实测的坑（见上文「表单 action 解析」）。
- **Vue 密码字段可能是 hidden**——`<input name="password" type="hidden" v-model="password">`，不是 `type="password"`。
- **`once` 子命令需要密码才能用**——`allow_password=cfg.password is not None`，免密场景下走 `session.json` 复用。
- **测试 jitter**：`make_config` 强制 `jitter_ratio = 0.0`，断言精确时间值。
- **`Session.trust_env = False`**——加新 session 别忘了，否则代理环境会失真。

## 改这些敏感区域前必读

- 协议字段 → `docs/protocol-notes.md`（当前已确认项 + 待确认标签编号）
- 抓包向导逻辑 → `docs/capture-guide.md`（用户体验）+ `tests/test_capture_wizard.py`（回归用例）
- 入口跳转逻辑 → `tests/test_discover.py`（302/meta/JS 三跳路径）
- 跨平台路径/守护 → `docs/windows-setup.md` + `docs/termux-setup.md` + `scripts/install_*.{ps1,sh}`
- 表单 action / hidden 字段识别 → `tests/test_htmlutil.py::test_form_action_sentinel_for_no_action` + `tests/test_discover.py::test_analyze_form_form_without_action_defaults_to_page_url`