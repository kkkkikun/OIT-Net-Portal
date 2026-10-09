# 协议确认记录（protocol-notes）

> 抓包结论逐条填入本表。状态：`待确认` → `已确认` / `确认不存在`。
>
> **获取方式**：校内未登录状态运行 `oit-portal capture` 向导，成功后自动写入
> `<配置目录>/protocol.json` 覆盖 `CAPTURED` 占位值（无需手改代码）；
> 向导报告 `capture-report.txt` 中的结论同步登记到下表。

## C1 触发链

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C1.1 | 未认证时入口形态 | ✅ 已确认（2026-10-09 抓包报告实测） | AC 对探测 URL 返回 **200 注入 JS 跳转页**（`<script>top.self.location.href='http://172.16.11.54/eportal/index.jsp?wlanuserip=<hex>&...&t=wireless-v2'</script>`），**非 302**；链路：注入页 → ePortal index.jsp →（JS 跳）→ SSO `authorize`（带 client_id/redirect_uri）→ 登录表单。已由 `discover.py` 统一处理三种页面级跳转 |
| C1.2 | SSO 会话 cookie 名 | ✅ 已确认 | `SID`（authorize GET 时 Set-Cookie: SID=...）+ `JSESSIONID`（index.jsp 跳转时）+ `query`、`login_from`（authorize 时）|
| C1.3 | ePortal 服务器地址 | ✅ 已知 | `http://172.16.11.54`（加密参数模式，`t=wireless-v2`） |

## C2 SSO 登录表单

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C2.1 | 表单 action（POST 端点） | ✅ 已确认 | `<form method="POST">` **无 action 属性**（浏览器原生行为：提交到当前 URL）。端点 = `http://open.oit.edu.cn:8090/auth/oauth/authorize?response_type=code&client_id=b50485d1-4e49-4d54-95b4-491c0b69ce15&redirect_uri=http%3A%2F%2F172.16.11.54%2Feportal%2Flogin_sso.jsp%3F<hex>%26...`（**整个 query 串原样回传**）。向导已实现：`htmlutil.form_action` 见到 `<form>` 无 action 返回哨兵 `""`，`analyze_form` 用 `page_url` 兜底 |
| C2.2 | 用户名字段名 | ✅ 已确认 | `name="username"`（`<input v-model="username" type="text">`，placeholder="职工号/学号"）|
| C2.3 | 密码字段名 | ✅ 已确认 | **注意：密码是 hidden 字段**——`<input name="password" type="hidden" v-model="password">`。原始输入 `<input v-model="password_" :type="passwordType">`（**无 name 属性**），Vue `watch` 监听 `password_` 变化后调用 `encrypt()` 把密文塞进 hidden `password` 字段再随表单提交。向导已实现：fallback 逻辑识别 `name="password"` 的隐藏输入 |
| C2.4 | 隐藏字段清单 | ✅ 已确认 | 3 个 hidden：<br>• `fingerprint`（FingerprintJS 异步填，初始空）<br>• `__token__`（HTML 静态值，**与 AES key 源串相同**：`550b3d92549b791a351f8fdcae939d1a`）<br>• `password`（Vue watch 加密后密文）|
| C2.5 | 验证码 | ✅ 已确认：**不存在**（2026-10-09 用户观察） | 账密自动登录路径无阻碍。页面里 `<input v-model="verify_code">` 与 `sliderVerify()` 仅为条件式图片码（`check_image_verify` 标志位 false 时跳过）|
| C2.6 | 密码前端加密方式 | ✅ 已确认（2026-10-09 多次抓包对比） | **AES-128-CBC，ZeroPadding，base64**；⚠️ **key=iv 每次页面加载动态变化**（实测：`563a38***` → `4826c9***` → `1c7358***`）。运行时由 `sso.login_password` 从当次登录页内联脚本重新提取（`htmlutil.find_aes`），protocol.json 存量 key 仅兜底。<br>**新发现**：key 字符串就是表单 `__token__` 字段的完整值（32 字符）的前 16 字符 |
| C2.7 | 登录失败响应格式 | ✅ 已确认 | 错误时返回 200/302 HTML 错误页（非 JSON），如"账号或密码错误"。成功时 302 Location 指向 `login_sso.jsp?code=...` |

## C3 code 换上线

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C3.1 | 登录成功后 code 出现位置 | ✅ 已确认 | 302 Location 头：`Location: /eportal/login_sso.jsp?code=<code>&wlanuserip=...&mac=...&t=wireless-v2&...` |
| C3.2 | login_sso.jsp 响应类型 | ✅ 已确认 | **(a) 服务端直通**：login_sso.jsp 直接处理 code + 加密参数，调用标准锐捷 ePortal 上线接口（`InterFace.do?method=getOnlineUserInfo` 等），重定向到 `success.jsp?userIndex=<hex>&liveInterval=<0:秒数>` |
| C3.3 | 上线调用链 | ✅ 已确认 | `login_sso.jsp` → `InterFace.do?method=...`（xhr）+ `userV2.do?method=...`（xhr），前端用 `AuthInterFace.js` 作为 Initiator |
| C3.4 | 成功判定标记 | ✅ 已确认 | URL `success.jsp?userIndex=<32位hex>&liveInterval=<0:秒数>`（页面正文："您当前登录的用户：<姓名>"）|
| C3.5 | userIndex / keepaliveInterval | ✅ 已确认 | `userIndex` = 32 位 hex（用户哈希）；`liveInterval=0:1958`（**1958 秒 ≈ 33 分钟**，可能为心跳/巡检间隔，待 C4.3 验证）|

## C4 会话与保活

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C4.1 | SSO cookie 可否免密复用 | ✅ 已确认：**可行**（2026-10-09 用户观察） | 免密静默是主路径 |
| C4.2 | SSO cookie 实际存活时长 | ✅ 部分确认：**>5 小时，次日必定失效**（约 6–24h 区间） | 每天最多一次账密重登，其余时间全程免密 |
| C4.3 | 空闲超时（挂机被踢时间） | 🟡 部分推测 | `success.jsp?liveInterval=0:1958` 提示 1958 秒（≈33 分钟）作为心跳/巡检间隔。**实际空闲超时**可能与该值相关（学校可能在该间隔前后主动断线或由前端定时刷新），待长时挂机实测 |
| C4.4 | 心跳接口（成功页 JS） | 🟡 已发现 | 成功页调用 `InterFace.do?method=getOnlineUserInfo` + `userV2.do?method=getErrorMsg`（Initiator: `AuthInterFace.js`），频率由 `liveInterval` 控制 |
| C4.5 | 多设备同账号互踢 | 待确认 | `<CAPTURE:E-3>` |
| C4.6 | 注销接口 | 🟡 已发现 | 成功页有「注销」按钮，链到 `/eportal/logout.jsp?ms2g=...`（document 302 重定向）。具体 API 端点待确认 |
| C4.7 | 已在线判定特征 | ✅ 已确认 | 探测 URL 返回 204 / `Success`（多探测点双确认）|
