# 实施任务：反馈通道改为飞书直发

- [x] 建 OpenSpec 提案、设计说明与 Delta Spec（依赖：无）
- [x] TDD 写红测试：群机器人请求体 / 多维表格扁平 JSON / 签名校验 / Bearer 凭证 / code 非 0 判失败（依赖：提案）
- [x] 实现 `oit_portal/feedback.py`：按通道形态构造请求体 + 凭证支持 + `category_label`/`submitted_at`（依赖：红测试）
- [x] 实现 `oit_portal/mobile_feedback.py`：桥接支持传凭证（依赖：feedback 模块）
- [x] Android：端点语义改为飞书地址 + 凭证字段 + 桥接传参（依赖：桥接）
- [x] Android：反馈表单文案改为如实说明「发往作者的收集通道」（依赖：文案）
- [x] 验证：pytest 全绿、Android testDebugUnitTest / assembleDebug / lintDebug（依赖：实现完成）
- [x] 文档重写：docs/app-feedback.md 飞书配置步骤 + 凭据风险 + 自托管退路（依赖：验证通过）
- [x] 同步 SNAPSHOT / tasks / learned / architecture spec / CHANGELOG（依赖：文档）
- [x] 通道地址与凭证改为**构建期注入**（`android/local.properties` → Gradle 生成 `BuildConfigFeedback`），真实地址与密钥不进公开仓库（已验证：dex 里有、git grep 无）

## 遗留（需要真实环境）

- [ ] 真机验收：同学端提交 → 飞书表格里出现一行（待 ADB 设备 + 作者的飞书通道地址）
- [ ] 分发前填写 `DEFAULT_FEEDBACK_ENDPOINT` / `DEFAULT_FEEDBACK_SECRET`，并在飞书侧开启校验
