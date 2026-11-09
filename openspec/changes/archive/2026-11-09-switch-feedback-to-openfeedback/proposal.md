# 反馈通道迁移到 OpenFeedback 统一服务

- 日期：2026-11-05
- 状态：提案已建立，实施中
- 范围：Android 端反馈提交通道（`oit-net-portal/android`），不改认证核心与既有协议

## Why

当前反馈通道走「飞书直发」：App 把反馈 POST 到飞书 webhook，反馈进多维表格。
这条路在日常使用上是够的，但它有四个绕不开的问题：

1. **数据只进表格，没有统一后台。** 四个应用（校园网助手 / 显影 / 牵线 / 校园墙）
   各有各的通道，看不到彼此，反馈无法汇总、无法检索、无法管理处理状态。
2. **只有文字，没有截图。** 问「哪里闪退了」时，同学截不了图，作者拿不到现场。
3. **断网即丢。** 提交失败只有一次机会，同学在弱网环境里重试一次就放弃了。
4. **通道地址是写入凭据。** 飞书 webhook 地址随 APK 分发，可被提取；
   只能靠飞书后台的签名校验兜底，而多维表格的 Bearer token 一旦泄漏就写进别人的表。

OpenFeedback 是一套独立、轻量、可自托管的反馈服务：同一套服务端、同一个后台，
按 `appId` 区分应用。它把上面四点一次性解决掉：

- 统一后台可以按应用筛选、搜索、改状态、写内部备注；
- 截图走 multipart 上传，单张压到 2 MB 以内；
- 离线时反馈存本机队列，联网后自动重试，提交带 `submissionId` 保证不重复；
- `appId` 是公开标识不是凭据，APK 里没有服务端密钥。

## What Changes

1. **Android 端接入 OpenFeedback SDK**（`com.kkkkikun.openfeedback:openfeedback-compose:0.1.0`）。
2. **保留现有 Compose 表单与 `FeedbackBridge` 边界。** 表单 UI 不动，
   只把桥接实现从「Chaquopy → Python → requests → 飞书」换成
   「SDK core → HttpURLConnection → OpenFeedback」。这样既有 UI 文案与交互不变，
   又拿到离线队列与自动重试。
3. **`oit_portal/feedback.py` 与 `oit_portal/mobile_feedback.py` 保留但不再被 Android 调用。**
   它们是 CLI 自托管收集端（`oit-portal feedback serve` / `list` / `export`）的实现，
   仍被桌面端与离线场景使用；Android 侧只是不再走它们。
4. **反馈通道地址改为构建期注入的 OpenFeedback 服务地址**，
   复用已有的 `android/local.properties` → `BuildConfigFeedback` 机制，
   真实地址与密钥仍然不进仓库。
5. **反馈类型从三类扩到四类**：Bug / 功能建议 / 体验问题 / 其他。
   服务端同时兼容旧的 `issue` / `suggestion` / `other`，所以回退也是安全的。

## 不做什么（Non-goals）

- 不改认证核心、SSO/ePortal 流程、`CAPTURED` 协议常量块。
- 不删 `oit_portal/feedback.py` 的自托管收集端，CLI 的 `feedback serve/list/export` 仍可用。
- 不引入飞书开放平台应用（app_id/app_secret）。
- 不做反馈的审核 / 回复界面（回复仍在 OpenFeedback 后台与后续的邮件通道里）。
- 不自动上传 logcat、账号信息、Cookie、Token。
- 不给 Android 端引入 OkHttp / Retrofit：SDK 用框架自带的 `HttpURLConnection`，
  宿主 App 的依赖树不变。

## 影响范围与安全边界

- **改动 Android**：
  - `android/app/build.gradle.kts`（加 SDK 依赖 + 仓库）；
  - `android/app/src/main/java/com/oitnetportal/core/`（新增 `OpenFeedbackBridge.kt`，
    改 `FeedbackSettingsStore.kt` 的地址语义）；
  - `android/app/src/main/java/com/oitnetportal/ui/FeedbackForm.kt`（类型枚举与文案）。
- **不改 Python**：协议、认证、日志脱敏一律不碰。
- **安全边界**：
  - 反馈内容只进 OpenFeedback，不进飞书表格；
  - 诊断摘要仍由 Python 侧 `sanitize_diagnostics()` 白名单过滤后再交给 SDK，
    宿主只传脱敏后的结果；
  - APK 里只有 `appId`（公开标识）和服务地址，**没有**任何服务端密钥；
  - 提交失败时反馈留在 App 私有目录（`noBackupFilesDir`），不外传。

## 回滚方案

Android 端的桥接实现是单点替换：把 `PortalViewModel` 里注入的桥接从
`OpenFeedbackBridge` 换回 `ChaquopyFeedbackBridge` 即可恢复飞书直发，
不需要回滚服务端，也不需要动表单 UI。

服务端侧回滚：把 `apps` 表里 `oit-net-portal` 这一行 `enabled` 置为 false，
该应用立即停止接收反馈（客户端会收到 403 并提示「该应用已停用接收反馈」）。
