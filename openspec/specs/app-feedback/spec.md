# app-feedback Specification

## Purpose

约束 App 内嵌反馈通道的形态与安全边界：反馈入口必须在 App 内以原生界面呈现，
收集端自托管、落盘优先于转发，同学填的内容与脱敏诊断摘要之外不得带出任何凭据。
（2026-11-04 由 change `add-app-feedback-channel` 建立；
2026-11-05 change `switch-feedback-to-openfeedback` 把 Android 端迁移到 OpenFeedback 统一服务）
## Requirements
### Requirement: App 内的快速反馈入口

Android 客户端 MUST 在设置页提供可直接到达的反馈入口，且反馈表单 MUST 在 App 内以原生界面呈现，
MUST NOT 依赖跳转外部浏览器或第三方问卷页面。

#### Scenario: 打开反馈表单

- **GIVEN** 用户进入设置页
- **WHEN** 页面渲染
- **THEN** 页面底部显示「意见反馈」卡片，点击后在 App 内打开反馈表单

#### Scenario: 校验并提交反馈

- **GIVEN** 反馈表单已打开
- **WHEN** 用户填写的反馈内容为空并尝试提交
- **THEN** 表单拒绝提交并显示明确的必填提示；内容非空时允许提交，提交期间禁用重复提交

#### Scenario: 附带脱敏诊断摘要

- **GIVEN** 用户在反馈表单中开启了「附带诊断信息」
- **WHEN** 反馈被提交
- **THEN** 载荷包含由已脱敏会话事件构造的诊断摘要，且摘要中不含账号、密码、Cookie 或完整 URL

#### Scenario: 表单如实说明反馈去向

- **GIVEN** 用户打开反馈表单
- **WHEN** 页面渲染
- **THEN** 界面说明反馈会发往作者的 OpenFeedback 后台，
  不得声称「只保存在作者本机」这类与实际投递方式不符的话；
  界面同时说明断网时会先存在手机里并在联网后自动补发

### Requirement: 反馈收集端

Python 核心 MUST 提供把反馈投递到外部通道的能力，MUST 按通道形态构造正确的请求体，
MUST 支持飞书的凭证校验，并在通道返回业务级失败时如实报告失败。

#### Scenario: 投递到群机器人

- **GIVEN** 目标地址是飞书群自定义机器人地址
- **WHEN** 提交一条反馈
- **THEN** 请求体为 `msg_type` + `content.text` 形态，文本包含分类、正文与诊断摘要

#### Scenario: 投递到多维表格

- **GIVEN** 目标地址是飞书多维表格 webhook 地址
- **WHEN** 提交一条反馈
- **THEN** 请求体为扁平 JSON，键名与表格列名对应，且含中文分类与提交时间

#### Scenario: 携带飞书凭证

- **GIVEN** 配置了飞书凭证
- **WHEN** 提交一条反馈
- **THEN** 群机器人地址附带 `timestamp` 与 `sign`（HMAC-SHA256 后 Base64），
  多维表格地址附带 `Authorization: Bearer` 请求头

#### Scenario: 通道返回业务失败

- **GIVEN** 通道返回 HTTP 200 但响应体的 `code` 非 0
- **WHEN** 提交一条反馈
- **THEN** 提交被判定为失败，调用方收到明确的失败信息，不得报告成功

#### Scenario: 投递到自托管收集端

- **GIVEN** 目标地址不是飞书地址
- **WHEN** 提交一条反馈
- **THEN** 请求体为原始反馈载荷，行为与自托管收集端既有契约一致

#### Scenario: Android 端不再走 Python 收集端

- **GIVEN** Android 端已迁移到 OpenFeedback
- **WHEN** 同学在 App 内提交反馈
- **THEN** 反馈由 SDK 直接投递到 OpenFeedback 服务，
  不经过 `oit_portal.mobile_feedback`；
  Python 侧的飞书直发与自托管收集端仍保留，供 CLI 与桌面端使用

### Requirement: 集中处理反馈

Python 核心 MUST 提供把本地反馈集中列出与导出的命令，导出的结果 MUST 是便于逐条处理与归档的格式。

#### Scenario: 列出反馈

- **GIVEN** 本机已落盘若干反馈
- **WHEN** 执行列出命令
- **THEN** 终端按时间顺序展示每条反馈的分类、内容摘要与提交时间

#### Scenario: 导出清单

- **GIVEN** 本机已落盘若干反馈
- **WHEN** 执行导出命令
- **THEN** 生成一份 Markdown 清单，逐条包含分类、完整内容、时间与诊断摘要

### Requirement: 反馈通道的安全边界

反馈通道 MUST NOT 在载荷中携带凭据，MUST NOT 声称对第三方投递不可见，
且 MUST 在文档中说明 webhook 地址随 APK 分发的风险与对应的飞书侧缓解手段。

#### Scenario: 载荷不含凭据

- **WHEN** 构造反馈载荷
- **THEN** 载荷只含分类、正文、诊断摘要、App 版本与提交时间，不含账号、密码、Cookie 或令牌

#### Scenario: 记录安全取舍

- **WHEN** 交付本能力
- **THEN** 文档写明 webhook 地址会随 APK 分发、可被提取，以及必须在飞书侧开启
  签名校验 / 凭证校验 / 关键词校验

### Requirement: 反馈投递到统一服务

Android 客户端 MUST 把反馈投递到 OpenFeedback 统一服务，
MUST 使用服务端认可的四类分类（bug / feature / experience / other），
MUST NOT 在 APK 中携带任何服务端凭据。

#### Scenario: 提交到统一服务

- **GIVEN** 已配置 OpenFeedback 服务地址
- **WHEN** 用户提交一条反馈
- **THEN** 反馈以 multipart/form-data 投递到该服务的提交接口，
  载荷含 `appId`、`submissionId`、分类、正文与 App 版本等设备上下文

#### Scenario: 不携带服务端凭据

- **WHEN** 检查构建产物
- **THEN** APK 中只有公开的 `appId` 与服务地址，不含管理员密码、服务端密钥或令牌

#### Scenario: 兼容旧分类

- **GIVEN** 载荷里的分类是旧版的 `issue` / `suggestion` / `other`
- **WHEN** 反馈被提交
- **THEN** 分类被映射到服务端分类（issue→bug，suggestion→feature，other→other），
  未知分类归为 other

### Requirement: 离线反馈不丢失

Android 客户端 MUST 在网络不可用时把反馈保存在本机，
MUST 在网络恢复后自动补发，且 MUST NOT 因补发产生重复记录。

#### Scenario: 断网时提交

- **GIVEN** 设备没有可用网络
- **WHEN** 用户提交一条反馈
- **THEN** 反馈被写入 App 私有目录的队列，界面显示已收到而不是失败，
  并登记一个带网络约束的后台任务

#### Scenario: 网络恢复后自动补发

- **GIVEN** 队列里有待发送的反馈
- **WHEN** 网络恢复
- **THEN** 后台任务自动把反馈发往服务端，成功后从队列中删除

#### Scenario: 补发不产生重复记录

- **GIVEN** 某条反馈已经发到服务端，但客户端没收到响应
- **WHEN** 客户端带着同一个 `submissionId` 重试
- **THEN** 服务端返回原记录而不新建，客户端据此识别为已发送

