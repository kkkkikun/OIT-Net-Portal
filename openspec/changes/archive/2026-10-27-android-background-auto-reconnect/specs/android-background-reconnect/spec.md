# Android 后台自动重连 Delta Spec

> 版本: 1.0.0 | 最后更新: 2026-10-24

## ADDED Requirements

### Requirement: 用户显式启用与通知授权

后台自动重连 MUST 默认关闭，且只能由用户在 App 内显式开启。开启前 MUST 存在可用的已保存账号；Android 13+ MUST 先取得 `POST_NOTIFICATIONS` 授权。

#### Scenario: 首次安装或升级后默认状态

- **WHEN** 用户首次安装或从不含该功能的版本升级
- **THEN** 后台自动重连保持关闭，不启动前台 Service，不读取凭据执行后台认证

#### Scenario: 没有可用账号时开启

- **WHEN** 用户在没有任何已保存账号时尝试开启
- **THEN** 开关保持关闭并提示先保存账号，不启动 Service

#### Scenario: 通知权限被拒绝

- **WHEN** Android 13+ 用户拒绝通知运行时权限
- **THEN** 开关保持关闭且不启动 Service，不反复自动请求权限

#### Scenario: 有效开启

- **WHEN** 有已保存账号且所需通知权限已满足的用户开启功能
- **THEN** App 启动前台 Service，Service 在任何异步认证工作前显示常驻通知

### Requirement: 前台 Service 生命周期与通知控制

后台运行 MUST 使用公开的前台 Service 生命周期，提供低打扰常驻通知、打开 App 和停止入口。用户停止、通知停止、设置关闭及结束本地会话 MUST 走一致的清理路径。

#### Scenario: 用户主动停止

- **WHEN** 用户通过设置开关或常驻通知停止功能
- **THEN** enabled 置为 false，取消后续调度和网络回调，不再发起新认证调用，在途调用结束后释放后台 Python 会话并移除常驻通知

#### Scenario: 结束本地会话

- **WHEN** 用户在后台自动重连开启时结束本地会话
- **THEN** App 同时停止后台 Service 和 UI Python 会话，enabled 置为 false，不向校园网服务器发送退出请求

#### Scenario: 系统回收进程

- **WHEN** 系统在 enabled 为 true 且非人工介入状态时回收进程
- **THEN** Service 使用 `START_STICKY` 语义尝试恢复，恢复后先探测而不是直接提交凭据；被用户强制停止时不得绕过系统限制

### Requirement: 后台账号选择与凭据失效

Service 每次启动 MUST 只选择一个已保存账号：当前 SSID 精确绑定账号优先，其次最近使用账号。Service 生命周期内 MUST NOT 轮换账号或在认证失败后切换账号。

#### Scenario: SSID 绑定账号优先

- **WHEN** 当前 SSID 与某个账号的非空绑定值精确匹配
- **THEN** Service 选择该账号，即使最近使用记录指向另一个账号

#### Scenario: 无 SSID 匹配时退化

- **WHEN** SSID 权限缺失、当前非 Wi-Fi 或没有绑定匹配
- **THEN** Service 选择最近使用账号；不存在最近使用账号时停止启用并提示人工选择

#### Scenario: 账号被删除或替换

- **WHEN** 当前后台账号被删除或其凭据被替换
- **THEN** 旧后台会话立即失效，不再发起使用旧秘密的新调用；已在途的一次调用允许按既有超时结束后释放，凭据替换后按新值重建，账号删除时进入人工介入而不得自动轮换到其他账号

### Requirement: 探测优先与有界重登调度

后台控制器 MUST 先探测再决定是否登录，只在 `CAPTIVE` 结果下提交凭据。周期与重试 MUST 有固定上限，网络事件 MUST 可合并，UI 与 Service 的 Python 调用 MUST 在进程内串行。

#### Scenario: 在线巡检

- **WHEN** 后台探测返回 ONLINE
- **THEN** 不调用登录，清零失败计数并安排 60 秒后的下一次巡检

