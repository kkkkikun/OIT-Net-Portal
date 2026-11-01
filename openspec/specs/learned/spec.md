# Learned Spec — oit-portal

> 版本: 1.2.0 | 最后更新: 2026-10-21

## Purpose

记录项目开发中学到的知识，避免重复探索。随踩坑实时追加，条目过多时由 openspec-archivist 清理。

## Requirements

### Requirement: 踩坑档案

技术陷阱 MUST 记录：症状 / 根因 / 解决方案 / 预防。

#### Scenario: 记录新坑

- **WHEN** 花费大量时间解决一个非显而易见的问题
- **THEN** 追加到下方「踩坑档案」区，四项齐全，注明日期

## 踩坑档案

### AES 加密 key 每次登录都不同（2026-10 确认）

- **症状**: 第一次抓包后把 AES key 当常量，第二次登录就失败
- **根因**: 登录页每次渲染生成新的 key/iv，藏在页面内联 JS
- **解决**: `htmlutil.find_aes` 每次从内联脚本动态提取；protocol.json 不写 AES 常量
- **预防**: 协议相关代码禁止给 key/iv 做常量兜底
- **相关**: AES key 与表单 `__token__` 隐藏字段是同一字符串（32 字符，key 取前 16）

### `<form method="POST">` 无 action 属性（2026-10-09 用户学校实测）

- **症状**: 猜测 action 拼 endpoint，登录全部失败
- **根因**: 浏览器原生行为是无 action 时提交当前 URL（含完整 query string），该校登录页正是这种 form，整个 authorize URL 要原样回传
- **解决**: `htmlutil.form_action()` 用 `""` 哨兵值区分「form 存在但无 action」，`capture.py` 用 page_url（含 query）作 endpoint
- **预防**: 改表单代码前读 `tests/test_analyze_form_form_without_action_defaults_to_page_url`

### Vue 密码字段是 hidden 不是 password（2026-10 确认）

- **症状**: 按 `<input type="password">` 找密码字段找不到
- **根因**: 该校 password 是 `<input name="password" type="hidden" v-model="password">`，Vue watch 监听另一个输入框后调 encrypt() 把密文塞进 hidden 字段
- **解决**: `analyze_form` 已实现对 hidden `password` 字段的 fallback 识别

### 注入式认证页不是 302（git 3ab4999 / 43a02c0）

- **症状**: daemon 入口发现只看 `Location` header，漏掉整类网络
- **根因**: 部分校园 AC 返回 200 注入页，靠 `<meta refresh>` / JS `location.href` 跳转
- **解决**: `discover.follow_entry()` 统一处理 302 / meta refresh / JS 跳转三种

### pycryptodome 缺失不能崩（git 236d7fb）

- **症状**: 无 pycryptodome 的环境直接 ImportError 崩溃
- **解决**: `sso.py` 捕获 ImportError，可读提示并允许降级

### Termux 日志目录不可写（2026-10 修复）

- **症状**: Termux 上 daemon 因日志文件写不进去直接崩
- **解决**: 日志两级降级（主路径 → $TMPDIR → 仅控制台）；状态目录从 `~/.local/state/` 改到 `~/.config/oit-portal/logs/`

### systemd Restart=on-failure + 守护退出码 1 = 重启风暴（2026-10 Linux 支持）

- **症状**: 设计 systemd 单元时发现：单实例锁冲突返回 1，Python 崩溃也返回 1，`Restart=on-failure` 无法区分 → 第二个实例一跑服务就进入 5s 重启循环
- **根因**: 守护进程的退出码没有区分「目标已达成」（已有实例在跑）与「崩溃」
- **解决**: 锁冲突路径 `return 0`（`daemon.run_daemon`），配合 `Restart=on-failure`：stop/锁冲突都不重启，崩溃/kill -9 都拉起
- **预防**: 给服务管理器写的守护进程，退出码必须区分「目标已达成」与「失败」；改退出码契约要同步测试（`test_run_daemon_lock_conflict_returns_zero`）

### pip --user 的 console script 不在 systemd PATH（2026-10 Linux 支持）

