# app-feedback Specification

## Purpose

约束 App 内嵌反馈通道的形态与安全边界：反馈入口必须在 App 内以原生界面呈现，
收集端自托管、落盘优先于转发，同学填的内容与脱敏诊断摘要之外不得带出任何凭据。
（2026-11-04 由 change `add-app-feedback-channel` 建立）
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
- **THEN** 界面说明反馈会发往作者配置的收集通道，不得声称「只保存在作者本机」这类与实际投递方式不符的话

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

