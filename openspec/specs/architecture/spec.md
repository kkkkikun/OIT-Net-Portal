# Architecture Spec — oit-portal

> 版本: 1.3.0 | 最后更新: 2026-10-27（自 change `android-background-auto-reconnect` 同步：移动端凭据生命周期独立成需求）

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

### Requirement: 移动端桥接（路线B Android App）

路线B Android 原生 App（`android/`，Kotlin + Compose + Chaquopy 17.1.0）MUST 按需复用仓库根目录的 Python 核心，且 MUST 通过 `oit_portal/mobile_bridge.py` 的脱敏桥接交互——桥接只暴露探测与单次登录，MUST NOT 暴露 capture / daemon 能力。

#### Scenario: Python 返回值脱敏

- **WHEN** Python 核心向 Kotlin/UI 层返回探测或登录结果
- **THEN** MUST 按白名单映射为稳定的 status/hint 结构，MUST NOT 透传原始异常、URL、会话内容或协议细节

#### Scenario: 凭据加密不确定时

- **WHEN** 移动端无法从当次登录页确认密码加密方式（普通明文表单、外链/未知加密、参数不完整、跨域表单、验证码、无表单 SPA、未知协议）
- **THEN** MUST fail-closed（安全失败并提示人工处理），MUST NOT 尝试明文提交或猜测加密

#### Scenario: 首装无 protocol.json

- **WHEN** 移动端首次安装、用户配置目录无 protocol.json
- **THEN** mobile_sso.py MUST 仅解析当次页面的 CryptoJS AES 登录表单并即时提取加密参数；MUST NOT 读取/写入 protocol.json，MUST NOT 向多个候选端点试发凭据

### Requirement: 移动端凭据与密码生命周期

Android UI 中的密码 MUST 只短暂存在于 Composition 的 `remember` 状态并在提交回调前清空。需要保存时 MUST 通过既有 `AndroidKeystoreAccountStore` 加密存储；后台自动重连只能在用户显式开启后读取一个已保存账号，禁止明文持久化或扩大秘密使用范围。

#### Scenario: Android UI 处理用户密码

- **WHEN** Android UI 接收、提交或清理用户密码
- **THEN** 密码只保存在 Composition 的 remember 状态并在提交回调前清空；UI 本身不得把明文密码写入偏好、诊断或日志

#### Scenario: 已保存账号用于后台自动重连

- **WHEN** 用户显式开启后台自动重连且存在已保存账号
- **THEN** Service 仅通过 `AndroidKeystoreAccountStore` 解密读取按规则选中的一个账号，秘密只用于创建现有移动桥接；功能关闭、账号删除或会话失效后不得继续使用旧秘密

#### Scenario: 未开启后台功能或存储不可用

- **WHEN** 后台自动重连未开启，或 Keystore 账号存储无法安全读取
- **THEN** 不得为后台认证读取或退化保存明文密码；存储不可用时按无可用账号处理并提示人工操作

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

### Requirement: 反馈通道（2026-11-04）

App 反馈 MUST 由自托管收集端承接：Python 侧提供 HTTP 收集端把反馈落盘为本机 JSONL，
Android 侧 MUST 通过移动端桥接提交，MUST NOT 在客户端内置任何第三方服务的写入凭据。

#### Scenario: 提交反馈

- **WHEN** App 提交一条反馈
- **THEN** 请求经 `network.create_session()`（trust_env=False）发往用户配置的收集端地址，
  载荷只含同学填写的正文与脱敏诊断摘要

#### Scenario: 落盘优先于转发

- **WHEN** 收集端配置了飞书 webhook 且转发失败
- **THEN** 反馈已经落盘，失败只记日志，不影响反馈被收集

#### Scenario: 客户端不持有第三方凭据

- **WHEN** 构建 App 分发给同学
- **THEN** APK 内不含任何第三方服务的写入令牌；收集端地址是普通配置，可由使用者自行修改

### Requirement: 反馈通道的投递形态与凭据取舍（2026-11-04）

反馈提交端 MUST 支持飞书两类 webhook（群自定义机器人 / 多维表格自动化），
MUST 按地址形态自动构造对应请求体，MUST 支持对方的凭证校验，
并 MUST 把「业务码非 0」判定为失败。

#### Scenario: 按形态构造请求体

- **WHEN** 提交目标地址含 `/open-apis/bot/`
- **THEN** 请求体为 `msg_type` + `content.text`；否则（其它飞书地址）为扁平 JSON，键名即列名

#### Scenario: 携带通道凭证

- **WHEN** 配置了通道凭证
- **THEN** 群机器人请求体附带 `timestamp` 与 `sign`（HMAC-SHA256 后 Base64），
  多维表格请求附带 `Authorization: Bearer` 请求头

#### Scenario: 业务级失败如实上报

- **WHEN** 通道返回 HTTP 200 但响应体 `code` 非 0
- **THEN** 提交被判定为失败，且失败信息不回显同学原文

#### Scenario: 凭据危害等级的选择

> 决策记录：飞书 webhook 地址随 APK 分发、可被提取，这是客户端直发第三方的固有代价。
> 选择该方案而非 GitHub token 的理由是**危害等级**：
> webhook 泄露的后果上限是「能往一张表/一个群写内容」，
> 而仓库 token 泄露等于交出代码修改权。
> 缓解手段是**强制在飞书侧开启校验**（签名校验 / 凭证校验 / 关键词校验），
> 因此客户端 MUST 支持携带凭证 —— 这不是疏漏，是必需的防线。

- **WHEN** 交付直发第三方的能力
- **THEN** 文档 MUST 写明地址可被提取的风险、必须在对方开启校验、以及两者的危害等级差异