- **症状**: unit 里写 `ExecStart=oit-portal daemon`，服务起不来（exit 203 PATH 找不到）
- **根因**: systemd 不读用户 PATH，`pip --user` 装的脚本在 `~/.local/bin/`
- **解决**: install 脚本三级解析到绝对路径（`command -v` → `~/.local/bin` → sysconfig scripts）+ `[ -x ]` 校验后 sed 进 unit 模板
- **预防**: unit 模板的 ExecStart 必须占位符化，禁止写相对命令名；也不要用 root 跑安装脚本（`pip --user` 会落到 /root，与 `User=` 矛盾）——脚本开头 EUID 检查直接拒绝

### 在 systemd unit 里加 PrivateTmp / ProtectHome（2026-10 设计期拦截）

- **症状**:（未发生，设计评审拦截）给 unit 加沙箱硬化
- **根因**: 单实例锁与 pid 文件在 `tempfile.gettempdir()`（/tmp），配置/日志在 `~/.config`——PrivateTmp 让 `oit-portal stop` 找不到 pid，ProtectHome 让日志/配置写不进
- **预防**: unit 模板注释明令禁止；`User=` 普通用户运行已提供足够的边界

### 移动端首装没有 protocol.json（2026-10 路线B）

- **症状**: 桌面/Termux/Linux 流程依赖 `oit-portal capture` 预先生成 protocol.json；Android 原生 App 首装时该文件不存在，也不能要求用户先跑向导
- **根因**: capture 向导是 CLI 交互式流程，不属于移动端桥接能力范围
- **解决**: `mobile_sso.py` 独立适配器——只解析当次登录页的 CryptoJS AES 表单（即时提取 key/iv），不读不写 protocol.json，不向多候选端点试凭据；其余形态一律 fail-closed 提示人工处理
- **预防**: 移动端任何「复用桌面流程」的冲动都要先过 mobile_bridge 白名单边界；加密方式不确定时禁止明文提交

### 移动端桥接不能透传 Python 异常（2026-10 路线B）

- **症状**:（设计期拦截）Kotlin 侧直接展示 Python 异常/URL/会话细节
- **根因**: 异常文本可能含内网地址、协议参数、cookie 片段；UI 层不需要也不该有这些
- **解决**: mobile_bridge 按白名单映射为稳定 status/hint；requests.Session 由 `MobileProbeBridge.close()` 显式释放
- **预防**: 新增桥接返回值必须走白名单枚举，测试用契约用例（test_mobile_bridge.py）兜底

## 技巧模式

### 三态探测双确认

probe.py 用 online / captive / offline 三态 + 多探测点双确认，避免单点误判导致 daemon 反复重登。新增探测点要同步测试状态机 fixture。

### FakeSession 测试模式

294 个用例全部无网络：FakeSession 预录响应序列 + fixture 构造状态机。写新协议分支时先构造对应 fixture 状态，再实现代码。

## 文件速查

| 路径 | 用途 |
|---|---|
| `oit_portal/cli.py` | CLI 入口，子命令 status/once/daemon/stop/login-info/capture |
| `oit_portal/capture.py` | 抓包向导（含 `_HEURISTIC_ENDPOINTS` / `_TOKEN_FIELD_HINTS` 等 fallback 常量） |
| `oit_portal/discover.py` | 入口链路发现（302/meta/JS 三跳） |
| `oit_portal/auth/flow.py` | AuthFlow.ensure_online 编排：SSO 复用 → 账密 → ePortal → 复测 |
| `oit_portal/auth/sso.py` | SSO 登录，CAPTURED 协议常量块在文件顶部 |
| `oit_portal/auth/eportal.py` | ePortal login_sso.jsp 上线检查，CAPTURED 块同顶部 |
| `oit_portal/protocol_overrides.py` | protocol.json 合并进 CAPTURED（仅替换已有键） |
| `oit_portal/daemon.py` | 常驻守护（探活 + 保活 + 退避 + WiFi SSID 触发） |
| `oit_portal/paths.py` | 跨平台路径解析（OIT_PORTAL_HOME → 便携 → 平台默认） |
| `docs/protocol-notes.md` | 协议确认记录（C1/C2/C3/C4 编号），改协议前必读 |
| `tests/test_capture_wizard.py` | 向导回归用例（10 种场景 fixture） |
| `tests/test_discover.py` | 三种跳转路径覆盖 |

