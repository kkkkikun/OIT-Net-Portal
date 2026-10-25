# 设计：Android 后台自动重连

## Context

当前 `MainActivity` 持有 `PortalViewModel`，只有手动提交账密后才创建 `ChaquopyPortalCoreBridge`。Activity 的网络回调只触发状态探测；`PortalForegroundService` 仅显示骨架通知，`DaemonEngine` 明确未实现。Python 移动桥接只提供脱敏的 `probe / login_once / close`，且 SSO 加密不确定时 fail-closed。

后台功能必须跨 Activity 生命周期运行，但又不能引入第二套认证协议、绕过现有脱敏边界或让 UI 与服务并发提交账密。实施以 Android 9 真机为最低实测环境，同时覆盖 Android 13+ 通知运行时权限。

## Goals / Non-Goals

**Goals:**

- 用户显式开启后，在 Activity 不可见时仍能低频巡检，并在确认 captive 后使用一个已保存账号自动认证。
- 常驻通知准确表达状态，随时可停止；结束本地会话、删除账号或更换凭据不会留下失控后台任务。
- 调度有界、事件可合并、UI 与服务调用串行，所有跨层文本保持脱敏。
- 调度逻辑可用 JUnit 假桥接和虚拟时间测试，无需网络或 Android 设备。

**Non-Goals:**

- 不做开机自启、流量心跳、Capture、WebView 验证码、多账号轮换或电池限制绕过。
- 不暴露 Python daemon，不修改 SSO/ePortal、`CAPTURED` 或协议确认记录。
- 不保证厂商强杀、用户强制停止或系统禁止后台后的运行能力。

## Decisions

### 1. 前台 Service + Kotlin 调度器，而不是 Python daemon / WorkManager

`PortalForegroundService` 只负责 Android 生命周期、通知和网络回调。新增 `BackgroundReconnectController` 负责状态机与协程调度，通过现有 `PortalCoreBridge` 调用单次探测和登录。

- **暴露 Python daemon**：拒绝。违反移动端桥接边界，也会带入桌面配置、pid/锁与保活语义。
- **WorkManager**：不采用。周期任务最小间隔和系统延迟不适合网络恢复后的及时认证；本需求已有前台 Service 骨架。
- **Service 内直接写循环**：拒绝。生命周期与策略难以独立测试，容易遗留协程和回调。

### 2. 独立后台会话，进程内所有 Python 调用串行

Service 按账号选择结果创建自己的 `ChaquopyPortalCoreBridge`，不持有 Activity 或 ViewModel。`ChaquopyPortalCoreBridge` 增加进程级调用 `Mutex`，所有实例的 `probe / loginOnce` 按固定锁顺序串行；实例锁继续保护本实例关闭。这样保留 UI 与 Service 的独立生命周期，又避免手动操作和后台任务同时认证。

不共享 ViewModel 的 core：Service 不应反向持有 Activity 作用域对象。停止服务时先取消后续调度，再等待当前桥接调用结束并 `shutdown()`；原生/Python 在途 HTTP 调用不假装可瞬间取消。

### 3. 显式状态机与固定脱敏状态

状态为 `STOPPED / STARTING / MONITORING / BACKOFF / NEEDS_ATTENTION`。`BackgroundReconnectStateStore` 只持久化开关、状态枚举和固定提示，不存账号、密码、URL、异常或会话。UI 观察同一状态源；Service 与通知只显示枚举对应的固定中文文本。

| 输入/结果 | 行为 | 下一状态 |
|---|---|---|
| 用户开启且权限、账号有效 | 立即 `startForeground`，创建会话并探测 | `STARTING → MONITORING` |
| `probe=ONLINE` | 不提交凭据，60 秒后巡检 | `MONITORING` |
| `probe=OFFLINE` | 不提交凭据，等待网络事件，30 秒兜底校准 | `MONITORING` |
| `probe=CAPTIVE` | 满足最小重登间隔时 `loginOnce` | `MONITORING / BACKOFF` |
| `probe=UNKNOWN` | 不登录，5 秒起指数退避，上限 300 秒 | `BACKOFF` |
| 登录成功/已在线 | 清零失败计数，60 秒后巡检 | `MONITORING` |
| 登录 `NO_NETWORK` | 等待网络事件与 30 秒兜底 | `MONITORING` |
| 登录 `FAILED` | 应用退避与 300 秒最小重登间隔；连续 3 次后停止自动尝试 | `BACKOFF / NEEDS_ATTENTION` |
| 拒绝、缺凭据、验证码 | 立即停止自动尝试，保留人工处理提示 | `NEEDS_ATTENTION` |

网络恢复、能力验证和周期事件合并为单个待处理校准；忙碌时只保留一个 pending 信号。300 秒最小重登间隔与失败计数由进程级 `BackgroundReconnectAttemptTracker.shared` 保存，账号操作导致控制器重建时也不得重置；进程回收后才重新计数。`FAILED` 包含当前桥接无法进一步区分的协议/加密失败：单次调用仍由 Python fail-closed，连续三次后必须停止，禁止无限后台重试。

