# 实施任务：App 内嵌快速反馈通道

- [x] 建 OpenSpec 提案、设计说明与 Delta Spec（依赖：无）
- [x] TDD 写红测试：Python 侧载荷构造 / 落盘存储 / 收集端校验 / 飞书转发 / list 与 export（依赖：提案）
- [x] 实现 `oit_portal/feedback.py`：schema、JSONL 存储、HTTP 收集端、飞书转发（依赖：红测试）
- [x] CLI 增加 `feedback serve|list|export` 子命令（依赖：feedback 模块）
- [x] TDD 写红测试：Android 侧契约测试（入口卡片、表单字段、脱敏摘要过滤、桥接契约）（依赖：提案）
- [x] Android 实现：FeedbackBridge 契约 + Chaquopy 实现 + 收集端地址存储（依赖：红测试）
- [x] Android 实现：FeedbackForm Compose 表单 + 设置页入口卡片 + ViewModel 接线（依赖：桥接）
- [x] 验证：pytest 403 passed、Android testDebugUnitTest 73 例 / assembleDebug / lintDebug、端到端联调（依赖：实现完成）
- [x] 文档同步：docs/app-feedback.md、SNAPSHOT、tasks、learned、architecture/android-ui spec、CHANGELOG（依赖：验证通过）

## 遗留（需要真实环境，非本变更内可完成）

- [ ] 真机验收：同学端提交 → 作者端 `oit-portal feedback list` 看到（待 ADB 设备）
- [ ] 分发前填写 `FeedbackSettingsStore.DEFAULT_COLLECTOR_ENDPOINT`（留空时 App 会提示「反馈通道尚未配置」）