## 踩坑：学生网 AC gzip 漏标 Content-Encoding（2026-10-22，真机实测）

**现象**：Android 端登录 OIT-XUESHENG 时 ePortal 判定 FAILED，logcat 中响应体为乱码。
**根因**：学生网侧 AC 返回 gzip 压缩体但漏标 Content-Encoding 头（gzip 魔数 1F 8B 可辨）；
桌面端因装有 brotli，协商路径不同所以从未触发。乱码导致 success_markers 漏判 → FAILED →
账号按 fail-closed 不保存（用户感知为"账号管理没存上"）。
**修复**：`eportal._response_text()` 检测 gzip 魔数手动解压，解压体按 utf-8→gb18030 以成功标记
命中为准选择编码；FakeResponse 无 content 属性，`getattr(resp, "content", b"")` 兜底。
**教训**：① 移动端/桌面端依赖集合不同（brotli 有无）会导致同一 AC 行为分叉；
② fail-closed 的静默 catch 要配可见的诊断出口（事件日志/notice），否则用户无法区分
"登录失败没存"与"保存功能坏了"。

## 踩坑：后台服务"开关是开的"不等于"服务在跑"（2026-10-31，P1）

**现象**：厂商划卡杀掉进程后重开 App，界面显示"网络在线，后台巡检中"，`dumpsys` 里却是 0 ServiceRecord。
**根因**：SharedPreferences 里的 `enabled=true` 与服务存活是两件事，进程被杀后两者脱节；
状态文本是上一次留下的旧值，而 `PortalViewModel` 里没有任何重新拉起服务的路径。
**修复**：新增 `BackgroundServiceRuntime` 进程内存活标记（`onCreate`→markRunning、`onDestroy`→markStopped）；
ViewModel 初始化时若 `enabled=true` 而运行时标记缺失，就按原设置重新拉起服务并纠正陈旧状态文本。
**教训**：① 持久化的"用户意图"和运行时的"客观事实"必须分开建模，不能用一个开关兼表两义；
② 进程内存标记是识别"进程被杀"的廉价可靠手段——磁盘上的状态活不过进程死亡。

## 踩坑：SharedPreferences 值不变时不写盘，别拿 mtime 当心跳（2026-10-31）

**现象**：用 `stat -c %Y` 盯后台状态文件，mtime 长时间不动，差点误判成"巡检循环停了"。
**根因**：`SharedPreferences.Editor.apply()` 在**值未变化时不会触发磁盘写入**，
状态文本每轮都一样 → 文件内容不变 → mtime 不动。循环其实一直是好的。
**教训**：判据要选"每次都变"的东西。改用 logcat 打点后真相立现：
后台循环 60s 一轮稳定运行，日志比 mtime 可靠得多。

## 踩坑：Material3 1.2+ 的 Card 默认取 surfaceContainer*（2026-10-31，界面不和谐）

**现象**：自定 `lightColorScheme()` 配了 `surface`/`surfaceVariant`，卡片却渲染成 M3 基线的淡紫灰，与整体灰蓝配色打架。
**根因**：Material3 1.2 起 Card 的默认容器色改取 `surfaceContainerLow` 一组新角色；
自定义 `lightColorScheme()` 没给这些角色 → 回落到 M3 基线（紫调灰），而不是主题自己的 `surface`。
**修复**：补齐 `surfaceContainerLowest/Low/High/Highest`、`surfaceBright/Dim`、`surfaceTint`，
并在所有 Card 上显式写 `containerColor = surface`，不依赖库版本的默认角色。
**教训**：升级 Material3 时，**新增的语义角色**不会自动跟随你自定义的配色——要么补齐，要么显式指定容器色。

## 踩坑：AppOps 的 op 编号厂商不统一（2026-10-31）

