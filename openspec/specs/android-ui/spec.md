# Android UI Spec — oit-portal

> 版本: 1.0.0 | 最后更新: 2026-10-27（自 change `android-ui-refresh` 同步，2026-10-23 完成）

## Purpose

约束 oit-portal Android 原生 App（路线B）的界面结构与安全边界：连接状态优先的首页、三入口页面分区，以及 UI 改动不得破坏认证核心与凭据安全。

## Requirements

### Requirement: 连接状态优先的首页

Android 客户端 MUST 在连接首页清晰展示当前 PortalStatus、状态解释、必要的操作反馈和登录入口。

#### Scenario: 展示在线状态

- **GIVEN** ViewModel 的状态为 ONLINE
- **WHEN** 用户打开连接页
- **THEN** 页面显示明确的在线文案、状态详情和可执行的刷新操作

#### Scenario: 展示待认证或离线状态

- **GIVEN** ViewModel 的状态为 CAPTIVE 或 OFFLINE
- **WHEN** 用户打开连接页
- **THEN** 页面显示对应的待认证/离线文案，并提供登录表单与状态刷新入口

#### Scenario: 操作进行中或返回提示

- **GIVEN** ViewModel 正在执行操作，或存在 notice
- **WHEN** 连接页渲染
- **THEN** 页面显示进度或提示，并阻止重复提交

### Requirement: 清晰的页面分区

Android 客户端 MUST 将连接、设置和诊断分成三个可直接到达的入口。

#### Scenario: 查看设置

- **GIVEN** 用户从底部导航进入设置
- **WHEN** 页面渲染
- **THEN** 用户能管理自动刷新选项、已保存账号和本地会话，并看到尚未接入功能的准确说明

#### Scenario: 查看诊断

- **GIVEN** 用户从底部导航进入诊断
- **WHEN** 页面渲染
- **THEN** 页面最多显示最新 10 条会话内脱敏事件，并提供空状态和当前提示

### Requirement: 保持认证和凭据安全边界

UI 重设计 MUST NOT 改变认证核心、凭据持久化策略或诊断脱敏边界。

#### Scenario: 提交登录表单

- **GIVEN** 用户提交有效账号和密码
- **WHEN** 表单调用现有 ViewModel 回调
- **THEN** 密码状态在回调前清空，凭据保存仍由用户明确选择，UI 不直接调用 Python 或存储 API

#### Scenario: 后台自动重连尚未实现

> 2026-10-27 注：后台自动重连已由 change `android-background-auto-reconnect` 接通，归档时此场景将被其 delta 更新。

- **GIVEN** 后台自动重连能力仍未接通
- **WHEN** 用户查看设置
- **THEN** 页面以说明文字标明未开放，不提供看似可用的开关

### Requirement: App 内的快速反馈入口

> 2026-11-04 由 change `add-app-feedback-channel` 加入。

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
