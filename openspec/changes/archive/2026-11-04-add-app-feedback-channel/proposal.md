# App 内嵌快速反馈通道

- 日期：2026-11-04
- 状态：已实施并验收（2026-11-04）
- 范围：Android 原生客户端反馈入口 + Python 侧反馈收集端与汇总工具

## Why

App 要分发给同学们使用，使用过程中必然出现「连不上」「不知道按钮干嘛」「想要某个功能」这类反馈。
目前 App 内没有任何反馈入口，同学只能私下找作者，既留不下记录，也没法集中处理。

需要一个**快**的反馈通道：入口好找、填写步骤少、提交不需要另开 App 或登录账号，并且作者能一次性把反馈捞出来统一看。

## What Changes

1. **设置页底部新增「意见反馈」卡片**，点开是一个 App 内的原生 Compose 表单（不跳浏览器、不跳链接）。
2. 表单内容：反馈类型（建议 / 问题 / 其他）、文字内容、是否附带脱敏诊断摘要。
3. **自托管收集端**：`oit-portal feedback serve` 起一个极简 HTTP 服务，把反馈按 JSONL 追加落盘到本机文件。
4. **可选转发飞书**：收集端配置了飞书多维表格 webhook 地址时，同步一份到飞书表格；不配置就只落本机。
5. **集中处理**：`oit-portal feedback list` 列出反馈，`oit-portal feedback export` 导出成 Markdown 清单。
6. App 侧反馈提交复用 Python 核心的 HTTP 通道（`requests` + `trust_env=False`），不新增网络栈。

## 不做什么（Non-goals）

- 不做账号体系、登录、评分或附件上传。
- 不把反馈内容写进 App 本地存储（App 只负责提交，不负责留存）。
- 不改认证核心、SSO/ePortal 流程、CAPTURED 协议常量块。
- 不引入账号密码到反馈内容；诊断摘要只取已脱敏的会话事件。
- 不做第三方推送（邮件/短信/微信模板消息）。
- 不改 Windows 托盘端与 Linux 打包形态（本变更只服务 Android App 的反馈收集，收集端本身是跨平台 Python）。

## 影响范围与安全边界

- **新增**：`oit_portal/feedback.py`（载荷构造 / 存储 / 收集端 / 飞书转发）、`oit_portal/cli.py` 增加 `feedback` 子命令。
- **新增 Android**：`core/FeedbackBridge.kt`（提交通道）、`core/FeedbackSettingsStore.kt`（收集端地址）、`ui/FeedbackForm.kt`（表单 UI）。
- **改动 Android**：`ui/PortalScreen.kt`（设置页入口卡片）、`ui/PortalViewModel.kt`（提交状态 + 摘要脱敏）、`MainActivity.kt`（接线）。
- **新增 Android 桥接**：`core/ChaquopyFeedbackBridge.kt`（与认证桥接分开，反馈不需要校园网账密）。
- **安全边界**：
  - 反馈内容不进入 App 本地存储，不进日志（日志只记 fingerprint 与长度）。
  - 收集端地址是用户自己填的配置，不是凭据；飞书 webhook 地址属于半凭据，**只写在本机配置文件与 App 本机设置，不入库**。
  - 反馈载荷里的诊断摘要来自已有的脱敏会话事件，界面不拼接账号、密码、Cookie 或完整 URL。
  - 提交走 `network.create_session()`，强制 `trust_env = False`。
  - 收集端默认只监听回环地址；对外监听需显式 `--host`。

## 验收标准

- 设置页底部能看到「意见反馈」卡片，点击后是 App 内的原生表单，含类型、内容、附带诊断摘要三项。
- 表单校验：内容为空时不能提交并给出明确提示；提交中禁用重复提交。
- 反馈提交成功后有明确成功反馈；失败时给出可理解的错误文案，不泄露异常堆栈。
- `oit-portal feedback serve` 启动后，同网段同学能提交并落盘；`list` 能看到内容、`export` 能导出 Markdown。
- 配置飞书 webhook 后，本机落盘的同时飞书表格也收到一条。
- `python3 -m pytest` 全绿；Android `testDebugUnitTest`、`assembleDebug`、`lintDebug` 通过。
- 反馈内容与 App 内凭据无关：测试断言载荷里不含账号、密码、Cookie。

## 回滚方案

本变更不修改认证协议与既有数据格式。回滚时删除新增的 `oit_portal/feedback.py` 与 Android 反馈相关文件，
并在 `cli.py` / `PortalScreen.kt` / `PortalViewModel.kt` / `MainActivity.kt` 撤掉对应接线即可；
已落盘的 JSONL 反馈文件留在用户目录，不影响 App 运行。