**现象**：`AppOpsManager.OP_POST_NOTIFICATION` 未在公开 SDK 暴露；想按编号查，
结果 vivo 上 11 是 POST_NOTIFICATION，而 AOSP 上 26 是 CAMERA。
**修复**：不硬编码编号，改用公开 API 按**名字**解析（`checkOpNoThrow("POST_NOTIFICATION", ...)`）；
且 `unsafeCheckOpNoThrow` 是 API 29+、`checkOpNoThrow` 从 API 19 就有，要按版本分支。
**教训**：隐藏的系统常量不要凭记忆硬编码；按名字让框架解析，并按 API 级别分支。
另外实测：框架的 `areNotificationsEnabled()` 在 API 28 上**不查 AppOps**，
检测"用户关掉了应用通知"要靠它，AppOps 那层只作为其他 ROM 的保守兜底。

## 踩坑：改 TrueType 字形后必须同步 hmtx 的 lsb（2026-11-01，字体工具）

**现象**：用 fontTools 替换 `uni3010`/`uni3011` 的轮廓后，fontTools 自己读回来是对的，
但 `hmtx` 里仍是旧 lsb（790 vs 新的 xMin 1499），差 709 单位 ≈ 0.35em。
**根因**：TrueType 的字形原点由 **hmtx 的 lsb** 决定（FreeType / Minikin 按它定位），
轮廓坐标本身不决定位置；只换 glyf 不换 hmtx 就会整体平移。
**修复**：写回轮廓后立刻 `hmtx[name] = (advance, min(x))`，并把「lsb == xMin」作为工具的自检项。
**教训**：**改 glyf ≠ 改完字体**；凡是动过轮廓的工具，必须同时校验 hmtx / head / maxp 的一致性。

## 踩坑：Chromium(WebView) 里「墨迹尺寸」和「步进」会被 size-adjust 拆开（2026-11-01）

**现象**：WebView 里正文 em=97px（按 ink 宽高比反推，与 PIL 渲染逐像素吻合），
但字间步进只有 92px，而非字体 hmtx 的 1.0742em ≈ 104px；回退字体更是被缩到 92px。
**根因**：Chromium 对 fallback 字体做 size-adjust（按 ascent/descent 对齐主字体），
**墨迹按 nominal size 绘制，步进按调整后的尺寸计算**，两者不再是同一个比例。
**修复**：不要用「advance / em」反推字号，改用「ink 宽高 ÷ 字体的 ink 设计比例」；
排版类问题一律以**真机截图量像素**为准。
**教训**：**WebView 不是 Android 原生文本栈**；同一段文字在 TextView 与 WebView 里的
字号/基线/回退行为可以完全不同，诊断必须先确认渲染引擎。

## 踩坑：诊断「某个 App 显示异常」先做 STOCK 对照（2026-11-01）

**现象**：阅读页 `【】` 左右不对称，怀疑是系统字体被换成黑板报体导致。
**根因**：切到 `stock`（系统字体 100% 原厂 MiSans，一行字体代码都没跑）截图，
**同样的不对称依然存在**（`【`→正文 59px vs 正文→`】` 12px），
而黑板报体下是 71px vs 12px，差值恰好等于两种字体空格步进之差（0.11em ≈ 12px）。
⇒ 根因是**原文里 `【` 后带了一个空格**，由正文字体渲染，与字体本身无关。
**修复**：App 侧用 CSS `text-spacing-trim: trim-both` 或文本清洗去掉全角标点内侧空白。
**教训**：**先建立「什么都不改」的基线，再谈修**；没有 STOCK 对照，很容易把
App/引擎的行为误判成字体问题，然后在字体上做无效改动。

## 踩坑：`NetworkCallback.onCapabilitiesChanged` 不去抖 = 诊断日志被刷爆（2026-11-01）

