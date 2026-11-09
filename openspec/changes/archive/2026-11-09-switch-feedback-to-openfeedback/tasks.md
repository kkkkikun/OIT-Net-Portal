# 实施任务：反馈通道迁移到 OpenFeedback 统一服务

- [x] 建 OpenSpec 提案、设计说明与 Delta Spec（依赖：无）
- [x] OpenFeedback SDK 发布 `com.kkkkikun.openfeedback:openfeedback-core:0.1.0`
      到只读静态 Maven 仓库（依赖：提案）
- [x] `settings.gradle.kts` 声明 SDK 的 Maven 仓库，地址由
      `oit.openfeedback.mavenUrl` 属性决定（依赖：SDK 发布）
- [x] `build.gradle.kts` 加 `openfeedback-core:0.1.0` 依赖（固定版本）（依赖：SDK 发布）
- [x] 新增 `core/OpenFeedbackBridge.kt`：实现既有 `FeedbackBridge` 边界，
      走 SDK core，不碰 Chaquopy（依赖：SDK 发布）
- [x] `core/FeedbackSettingsStore.kt`：地址语义改为 OpenFeedback 服务地址，
      去掉不再需要的凭证字段（依赖：OpenFeedbackBridge）
- [x] `MainActivity.kt`：桥接从 `ChaquopyFeedbackBridge` 换成 `OpenFeedbackBridge`（依赖：OpenFeedbackBridge）
- [x] `build.gradle.kts` 的 `generateFeedbackConfig` 只注入服务地址，
      不再注入凭证（APK 里不再有服务端凭据）（依赖：FeedbackSettingsStore）
- [x] `ui/FeedbackForm.kt`：分类扩到四类（bug/feature/experience/other），
      文案改为如实说明「发到 OpenFeedback 后台，断网会本地暂存」（依赖：提案）
- [x] TDD 写测试：分类映射（新分类 + 旧分类 + 未知分类兜底）（依赖：OpenFeedbackBridge）
- [x] 既有 `PortalFeedbackViewModelTest` 跟随分类改名（依赖：FeedbackForm）
- [x] 验证：`./gradlew testDebugUnitTest assembleDebug lintDebug` 全绿（依赖：实现完成）
      （2026-11-05：79 例全绿 0 失败；已核对 APK dex 含 `FeedbackApiClient` / `FeedbackQueue` /
      `FeedbackUploadWorker`，旧飞书 webhook 与 token 在 dex 里 0 处残留）
- [x] 真机验收：同学端提交 → OpenFeedback 后台出现记录（待 ADB 设备 + 公网 HTTPS）
      （2026-11-05：红米 K50 Ultra / Android 15 / API 35，在线提交 → 后台出现记录，
      诊断摘要只含脱敏状态）
- [x] 真机验收：断网提交 → 恢复网络 → 自动补发 → 无重复记录（依赖：真机验收）
      （2026-11-05：飞行模式提交 → 本机队列落盘；恢复网络 → WorkManager 自动补发，
      `submission_id` 一致；强制重跑 worker 3 次无重复）
- [x] 文档重写 `docs/app-feedback.md`：改为 OpenFeedback 配置步骤（依赖：验证通过）
- [x] 同步 SNAPSHOT / tasks / learned / architecture spec / CHANGELOG（依赖：文档）
      （2026-11-05 已同步）

## 遗留（需要真实环境）

- [x] 公网 HTTPS：阿里云安全组需要放行入站 TCP 80/443，
      否则 Caddy 拿不到证书（Let's Encrypt 验证器报 "likely firewall problem"）
      （2026-11-05：安全组已放行，Let's Encrypt 生产 CA 签发 IP 证书成功，链校验 0 ok）
- [x] `android/local.properties` 的 `oit.feedback.endpoint` 填 OpenFeedback 服务地址
      （2026-11-05：已填 `https://8.160.116.34`）
- [x] `oit.feedback.secret` 已不再使用，可以从本机配置里删掉
      （2026-11-05：已删除，`git grep` 确认无代码读取）