### 4. 账号选择与失效

开启时从 `AccountStore` 选择唯一账号：当前 SSID 精确绑定优先，其次最近使用账号；无匹配则不启用。服务生命周期内不轮换账号。

UI 对账号的删除、凭据覆盖或手动换号登录发送失效信号：Service 取消旧会话并按规则重新选择；旧账号不存在则进入 `NEEDS_ATTENTION`，不再发起使用旧秘密的新调用。已经开始的一次阻塞式 HTTP 调用无法抢占，允许其在既有超时内结束后释放；这是有界的一次在途操作，不代表停止后仍会调度。通知停止、设置关闭与结束本地会话都会把开关置为关闭；结束本地会话还会同时停止 UI 与 Service 两侧会话。

### 5. 权限、通知与恢复语义

- 默认关闭。Android 13+ 在 UI 中请求 `POST_NOTIFICATIONS`，拒绝时不写 enabled、不启动 Service。
- 用户开启时由前台 Activity 调用 `startForegroundService`；Service 首先 `startForeground`，再执行异步初始化。
- 通知使用现有低重要性 channel，提供「打开 App」和「停止」；停止 action 与 UI 关闭走同一入口。
- 进入 `NEEDS_ATTENTION` 时把 enabled 置为 false、取消调度、移除常驻通知并发一条普通人工处理提示，随后停止 Service；用户处理后必须显式重新开启。
- 正常运行返回 `START_STICKY`，系统回收后仅在 enabled 仍为 true 时恢复。用户停止、人工介入或强制停止后不主动绕过系统限制。
- 停止命令处理前后重查 enabled，并用 `stopSelfResult(startId)` 只停止对应启动代次，避免快速关→开时旧 Stop/Destroy 误杀新 worker；已确认等待销毁时只交给 sticky 重启，不再半初始化替代 worker。
- 不增加 boot receiver，不请求新的网络、定位或电池权限。

### 6. 依赖与安全边界

不新增第三方依赖；协程、`androidx.core` 通知和现有 Chaquopy 已足够。Python Session 仍由现有桥接创建并保持 `trust_env=False`。AES key/iv 仍由 `mobile_sso.py` 每次从当次页面动态提取，`pycryptodome` 缺失或参数不确定仍安全失败；本变更不新增协议常量或加密兜底。

### 7. 测试策略

先写失败测试，再实现：

- JUnit 覆盖 ONLINE 不登录、CAPTIVE 才登录、OFFLINE 不登录、退避/最小间隔、三次 FAILED、人工介入、事件合并和停止清理。
- 并发测试覆盖 UI 与 Service 两个桥接不能同时进入登录调用。
- 设置/ViewModel 测试覆盖默认关闭、权限拒绝、无账号、通知停止、结束会话和账号失效。
- pytest 静态契约覆盖 manifest 未新增 boot 能力、通知 action、默认关闭及安全文案；全部自动化测试无网络。
- 真机覆盖 Android 9，并在可用的 Android 13+ 设备/模拟器补通知授权路径。

## Risks / Trade-offs

- **厂商后台限制导致 Service 被kill或 sticky 不重启** → 通知与文档只承诺公开 API 行为，真机记录实际结果，不加入绕过机制。
- **UI 与 Service 各有一个 Python Session，资源略增** → 进程级串行调用、停止即关闭，避免并发和长期额外会话。
- **300 秒最小重登间隔会延迟频繁掉线后的恢复** → 这是防止认证风暴的有意权衡； ONLINE 探测不受影响，用户仍可手动登录。
- **桥接 `FAILED` 无法区分所有瞬时错误与协议变化** → 有界退避加连续三次后人工介入；不向桥接透传异常来换取分类。
- **在途 Python HTTP 调用不能即时取消** → 停止后不再发起新调用，等待有超时的在途调用结束再释放，并在文档中明确。
- **单调时钟不跨进程保存** → 进程内控制器重建由共享 tracker 保留节流；sticky 进程重建会重新执行一次探测，只有 CAPTIVE 才登录，且 Service 恢复有系统退避，不为首版引入敏感或不可靠的持久化时间戳。

## Migration Plan

1. 先加入调度器与测试，再接 Service，最后接 UI；每阶段保持默认关闭。
2. 升级无需迁移既有账号或设置；新增偏好缺省为关闭，旧版本「尚未接入」文案替换为真实状态。
3. 真机验证开启、通知停止、后台断网恢复、人工介入、结束会话和进程回收。
4. 回滚时停用入口并恢复占位，保留无害的非敏感偏好；不删除用户账号，不改 Python 包或其他平台。

## Open Questions

没有阻塞实现的产品决策。真机阶段需确认目标 vivo/Android 9 的 sticky 恢复表现，以及是否另有 Android 13+ 设备可验证通知授权；若缺失，只把对应平台路径标为未实测，不阻塞默认关闭与其余测试。