**现象**：Android 15 红米上，App 静置不动，诊断事件却每 3~12 秒涨两条
（`检测到网络恢复，开始状态校准` + `网络恢复校准（第 1 次）：ONLINE`），
一分钟就把 50 条的环形缓冲区占满，**「登录成功」这类关键事件直接被挤掉**。
**根因**：`MainActivity.kt` 的 `onCapabilitiesChanged` 回调里，
只要 `NET_CAPABILITY_VALIDATED` 成立就调 `onNetworkAvailable()`，
而 Wi-Fi 的能力（信号/带宽/验证态）本身就在持续变化 ⇒ 回调高频触发。
注释写的「仅在系统完成网络验证后触发一次状态校准，避免能力抖动反复探测」
**在实现里并没有对应的去抖**——注释描述的是意图，代码没兑现。
**修复**：加时间窗去抖，或只在 `VALIDATED` 状态发生**翻转**时触发。
**教训**：**注释不是实现**；注释里出现「仅…一次」「避免…」这类量化承诺时，
必须去代码里找对应的状态机/去抖，否则那条注释就是误导。

## 踩坑：状态文案相同的两次 `onState` 会让关键事件在日志里隐形（2026-11-01）

**现象**：后台自动重登到底有没有发生，**从 App 日志里无法判断**。
**根因**：`BackgroundReconnectController.handleCaptive()` 探测到 CAPTIVE 后走 `handleLogin()`，
成功则 `healthyDelay()` → `onState(MONITORING, "网络在线，后台巡检中")`，
和重登**之前**的状态**逐字相同**；`PortalForegroundService` 虽然每次 `onState` 都打日志，
两条日志长得一模一样。
**修复**：`handleCaptive()` / `handleLogin()` 要各补一条**区分性**日志
（如「检测到需认证，开始自动重登」「重登成功」）。
**教训**：**可观测性要以「状态能否区分」为准**，不是「有没有打日志」；
状态机分支如果收敛到同一个状态文案，中间的关键路径就等于没被观测到。

## 踩坑：门户会话不能从外部打掉 App 自己的 cookie（2026-11-01）

**现象**：用 `http://172.16.11.54/eportal/InterFace.do?method=logout`（**不需要 `userIndex`**）
把门户会话注销掉后，无 cookie 的 `curl` 探测立刻 204→200（AC 注入认证页），
但 **App 仍然报「网络在线」**——它的探测请求带着自己的 session cookie，AC 认这个 cookie。
**根因**：AC 的会话以 IP+MAC 为键，但**携带有效 cookie 的请求会把会话重新挂回去**；
所以「外部注销」只能注销掉匿名会话，打不掉 App 的会话。
**教训**：要制造「需要认证」状态，**必须让 App 自己的 cookie 失效**（AC 主动过期，
或换 MAC/IP 重新接入），否则 App 看到的永远是 ONLINE。
反过来这也是个优点：App 会话**抗外部注销**。

## 踩坑：MIUI 权限弹窗的按钮文案会随历史变化（2026-11-01）

**现象**：同一次自动化里，「拒绝」按钮的坐标没变，但用户拒绝过一次之后，
左键文案变成了「**拒绝且不再询问**」；用像素/控件树取文字时两者不能混为一谈。
**教训**：**自动化要按控件文本而不是固定坐标点击**；
`uiautomator dump` + 按文本匹配 bounds 比硬编码坐标可靠得多
（本次「拒绝」`[110,2399][591,2554]`、「始终允许」`[628,2399][1109,2554]`）。

## 踩坑：Windows 的 .ps1 必须存成 UTF-8 with BOM（2026-11-01）

**现象**：仓库里的 4 个 `scripts/*.ps1` 带中文，用 **UTF-8 无 BOM** 存盘。
Windows PowerShell 5.1（用户机器上是 5.1.26100.9711）**按 ANSI(cp936) 解码无 BOM 文件**，
中文字符的末字节被吃掉、连累后面的引号 → 字符串未闭合 → 语法错误。
实测 `install_windows.ps1`、`install_windows_tray.ps1`、`uninstall_windows.ps1` 直接解析失败，
**文档里推荐的托盘安装/卸载方式在中文 Windows 上完全不可用**；
`build_windows.ps1` 侥幸能跑，但中文提示全是乱码。
**根因**：PowerShell 只对**带 BOM** 的文件按 UTF-8 解码，无 BOM 一律走系统 ANSI 代码页。
**教训**：
1. `.ps1` 一律存 **UTF-8 with BOM**（微软官方约定），不要为了躲这个坑把中文改成英文；
2. 自查方法：`[System.Management.Automation.Language.Parser]::ParseFile($f,[ref]$null,[ref]$errors)`，
   比"跑一遍看报不报错"可靠（脚本可能在出错前已经做了一半事）；
