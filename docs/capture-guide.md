# 阶段 0 抓包引导清单（在校内完成）

> 目的：摸清 `open.oit.edu.cn:8090`（SSO 统一认证）和 `172.16.11.54`（锐捷 ePortal）的真实登录协议，
> 关闭 [protocol-notes.md](protocol-notes.md) 中的全部 `<CAPTURE>` 待确认项。
>
> 全程只需要一台连着校园 WiFi 的电脑 + Chrome/Edge 浏览器，**不需要安装任何抓包工具**。
> 预计耗时 30–60 分钟。抓完后把结果（截图/复制文本/导出的 HAR）交给 Claude 填充代码。

---

## 准备工作

1. 电脑连接校园网 WiFi（确保当前是**未登录**状态；如果已登录，先在认证成功页点「注销」，或断开重连 WiFi）
2. 打开 Chrome/Edge，按 `F12` 打开开发者工具 → **Network（网络）** 面板
3. 勾选：
   - ✅ **Preserve log（保留日志）** —— 关键！跳转后不丢失记录
   - ✅ **Disable cache（停用缓存）**
4. 建议开一个无痕窗口操作，避免插件和老 cookie 干扰

---

## A. 触发链抓取（拿到完整 302 跳转链）

1. 在地址栏输入并访问：`http://captive.apple.com/hotspot-detect.html`
2. 观察会被自动跳转到登录页。在 Network 面板里（类型选 **All**），从第一条请求开始逐条点击：
   - 每一条都看 **Headers → General** 里的 `Status Code`（302?）和 **Response Headers** 里的 `Location`
   - 记录每一跳的：`Request URL`、`Status`、`Location`、`Set-Cookie`
3. 对链条里**每一跳**右键 → **Copy → Copy as cURL (bash)**，粘贴保存到文本文件
4. 记下最终停留的登录表单页 URL（应该在 `open.oit.edu.cn:8090` 域下）

**要关闭的项**：完整跳转链、SSO 会话 cookie 名（Set-Cookie 里的，通常类似 `JSESSIONID` / `SESSION` / `TGC`）

> 💡 如果 `captive.apple.com` 打不开，换 `http://connect.rom.miui.com/generate_204` 或直接访问 `http://172.16.11.54` 触发。

## B. 登录表单分析（搞清字段名和加密方式）

停留在登录表单页，按 `F12` 切到 **Elements（元素）** 面板：

1. 找到 `<form>` 标签，记录：
   - `action="..."`（表单提交到哪个 URL）
   - `method`（POST 还是 GET）
2. 列出**所有** `<input>` 的 `name`（包括 `type="hidden"` 的隐藏字段，全部抄下来）
3. 检查有无验证码：表单里是否有 `<img>` 验证码图片 / `validcode` / `captcha` 字样
4. 检查密码加密（重要）：
   - 在 Elements 里 `Ctrl+F` 搜索：`encrypt`、`publicKey`、`jsencrypt`、`rsa`、`aes`、`CryptoJS`、`JSEncrypt`
   - 或切到 **Sources（源代码）** 面板看页面引入了哪些 JS 文件
   - 如果搜到 RSA 公钥（`-----BEGIN PUBLIC KEY-----` 或一长串 `MIGfMA0GCSq...`），把公钥完整复制下来
5. 在 Network 面板里点登录表单页那条文档请求，记录 **Response Headers → Set-Cookie**（cookie 名 + 属性）

**要关闭的项**：表单 action、字段名清单、有无验证码、密码是否前端加密（及公钥）

## C. 登录提交抓取（最关键的一步）

> 先故意输错一次密码（观察失败响应格式），再输正确的。

1. 在登录表单里**故意输错密码**，点登录 → Network 里找到那条 POST/GET 请求：
   - 点开 **Payload（载荷）** 面板：记录所有参数名和值（密码值如果是 100+ 位的乱码 = 有前端加密；如果是你输入的原文 = 明文传输）
   - 记录 **Response**：返回了什么（错误提示 JSON？还是重新渲染的页面？）
