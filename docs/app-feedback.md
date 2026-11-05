# App 反馈通道

给 App 的使用者一个**在 App 内就能用**的反馈入口：同学在设置页点「写一条反馈」，
填完直接提交；反馈进作者的 **OpenFeedback 后台**，作者随时集中看、筛选、改状态。

**作者的电脑不用开着任何服务。** OpenFeedback 跑在一台常开的服务器上（自托管），
同学提交时 App 直连那台服务器。

设计取舍与背景见 `openspec/changes/2026-11-05-switch-feedback-to-openfeedback/`。

## 为什么不用问卷链接

问卷链接必须跳出 App（浏览器/第三方页），同学会中断，而且多数问卷平台没有免登录的
程序化提交接口，收集端仍然是人工导出。

本方案是 App 内原生 Compose 表单：不跳浏览器、不开第三方页面、不需要同学注册任何账号。

## 同学怎么用

1. 打开 App → 底部「设置」→ 滚到底部 →「意见反馈」→「写一条反馈」。
2. 选类型（问题 / 功能建议 / 体验问题 / 其他），写下遇到的情况。
3. 需要的话打开「附带诊断信息」——只带最近连接状态等脱敏信息，不含账号密码。
4. 点「提交反馈」。提交成功设置页会显示「反馈已收到」。

### 断网了会怎样

**不会丢，也不会重复。**

- 提交时如果没网，反馈会先存在手机本机（App 私有目录），App 照样提示「反馈已收到」；
- 之后网络恢复，App 会**自动补发**，你不需要手动再点一次提交；
- 每条反馈带一个客户端生成的唯一标识（`submissionId`），服务端按它去重，
  所以补发**不会**在后台产生两条一样的记录。

> 反馈在补发成功之前只留在手机本地，不会外传。卸载 App 会一并清掉。

---

## 作者怎么配

前置条件：**你已经部署了一套 OpenFeedback 服务**（它负责收反馈 + 提供管理后台）。
没有的话先看 OpenFeedback 仓库的 `docs/DEPLOYMENT.md`。

需要从 OpenFeedback 那边拿到两样东西：

| 要什么 | 从哪来 | 说明 |
|---|---|---|
| 服务地址 | 部署时设的 `OF_PUBLIC_HOST` | 例如 `https://feedback.example.com` |
| SDK 的 Maven 仓库地址 | `https://<服务地址>/maven/` | OpenFeedback 自带，只读静态仓库 |

### 第 1 步：填服务地址

编辑 `android/local.properties`（该文件已在 `.gitignore` 里）：

```properties
oit.feedback.endpoint=https://feedback.example.com
```

`local.properties` 里**不需要**任何密钥。OpenFeedback 的提交接口不接受客户端密钥，
APK 里只有公开的应用标识 `oit-net-portal` 和服务地址。

> 如果之前按旧文档配过 `oit.feedback.secret`，那行可以删掉了 ——
> 旧配置是飞书 webhook 的签名 token，OpenFeedback 用不到它。

### 第 2 步：告诉 Gradle SDK 仓库在哪

OpenFeedback 的 SDK（`com.kkkkikun.openfeedback:openfeedback-core`）在服务端的 `/maven/` 路径下。
仓库地址通过 Gradle 属性 `oit.openfeedback.mavenUrl` 传入：

```bash
cd android
./gradlew assembleDebug \
  -Poit.openfeedback.mavenUrl=https://feedback.example.com/maven/
```

如果**不能连公网**（例如内网开发机），可以把 SDK 构件拉到本地再指过去：

```bash
# 在能访问服务端的机器上
curl -O https://feedback.example.com/maven/com/kkkkikun/openfeedback/openfeedback-core/0.1.0/openfeedback-core-0.1.0.aar
# 然后
./gradlew assembleDebug -Poit.openfeedback.mavenUrl=file:///abs/path/to/maven-repo
```

> 不传这个属性也能构建，但会退回默认地址 `https://feedback.example.com/maven/`，
> 拉到的是一份**示例** SDK，不是你部署的那台。

### 第 3 步：构建与安装

```bash
cd android && ./gradlew assembleDebug
```

装好后同学端直接就能用。

### 第 4 步：在后台处理