3. **连临时诊断脚本都会踩**：本次自己写的体检脚本没带 BOM，同样解析失败——
   说明这是"用 WSL 写、Windows 跑"这个工作流的通病，必须写成硬性约定 + pytest 契约。
   已由 `tests/test_windows_script_encoding.py` 守住。

## 踩坑：PowerShell 的 `$ErrorActionPreference="Stop"` 会把原生命令的 stderr 当成终止错误（2026-11-01）

**现象**：安装脚本第 2 步调用 `oit-portal stop`，该命令在「没有 daemon 在跑」时
用 `logger.error` 打日志 —— 而 `oit_portal/log.py` 的 `logging.StreamHandler()` 默认写 **stderr**。
PowerShell 5.1 在 `$ErrorActionPreference="Stop"` 下把**任何**原生命令的 stderr 输出
都升级成终止错误 → 安装脚本被打断，**托盘根本没启动**。
**根因**：`$ErrorActionPreference` 管的是 PowerShell 的错误记录，
但原生可执行文件只要往 stderr 写一行就会被捕获成 `NativeCommandError`。
**教训**：
1. 探活/清理这类「尽力而为」的调用，先临时 `$ErrorActionPreference="Continue"`，
   只看 `$LASTEXITCODE`，不要依赖 stderr 是否为空；
2. 更根本的修法是让「没有 daemon」这种**正常状态**不要走 `logger.error`
   （`stop` 已改成幂等返回 0 + INFO，与 `systemctl stop` 对未激活单元返回 0 一致）。

## 踩坑：tkinter 不是 pip 包，缺它时托盘启动即崩（2026-11-01）

**现象**：用户机器上的 Python 3.13 是最小化安装，**连 `tcl` 目录都没有** → `import tkinter` 失败
→ 托盘 App 启动即崩（退出码 3）；而 `install_windows_tray.ps1` 当时照旧打印
「完成！请在首次弹出的窗口中输入账号密码。」—— 用户只会等一个永远不弹出的窗口。
原报错文案是「托盘依赖未安装，请执行 pip install .[tray]」，但 **tkinter 根本不是 pip 包**，
让用户去 pip install 是把人引向死路。
**教训**：
1. 缺 tkinter 的指引必须指向 **Python 安装程序 → Modify → 勾选 tcl/tk and IDLE**，
   同时给出 `oit-portal configure` 这条不用界面的替代路径；
2. **任何「启动 GUI」的动作都要在报完成前验证进程真的活着**
   （`Start-Sleep` + `Get-Process`），否则就是假成功；
3. 排查方向：`import tkinter` 逐个候选解释器试一遍——用户机器上 4 个 Python 里有 3 个带 tkinter，
   不一定要逼用户重装。

## 踩坑：`pip install .[tray]` 重装本项目会撞上正在运行的入口 exe（2026-11-01）

**现象**：`build_windows.ps1` 原本先 `pip install ".[tray]" pyinstaller`。
托盘 App 正从 venv 里运行时，重装会重新生成 `Scripts\oit-portal-tray.exe`，
该 exe 被 Windows 锁住 → pip 报 `[WinError 5] 拒绝访问` → **构建在第一步就失败**。

**更正（2026-11-01 晚，同日 GitHub Actions 首轮 CI 复现后）**：
当时的解法是「构建脚本只装构建期第三方依赖（`pystray pillow pyinstaller`），**不重装本项目**」，
并把这条写进了契约测试。**这个解法是错的**——CI 上 Windows job 直接挂在
`from oit_portal.tray import ...`：`ModuleNotFoundError: No module named 'requests'`
（托盘模块会间接 import `requests` / `pycryptodome`，PyInstaller 分析导入时需要它们真装在环境里）。
**真正的根因是「托盘进程在跑、锁住了入口 exe」，不是「要重装本项目」**——
正解是**先停掉运行中的托盘，再正常装 `".[tray]"`**。
教训：
1. **绕过症状会制造新缺陷**。「不重装」看起来绕开了 WinError 5，实际上把依赖缺口带到了 CI；
   遇到「重装被占用」先问「谁占用的」，把它停掉比绕开整步更正确；
