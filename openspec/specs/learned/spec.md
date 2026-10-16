# Learned Spec — oit-portal

> 版本: 1.1.0 | 最后更新: 2026-10-16

## Purpose

记录项目开发中学到的知识，避免重复探索。随踩坑实时追加，条目过多时由 openspec-archivist 清理。

## Requirements

### Requirement: 踩坑档案

技术陷阱 MUST 记录：症状 / 根因 / 解决方案 / 预防。

#### Scenario: 记录新坑

- **WHEN** 花费大量时间解决一个非显而易见的问题
- **THEN** 追加到下方「踩坑档案」区，四项齐全，注明日期

## 踩坑档案

### AES 加密 key 每次登录都不同（2026-10 确认）

- **症状**: 第一次抓包后把 AES key 当常量，第二次登录就失败
- **根因**: 登录页每次渲染生成新的 key/iv，藏在页面内联 JS
- **解决**: `htmlutil.find_aes` 每次从内联脚本动态提取；protocol.json 不写 AES 常量
- **预防**: 协议相关代码禁止给 key/iv 做常量兜底
- **相关**: AES key 与表单 `__token__` 隐藏字段是同一字符串（32 字符，key 取前 16）

### `<form method="POST">` 无 action 属性（2026-10-09 用户学校实测）

- **症状**: 猜测 action 拼 endpoint，登录全部失败
- **根因**: 浏览器原生行为是无 action 时提交当前 URL（含完整 query string），该校登录页正是这种 form，整个 authorize URL 要原样回传
- **解决**: `htmlutil.form_action()` 用 `""` 哨兵值区分「form 存在但无 action」，`capture.py` 用 page_url（含 query）作 endpoint
- **预防**: 改表单代码前读 `tests/test_analyze_form_form_without_action_defaults_to_page_url`

### Vue 密码字段是 hidden 不是 password（2026-10 确认）

- **症状**: 按 `<input type="password">` 找密码字段找不到
- **根因**: 该校 password 是 `<input name="password" type="hidden" v-model="password">`，Vue watch 监听另一个输入框后调 encrypt() 把密文塞进 hidden 字段
- **解决**: `analyze_form` 已实现对 hidden `password` 字段的 fallback 识别

### 注入式认证页不是 302（git 3ab4999 / 43a02c0）

- **症状**: daemon 入口发现只看 `Location` header，漏掉整类网络
- **根因**: 部分校园 AC 返回 200 注入页，靠 `<meta refresh>` / JS `location.href` 跳转
- **解决**: `discover.follow_entry()` 统一处理 302 / meta refresh / JS 跳转三种

### pycryptodome 缺失不能崩（git 236d7fb）

- **症状**: 无 pycryptodome 的环境直接 ImportError 崩溃
- **解决**: `sso.py` 捕获 ImportError，可读提示并允许降级

### Termux 日志目录不可写（2026-10 修复）

- **症状**: Termux 上 daemon 因日志文件写不进去直接崩
- **解决**: 日志两级降级（主路径 → $TMPDIR → 仅控制台）；状态目录从 `~/.local/state/` 改到 `~/.config/oit-portal/logs/`

### systemd Restart=on-failure + 守护退出码 1 = 重启风暴（2026-10 Linux 支持）

- **症状**: 设计 systemd 单元时发现：单实例锁冲突返回 1，Python 崩溃也返回 1，`Restart=on-failure` 无法区分 → 第二个实例一跑服务就进入 5s 重启循环
- **根因**: 守护进程的退出码没有区分「目标已达成」（已有实例在跑）与「崩溃」
- **解决**: 锁冲突路径 `return 0`（`daemon.run_daemon`），配合 `Restart=on-failure`：stop/锁冲突都不重启，崩溃/kill -9 都拉起
- **预防**: 给服务管理器写的守护进程，退出码必须区分「目标已达成」与「失败」；改退出码契约要同步测试（`test_run_daemon_lock_conflict_returns_zero`）

### pip --user 的 console script 不在 systemd PATH（2026-10 Linux 支持）

- **症状**: unit 里写 `ExecStart=oit-portal daemon`，服务起不来（exit 203 PATH 找不到）
- **根因**: systemd 不读用户 PATH，`pip --user` 装的脚本在 `~/.local/bin/`
- **解决**: install 脚本三级解析到绝对路径（`command -v` → `~/.local/bin` → sysconfig scripts）+ `[ -x ]` 校验后 sed 进 unit 模板
- **预防**: unit 模板的 ExecStart 必须占位符化，禁止写相对命令名；也不要用 root 跑安装脚本（`pip --user` 会落到 /root，与 `User=` 矛盾）——脚本开头 EUID 检查直接拒绝

### 在 systemd unit 里加 PrivateTmp / ProtectHome（2026-10 设计期拦截）

- **症状**:（未发生，设计评审拦截）给 unit 加沙箱硬化
- **根因**: 单实例锁与 pid 文件在 `tempfile.gettempdir()`（/tmp），配置/日志在 `~/.config`——PrivateTmp 让 `oit-portal stop` 找不到 pid，ProtectHome 让日志/配置写不进
- **预防**: unit 模板注释明令禁止；`User=` 普通用户运行已提供足够的边界

## 技巧模式

### 三态探测双确认

probe.py 用 online / captive / offline 三态 + 多探测点双确认，避免单点误判导致 daemon 反复重登。新增探测点要同步测试状态机 fixture。

### FakeSession 测试模式

85 个用例全部无网络：FakeSession 预录响应序列 + fixture 构造状态机。写新协议分支时先构造对应 fixture 状态，再实现代码。

## 文件速查

| 路径 | 用途 |
|---|---|
| `oit_portal/cli.py` | CLI 入口，子命令 status/once/daemon/stop/login-info/capture |
| `oit_portal/capture.py` | 抓包向导（含 `_HEURISTIC_ENDPOINTS` / `_TOKEN_FIELD_HINTS` 等 fallback 常量） |
| `oit_portal/discover.py` | 入口链路发现（302/meta/JS 三跳） |
| `oit_portal/auth/flow.py` | AuthFlow.ensure_online 编排：SSO 复用 → 账密 → ePortal → 复测 |
| `oit_portal/auth/sso.py` | SSO 登录，CAPTURED 协议常量块在文件顶部 |
| `oit_portal/auth/eportal.py` | ePortal login_sso.jsp 上线检查，CAPTURED 块同顶部 |
| `oit_portal/protocol_overrides.py` | protocol.json 合并进 CAPTURED（仅替换已有键） |
| `oit_portal/daemon.py` | 常驻守护（探活 + 保活 + 退避 + WiFi SSID 触发） |
| `oit_portal/paths.py` | 跨平台路径解析（OIT_PORTAL_HOME → 便携 → 平台默认） |
| `docs/protocol-notes.md` | 协议确认记录（C1/C2/C3/C4 编号），改协议前必读 |
| `tests/test_capture_wizard.py` | 向导回归用例（10 种场景 fixture） |
| `tests/test_discover.py` | 三种跳转路径覆盖 |
