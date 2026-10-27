# Android UI Spec

> 版本: 1.0.0 | 最后更新: 2026-10-23

## ADDED

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

- **GIVEN** 后台自动重连能力仍未接通
- **WHEN** 用户查看设置
- **THEN** 页面以说明文字标明未开放，不提供看似可用的开关