2. **本地实测通过 ≠ 结论正确**。当时的"解法"在用户机器上确实能出 exe，
   但它把一个环境假设（构建机上恰好有 requests）固化进了脚本；
3. 契约测试要断言**真实不变量**（「装项目依赖」+「停托盘在装之前」），
   而不是断言某次事故的绕行方式。

## 踩坑：pytest ≥ 9.2 会往 `propagate=False` 的 logger 挂自己的 handler（2026-11-01）

**现象**：`oit_portal.log.setup_logging()` 用 `if logger.handlers: return logger` 判断「已初始化」。
本地 pytest 9.0.3 全绿（326 例），GitHub Actions 上同样代码 **3 个日志用例全红**：
日志文件根本没被创建。
**根因**：pytest ≥ 9.2 的 logging 插件会把自己的 `LogCaptureHandler`
（与挂在 root 上的是**同一批对象**）挂到**所有 `propagate=False` 的 logger** 上——
这样 `caplog` 才抓得到不向上传播的日志。而 `setup_logging()` 自己就设了
`logger.propagate = False`，于是从第二个用例起 `logger.handlers` 里就挂着 pytest 的 handler，
旧代码把它误认成「我们初始化过了」→ `RotatingFileHandler` 根本没挂上。
**教训**：
1. **幂等判断不能看「有没有 handler」，要看「是不是自己的 handler」**——
   给本模块挂的 handler 打自有标记（`_oit_portal_own_handler`），判断只看自己挂的；
2. **「本地绿、CI 红」先怀疑依赖版本差**：本机 pytest 9.0.3 / CI 装到 pytest 9.2.0，
   行为差异就在这。CI 第一次跑要**主动对齐版本**（CI 里复现一遍再改）；
3. 复现手法：新建一个干净 venv，`pip install -e ".[dev,tray]"` 后跑同一套用例。


## 踩坑：`pip uninstall` 会静默跳过被占用的入口 exe（2026-11-01）

**现象**：卸载后 `site-packages\oit_portal` 包目录没了，但
`Scripts\oit-portal.exe` / `oit-portal-tray.exe` **还在**，并且 site-packages 里留下
`~it_portal` / `~it_portal-0.1.0.dist-info` 两个 `~` 前缀的临时目录；
**pip 全程打印「Successfully uninstalled」，没有任何报错**。
后果是：用户 PATH 上还能跑到一个指向已删包的旧启动器，
而 `pip show oit-portal` 已经查不到它（pip 会忽略 `~` 前缀目录）——
**只靠 `pip show` 做"卸载干净了没有"的验证是假阳性**。
**教训**：
1. 卸载脚本要显式清残留：从解释器本身问出 `sysconfig.get_path('scripts')` 和
   `purelib`，删掉 `oit-portal*.exe` 和 `~it_portal*`；
2. 验证也要查这两处，而不是只看 `pip show`；
3. **凡是"报告成功"的脚本，都要有一条独立的核实路径**——
   安装脚本的「完成！」和卸载脚本的「卸载完成。」原本都是无条件打印的，
   这类假成功比崩溃更伤人。

## 踩坑：重写 git 历史 ≠ GitHub 上立刻消失（2026-11-01）

**现象**：用 `git filter-repo --blob-callback` 把公开仓库里一张含**真实姓名 + 工号**的截图
在所有历史提交中的原始 blob 替换成遮盖版，并强推了分支。
本地 `git cat-file -e <旧blob>` 已经「不存在」，全新克隆里也确认只剩遮盖版。
**但 `gh api repos/.../git/blobs/<旧SHA>` 仍然返回 200 —— 旧图还能按 SHA 取到。**
**根因**：GitHub 不会在推送时立刻删除不可达对象（dangling objects），
它们留在对象库里，直到平台自己的 GC 回收为止（通常几天到几周）。
**教训**：
1. **重写历史 ≠ 立刻擦除**。想确认「真的没了」，要查对象库而不是查 ref 可达性 ——
   **唯一可靠的判据是「全新克隆里还有没有」**；