#### Scenario: 离线处理

- **WHEN** 后台探测返回 OFFLINE 或默认网络断开
- **THEN** 不调用登录，等待网络恢复事件，并以 30 秒间隔进行兜底校准

#### Scenario: 需要认证

- **WHEN** 后台探测返回 CAPTIVE 且距上次后台登录尝试不少于 300 秒
- **THEN** 只使用所选账号调用一次 `loginOnce`；不足 300 秒时等待到间隔届满

#### Scenario: 控制器重建仍保持重登节流

- **WHEN** 账号选择或凭据更新导致控制器在同一进程内重建
- **THEN** 上次登录尝试时间与连续失败计数必须保留，不得借重建绕过 300 秒最小重登间隔或三次失败上限

#### Scenario: 未知状态退避

- **WHEN** 后台探测返回 UNKNOWN
- **THEN** 不调用登录，从 5 秒开始按指数退避，最大间隔不超过 300 秒

#### Scenario: 重复网络事件

- **WHEN** 网络可用、能力验证和周期信号在校准进行中重复到达
- **THEN** 控制器最多保留一个待处理校准，不并发执行探测或登录

#### Scenario: UI 与后台同时操作

- **WHEN** UI 手动操作与 Service 后台操作同时需要 Python 桥接
- **THEN** 进程级互斥保证同一时间最多一个探测或登录调用在执行

### Requirement: 登录结果与人工介入

登录成功 MUST 恢复正常巡检；暂时性失败 MUST 有界重试。凭据或协议无法继续静默处理时 MUST 停止自动重试，禁止认证风暴。

#### Scenario: 登录成功或已在线

- **WHEN** 登录返回 LOGGED_IN 或 ALREADY_ONLINE
- **THEN** 清零失败计数并恢复 60 秒在线巡检

#### Scenario: 暂时性登录失败

- **WHEN** 登录返回 FAILED
- **THEN** 应用退避和 300 秒最小重登间隔；连续第三次 FAILED 后进入人工介入，不再自动尝试

#### Scenario: 登录时网络消失

- **WHEN** 登录返回 NO_NETWORK
- **THEN** 转入离线等待，不把该结果显示为在线

#### Scenario: 凭据或验证码需要人工处理

- **WHEN** 登录返回 LOGIN_REJECTED、NEED_CREDENTIALS 或 CAPTCHA_REQUIRED
- **THEN** 立即停止自动尝试并进入人工介入，不尝试其他账号或重复提交凭据

#### Scenario: 加密或协议不确定

- **WHEN** 当次页面无法明确确认密码加密方式或协议结构
- **THEN** 现有移动桥接 fail-closed 且不发送明文密码；后台通过 FAILED 上限保证不会无限调度

#### Scenario: 进入人工介入

- **WHEN** 任一人工介入条件成立
- **THEN** enabled 置为 false，取消调度并释放后台会话，移除常驻通知、发出不含敏感详情的普通提示并停止 Service；用户处理后必须显式重新开启

### Requirement: 脱敏状态与功能边界

UI、通知、偏好和诊断 MUST 只使用固定状态枚举与脱敏提示，且后台功能 MUST 复用现有移动桥接能力，不得扩张为 daemon 或 Capture。

#### Scenario: 状态展示与持久化

- **WHEN** 后台状态写入 UI、通知、诊断或偏好
- **THEN** 不包含密码、Cookie、token、原始 URL、页面内容、异常原文或会话数据，账号标识不出现在通知中

#### Scenario: 桥接能力保持不变

- **WHEN** 后台控制器需要认证或保活
- **THEN** 只组合现有 `probe`、`loginOnce` 与 `close`，不调用或新增 Python daemon / Capture 移动接口，不实现流量心跳

#### Scenario: 不增加后台绕过能力

- **WHEN** 实现后台自动重连
- **THEN** 不新增 BOOT_COMPLETED、开机自启、电池优化白名单引导或厂商限制绕过逻辑
