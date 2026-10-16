# Architecture Spec — oit-portal

> 版本: 1.1.0 | 最后更新: 2026-10-16

## Purpose

记录 oit-portal（校园网静默自动登录 + 保活工具）的架构决策与设计原则，指导协议适配、双端部署和功能演进。

## Requirements

### Requirement: 协议自配置机制

登录协议 MUST NOT 写死，MUST 通过抓一次自动发现：CAPTURED 常量块（占位标签）→ capture 向导 → protocol.json → 运行时合并覆盖。

#### Scenario: 添加新学校的协议支持

- **WHEN** 需要适配一个新的校园网认证系统
- **THEN** 在 sso.py / eportal.py 的 CAPTURED 块中增加带 `<CAPTURE:Cx.y>` 占位标签的常量，扩展 capture.py 的发现逻辑，并在 docs/protocol-notes.md 登记编号

#### Scenario: 运行时合并协议覆盖

- **WHEN** 用户已跑过 capture 向导生成 protocol.json
- **THEN** protocol_overrides.apply_overrides 只替换 CAPTURED 中已有的键，未知键打 warning 并忽略

### Requirement: CAPTURED 块键名稳定

CAPTURED 命名空间的键名是协议契约的一部分，外部 protocol.json 依赖它；修改时 MUST 只改值并保持键名稳定。

#### Scenario: 修改 CAPTURED 块

- **WHEN** 开发者修改 sso.py / eportal.py 顶部的 CAPTURED 常量块
- **THEN** 只改值、保持键名稳定；未知键会被 overrides 静默忽略
- **AND** 同步更新 tests/test_capture_wizard.py 或对应测试夹具

### Requirement: AES key 动态提取

AES key/iv MUST 每次登录从内联脚本实时提取，MUST NOT 做协议常量兜底。

#### Scenario: 实现密码加密

- **WHEN** sso.py 需要加密密码
- **THEN** 调用 htmlutil.find_aes 从当前页面内联 JS 提取 key/iv，不把常量写进 protocol.json
- **AND** pycryptodome 缺失时捕获 ImportError，给出可读提示并允许降级

### Requirement: HTTP 直连不代理

所有探测/认证请求 MUST 直连校园 AC，MUST NOT 被代理环境干扰。

#### Scenario: 创建新 Session

- **WHEN** 任何模块创建 requests.Session
- **THEN** 必须设置 session.trust_env = False

### Requirement: 多平台单代码库

Windows（计划任务）、Android Termux（Termux:Boot）、Linux（systemd 系统服务）MUST 共用同一套代码，平台差异 SHALL 收敛在 oit_portal/platform/、paths.py 与 scripts/ 下的平台脚本。Linux MUST NOT 新增 platform/linux.py——notify/wake_lock 为预留死代码，不扩散。

#### Scenario: 新增平台相关行为

- **WHEN** 需要 Windows 或 Termux 特有的启动/守护逻辑
- **THEN** 实现放进 oit_portal/platform/{windows,termux}.py，路径解析走 paths.resolve_paths()
- **AND** 不假定 Path.home() 可用（CI 环境可能缺失）

#### Scenario: Linux 守护部署

- **WHEN** 在 Linux 上需要开机自启与崩溃自愈
- **THEN** 使用 scripts/oit-portal.service.template 渲染为 /etc/systemd/system/oit-portal.service：Type=simple、User= 目标用户、ExecStart 绝对路径、Restart=on-failure + RestartSec=5
- **AND** MUST NOT 在 unit 中加 PrivateTmp/ProtectHome/ProtectSystem（锁/pid 在 /tmp，配置/日志在 ~/.config，沙箱化会让 `oit-portal stop` 和日志写入失效）

#### Scenario: 守护进程给服务管理器的退出码契约

- **WHEN** run_daemon 因单实例锁冲突退出
- **THEN** MUST 返回 0 而非 1——systemd Restart=on-failure 下退出码 1 会被当崩溃无限重启；「已有实例在跑」对服务管理器而言目标已达成。Python 崩溃（退出码非 0）才会触发重启

#### Scenario: 判断真 Linux

- **WHEN** 代码需要区分 Linux 与其他平台
- **THEN** MUST 使用 daemon._is_linux()（sys.platform == "linux" and not is_termux()）——Termux 的 sys.platform 也是 "linux"

#### Scenario: Linux WiFi SSID 探测

- **WHEN** daemon 在 Linux 上读取当前 WiFi SSID（wifi_ssid 触发 burst）
- **THEN** 走 best-effort 链：nmcli（NetworkManager）优先，iwgetid（wireless-tools）兜底，命令缺失/异常返回 None（feature gate 自动失效，不影响登录）

#### Scenario: 修改路径解析

- **WHEN** 修改 paths.py 的路径优先级逻辑
- **THEN** 同时检查 is_termux() 分支与便携模式分支（sys.frozen / 源码根目录）

### Requirement: 安全脱敏

日志与任何持久化输出 MUST NOT 包含明文密码、完整 cookie 或 token。

#### Scenario: 记录敏感值

- **WHEN** 日志需要引用密码、cookie、token
- **THEN** 必须经 log.fingerprint() 只记录前 4 位 + 长度，禁止拼接原始 secret

#### Scenario: 新增持久化文件

- **WHEN** 代码新增记录凭证/会话的文件
- **THEN** 检查 .gitignore 是否需要加新模式（config.toml / credentials.toml / session.json / *.log / *.har 已屏蔽）

### Requirement: 架构决策记录

重要架构决策 SHALL 以 ADR 形式记录在本文件，包含决策、原因、影响、替代方案。

#### Scenario: 记录新决策

- **WHEN** 做出影响系统架构的决策（模块边界、依赖选择、协议策略）
- **THEN** 在对应 Requirement 下补充 Scenario 或新增 Requirement，注明日期

#### Scenario: 查询决策原因

- **WHEN** 需要了解某个架构选择的原因
- **THEN** grep 搜索 openspec/specs/architecture/spec.md 中的关键词