打开 `https://<服务地址>/admin`，用管理员账号登录：

- **列表页**：按应用 / 状态 / 类型筛选，可以搜正文；
- **详情页**：看正文、诊断摘要、设备信息（机型、系统版本、App 版本），
  可以改处理状态（待处理 / 处理中 / 已解决 / 已关闭）、加内部备注、下载同学附的截图；
- **状态历史**：每次改状态都留痕，方便回溯。

> 反馈内容与截图**只有登录后的管理员能看到**，公开的提交接口不接受查询。

---

## 改服务地址（不重新构建）

App 里可以随时改通道地址，存在本机设置里。换了网络、或者作者换了服务器时，
可以在 App 内把地址改成新的，下次提交就走新地址。

---

## 安全须知（请认真读）

**APK 里没有任何服务端凭据。**

这一点和旧方案（飞书直发）有本质区别：

| | 飞书直发（旧） | OpenFeedback（现在） |
|---|---|---|
| APK 里的东西 | webhook 地址 + 签名 token | 公开的 `appId` + 服务地址 |
| 拿到地址的人能干什么 | **能往你的表格/群里写内容** | 只能提交反馈（会被限流） |
| 服务端凭据 | 在飞书后台 | **不在 App 里，只在服务器上** |

OpenFeedback 的提交接口是公开的（任何人都能提交），这是刻意的设计：
反馈端不需要鉴权，服务端靠下面几层兜底：

- **按 IP 限流**：每个应用每 IP 每小时 10 条，超了返回 429；
- **服务端校验**：正文长度、分类合法性、附件类型与大小都在服务端再校验一遍，
  不信任客户端；
- **附件魔数校验**：只接受真正的 JPEG / PNG / WebP，改扩展名绕过不了；
- **后台需要登录**：只有登录后的管理员能看到反馈内容与截图。

其它边界：

- 反馈载荷只有同学填的正文 + 脱敏摘要，**没有**账号、密码、Cookie、完整 URL。
- 诊断摘要里含 URL、token/password/cookie 字样或账号字样的行**整行丢弃**
  （不是打码，避免留下「这里原来有个账号」的痕迹）。
- App 里不存任何第三方账号密码。

---

## 集中处理

在 OpenFeedback 后台做：

- 按「应用」筛选：先看问题类。
- 改「状态」：`待处理` / `处理中` / `已解决` / `已关闭`，按它筛选就知道还剩哪些。
- 加内部备注：记下跟进过程，同学看不到。
- 导出：见 OpenFeedback 仓库的 `docs/API.md`。

---

## 常见问题

**同学提交提示「反馈通道尚未配置」**
构建时没填 `oit.feedback.endpoint`，或 App 里的地址被清空了。

**提交提示「反馈提交失败，请稍后重试」**
- 服务端地址填错，或者 App 当前网络访问不了那台服务器；
- 反馈类型不被服务端接受（只会是本 App 的四个分类，一般不会）；
- 服务端触发了限流（同一 IP 一小时内提交超过 10 条）。

**App 显示提交成功，后台却没有这条反馈**
先看 App 是不是**离线**提交的：离线时反馈存在本机，等联网后会自动补发，
这时后台要过一会儿才会出现。如果联网后等了很久仍然没有，检查：

- 服务端的 Caddy / 反代是否正常（`GET /api/v1/health` 应返回 `{"status":"ok"}`）；
- App 的地址是否是 `https://` 开头的完整服务地址（不是 `/maven/` 那条路径）。

**能不能既进后台又留一份本机副本？**
可以。服务端是自托管的，数据库就在你自己的服务器上，定期备份即可，
见 OpenFeedback 仓库的 `deploy/backup.sh`。

---

## 回退到飞书直发

桥接实现是单点替换：把 `MainActivity.kt` 里注入的桥接从 `OpenFeedbackBridge`
换回 `ChaquopyFeedbackBridge` 即可恢复旧通道，不需要回滚服务端，也不用动表单 UI。

服务端侧想停收这个应用的反馈：把服务端数据库 `apps` 表里 `oit-net-portal`
那一行的 `enabled` 置为 false，该应用立即停止接收（客户端会收到 403 并提示
「该应用已停用接收反馈」）。