2. 已公开过敏感内容的对象，必要时只能通过 GitHub Support 申请加速清理；
3. 更好的防线在前面：**先遮盖、再推送**。本项目三个验收目录里，
   两个是在推送前就遮盖的（历史干净），只有最早那批目录真的漏了 —— 差别就在这一步；
4. 推之前先查一遍 `git ls-remote` 看哪些目录**已经**公开，比事后补救便宜得多。

## 踩坑：`.git-credentials` 里的 GitHub 账号可能不是你以为的那个（2026-11-01）

**现象**：本轮强推时 GitHub 返回 `Permission to kkkkikun/OIT-Net-Portal.git denied to LL-ki`，
而同一个会话里前两次普通 push 是成功的。查 `~/.git-credentials` 发现 github.com 那条
存的 username 是 **`LL-ki`**（文件 mtime 显示是被别的进程改写的），不是仓库归属的 `kkkkikun`。
**根因**：`credential.helper = store` 只会**盲取**第一条匹配记录，不校验该 token 对哪个账号有效；
`gh auth status` 里的活动账号（kkkkikun）与 git 推送实际用的凭据**是两套东西**。
**教训**：git 推送报 403 时先看 `git credential fill` 取出来的 username 是谁，别急着怀疑 token 过期。
需要按账号临时取凭据又不污染全局配置时，可以用**仅本次命令**生效的
`git -c credential.helper= -c credential.helper='!gh auth git-credential' push ...`。

## 踩坑：`android-actions/setup-android` 会去装早已下架的 `tools` 包（2026-11-01）

**现象**：GitHub Actions 的 Android job 挂在 `android-actions/setup-android@v3` 这一步，
日志里是 `sdkmanager` 打印 `Warning: Failed to find package 'tools'`，
随后 `Error: The process '.../sdkmanager' failed with exit code 1`。
**根因**：该 action 默认 `packages: tools platform-tools`，而 SDK 仓库里的 `tools` 包早已下架，
`sdkmanager` 找不到就以非 0 退出，把整步带崩（连带许可交互也没走完）。
**教训**：
1. **runner 镜像本来就自带完整 SDK**（`ANDROID_HOME=/usr/local/lib/android/sdk`，
   `cmdline-tools/latest/bin` 在 PATH 上），根本不需要这个 action；
   直接定位 `sdkmanager` + `sdkmanager --install "platforms;android-35" "build-tools;35.0.0"` 即可；
2. **`sdkmanager` 是交互式的**，装包前要先接受许可：`yes | sdkmanager --licenses`，
   否则会卡在 `Review licenses that have not been accepted (y/N)?`；
3. 顺手写一份 `android/local.properties`（`sdk.dir=...`），Gradle 不必再猜 SDK 位置；
4. 定位 `sdkmanager` 时别只信 `ANDROID_HOME`：按
   `PATH → ANDROID_HOME/ANDROID_SDK_ROOT → /usr/local/lib/android/sdk → ~/Android/Sdk` 依次兜底，
   找不到就**明确报错**，别让构建带着空路径往下跑。

## 踩坑：awk 正则里 `[` 是字符类开头，别用来匹配 Markdown 标题（2026-11-01）

**现象**：发版 workflow 里用
`awk '$0 ~ "^## \[" tag "\]"' CHANGELOG.md` 抽取对应版本的小节，
实测**一行都匹配不到**（awk 还会警告 `escape sequence '\[' treated as plain '['`），
发布说明会退化成一句占位话。shell 单引号 + YAML 纯量 + awk 正则三层转义叠在一起，极易写错。
**教训**：
1. **匹配固定前缀用 `index()`，不要用正则**：
   `index($0, "## [" tag "]") == 1` —— 没有转义问题，也更快；
2. **凡是「按标题抽取小节」的脚本，都要用真实文件跑一遍验证抽取结果行数**，
   不能只看 workflow 语法通过（本项目就是语法全绿、逻辑全空）；
3. 顺手让抽取同时认 `## [1.0.0]` 与 `## [v1.0.0]` 两种写法（CHANGELOG 标题不带 v、标签带 v）。
