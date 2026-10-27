# 实施任务：Android 后台自动重连

## 1. 测试契约与状态存储

- [x] 1.1 新增 `BackgroundReconnectControllerTest` 假桥接/假账号/虚拟时钟用例，先覆盖 ONLINE 不登录、CAPTIVE 才登录、OFFLINE 不登录、300 秒最小重登、UNKNOWN 退避、三次 FAILED 与人工介入（依赖：提案/设计；验证：测试先失败且无网络）
- [x] 1.2 补事件合并、跨桥接互斥、停止后不再调用、账号选择/删除/替换测试（依赖：1.1；验证：JUnit 可重复运行且能区分并发与旧会话失效）
- [x] 1.3 新增设置、通知权限、Service action、默认关闭、无 BOOT_COMPLETED 和安全文案的 pytest 静态契约（依赖：1.1；验证：pytest 目标用例先失败）
- [x] 1.4 实现 `BackgroundReconnectStateStore` 与 SettingsStore 扩展，仅持久化 enabled、状态枚举和固定脱敏提示，缺省关闭（依赖：1.3；验证：1.3 中存储/默认值用例通过，敏感字段审查通过）

## 2. 后台调度核心

- [x] 2.1 实现账号选择器：SSID 精确绑定优先、最近使用其次，无账号或删除当前账号时人工介入且不轮换（依赖：1.2、1.4；验证：对应 JUnit 通过）
- [x] 2.2 实现 `BackgroundReconnectController` 状态机、60/30 秒巡检、5–300 秒退避、300 秒最小重登、三次 FAILED 上限及单 pending 校准（依赖：2.1；验证：1.1 全部通过）
- [x] 2.3 为所有 `ChaquopyPortalCoreBridge` 实例加入固定锁顺序的进程级探测/登录互斥，并保持实例关闭幂等（依赖：2.2；验证：1.2 并发与停止清理用例通过）

## 3. 前台 Service 与通知

- [x] 3.1 接通 `PortalForegroundService` 的启动、常驻通知、打开 App、通知停止和普通人工介入提示；异步工作前先 `startForeground`（依赖：2.2；验证：3.2 的静态契约及后续真机检查通过）
- [x] 3.2 在 Service 注册/注销默认网络回调，接入控制器；统一 UI/通知停止、异常清理、`START_STICKY` 和 enabled 状态，停止后等待在途调用再释放 core（依赖：2.3、3.1；验证：生命周期 JUnit/静态契约通过，无回调或协程泄漏）
- [x] 3.3 接入账号删除、凭据替换与手动换号导致的旧后台会话失效；人工介入时关闭 enabled、停止 Service 并只显示固定提示（依赖：3.2；验证：账号失效与人工介入测试通过）

## 4. UI 与生命周期集成

- [x] 4.1 将设置页占位替换为后台自动重连开关和真实状态；无账号禁止开启，Android 13+ 权限拒绝时不启动且不反复请求（依赖：1.4、3.1；验证：ViewModel/静态契约通过）
- [x] 4.2 让结束本地会话同时停止 UI/Service 两侧会话并保持不向服务器注销；确保现有自动刷新、手动登录、多账号行为不回归（依赖：3.3、4.1；验证：相关 ViewModel 回归测试通过）
- [x] 4.3 接入脱敏诊断与通知状态映射，不展示账号、密码、Cookie、token、URL、页面或异常原文（依赖：4.1；验证：安全静态检查及全部单测通过）

## 5. 验证与交付

- [x] 5.1 运行完整 `python3 -m pytest` 与 Android `testDebugUnitTest`，修复仅限本变更导致的问题（依赖：1–4；验收：全部通过、无网络、既有用例无回归）
- [x] 5.2 运行 `assembleDebug` 与 `lintDebug`，检查 manifest 未新增 boot/电池绕过能力、未新增第三方依赖（依赖：5.1；验收：构建和 Lint 通过）
- [x] 5.3 用 ADB 在 Android 9 真机验证默认关闭、开启/通知停止、后台断网自动重连、三次失败/人工介入可模拟路径、结束会话与进程回收；有 Android 13+ 环境时补通知授权（依赖：5.2；验收：保存截图和结果，未实机覆盖的路径明确标注）——**2026-10-27 完成**：vivo V1936A (Android 9) 实测，默认关闭/开启+通知/通知停止/断网监控与恢复/结束会话全部通过；CAPTIVE 自动认证（服务端会话未过期）与三次 FAILED（需破坏真实凭据）未自然触发，JUnit 覆盖；Android 13+ 无设备未覆盖；vivo 划卡杀进程且 sticky 不重启（符合设计预测，已记录）；发现 P1：重开 App 不恢复服务且状态文本陈旧；详见 `android/validation/2026-10-27-background-reconnect/report.md`
- [x] 5.4 更新 `android/README.md`、`.claude/docs/SNAPSHOT.md` 与 `.claude/docs/tasks.md`，记录实测范围、厂商后台限制和回滚方式（依赖：5.3；验收：文档不再把已接通功能列为未接入，未验证项不写成通过）