2. 删掉错误记录（🚫 图标），**输入正确密码**登录成功。此时重点看：
   - 登录提交那条请求（Copy as cURL 保存）
   - 随后的 302 跳转链：`authorize` → 携带 `code=xxx` → `172.16.11.54/eportal/login_sso.jsp?code=...`
   - **login_sso.jsp 这条请求**：它的响应是什么？
     - (a) 直接 302 到成功页 / 返回「登录成功」HTML → 服务端处理，我们只需 GET 它
     - (b) 返回一个带 JS 的 HTML，随后 Network 里又出现 `InterFace.do` 或其他 XHR 请求 → JS 处理，需要模拟那条 XHR（Copy as cURL 保存）
3. 找到最终的**成功页**（「认证成功/上线成功」字样的页面）：
   - 在 Elements/Response 里搜索：`userIndex`、`keepaliveInterval`，把值抄下来
   - 如果页面 Sources 里有 JS 定时器发心跳（搜 `setInterval`），记下心跳请求的 URL

**要关闭的项**：登录 POST 端点与参数、密码加密方式、错误响应格式、code 回跳处理方式（a/b 二选一）、userIndex/keepaliveInterval、有无心跳接口

## D. 会话有效期实验（决定能否「免密码静默登录」，重中之重）

> 目的：确认 SSO 登录一次后，cookie 能活多久。cookie 活得久 → 之后脚本全程免密码。

1. 刚登录成功后，**新开一个标签页**，把 A 步骤里记下的原始 `http://open.oit.edu.cn:8090/auth/oauth/authorize?...` 长链接粘贴进去访问：
   - ✅ 如果**不出现登录表单**、直接跳到成功页（URL 里带 `code=`）→ 会话有效，脚本可免密复用
   - ❌ 如果又出现登录表单 → 会话不可复用，脚本每次都要提交账密
2. 如果第 1 步是 ✅：**1 小时后**再试一次，**第二天**再试一次，记录到哪次开始失效
3. 顺便观察：注销（如果成功页有注销按钮）后 cookie 是否随之失效

**要关闭的项**：SSO 会话是否可复用、实际存活时长

## E. 掉线条件观察（决定保活策略）

1. 登录成功后**挂机 1 小时**什么都不做（关掉所有联网程序），再看是否还在线（访问 `http://connect.rom.miui.com/generate_204`，空白页=在线，跳转=掉线）
2. 如果被踢了：登录成功页是否有「保持在线」心跳 JS？记录心跳 URL 和间隔
3. （可选）如果平时遇到过「手机和电脑不能同时在线」（同账号互踢），记录现象

**要关闭的项**：空闲超时时间、是否需要心跳保活、是否多设备互踢

---

## 交付物清单（做完后交给 Claude）

- [ ] 每一跳的 Copy as cURL（A、C 步骤）
- [ ] 登录表单页的 `<form>` action + 全部 input name + Set-Cookie（B 步骤）
- [ ] 密码加密结论：明文 / RSA（附公钥）/ 其他（B、C 步骤）
- [ ] 有无验证码的结论（B 步骤）
- [ ] 正确登录的完整请求/响应记录 + login_sso.jsp 响应类型 a 或 b（C 步骤）
- [ ] userIndex / keepaliveInterval 值（C 步骤）
- [ ] 会话复用结论 + 存活时长（D 步骤）
- [ ] 空闲超时 / 心跳 / 互踢结论（E 步骤）
- [ ] （加分）Network 面板右键 → **Save all as HAR with content** 导出的 .har 文件（记得先删敏感值，或交给我们时说明，我们会脱敏后入库 `tests/fixtures/`）

> ⚠️ 交给 Claude 前可自行脱敏：HAR/文本里的真实密码、完整 cookie 值可以打码，字段名和 URL 保留即可。
