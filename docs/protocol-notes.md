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
| C1.2 | SSO 会话 cookie 名 | 待确认 | `<CAPTURE:B-5>` |
| C1.3 | ePortal 服务器地址 | 已知 | `http://172.16.11.54`（加密参数模式，`t=wireless-v2`） |

## C2 SSO 登录表单

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C2.1 | 表单 action（POST 端点） | 待确认 | `<CAPTURE:B-1>` |
| C2.2 | 用户名字段名 | 待确认 | `<CAPTURE:B-2>`（预设 `username`） |
| C2.3 | 密码字段名 | 待确认 | `<CAPTURE:B-2>`（预设 `password`） |
| C2.4 | 隐藏字段清单 | 待确认 | `<CAPTURE:B-2>` |
| C2.5 | 验证码 | ✅ 已确认：**不存在**（2026-10-09 用户观察） | 账密自动登录路径无阻碍 |
| C2.6 | 密码前端加密方式 | 待确认 | `<CAPTURE:B-4>`（无 / RSA+公钥 / 其他） |
| C2.7 | 登录失败响应格式 | 待确认 | `<CAPTURE:C-1>` |

## C3 code 换上线

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C3.1 | 登录成功后 code 出现位置 | 待确认 | 预设：302 Location `login_sso.jsp?code=...` |
| C3.2 | login_sso.jsp 响应类型 | 待确认 | `<CAPTURE:C-3>`：(a) 服务端直通 / (b) JS 再调接口 |
| C3.3 | (b) 情况下的接口与参数 | 待确认 | `<CAPTURE:C-3>`（预设锐捷标准 `InterFace.do?method=login`） |
| C3.4 | 成功判定标记 | 待确认 | `<CAPTURE:C-3>`（预设「成功/userIndex」关键字） |
| C3.5 | userIndex / keepaliveInterval | 待确认 | `<CAPTURE:C-4>` |

## C4 会话与保活

| ID | 项目 | 状态 | 结论 |
|----|------|------|------|
| C4.1 | SSO cookie 可否免密复用 | ✅ 已确认：**可行**（2026-10-09 用户观察） | 免密静默是主路径 |
| C4.2 | SSO cookie 实际存活时长 | ✅ 部分确认：**>5 小时，次日必定失效**（约 6–24h 区间） | 每天最多一次账密重登，其余时间全程免密 |
| C4.3 | 空闲超时（挂机被踢时间） | 待确认 | `<CAPTURE:E-1>` |
| C4.4 | 心跳接口（成功页 JS） | 待确认 | `<CAPTURE:E-2>` |
| C4.5 | 多设备同账号互踢 | 待确认 | `<CAPTURE:E-3>` |
| C4.6 | 注销接口 | 待确认 | `<CAPTURE:E-4>`（预设 `InterFace.do?method=logout`） |
| C4.7 | 已在线判定特征 | 预设 | 探测 URL 返回 204 / `Success`（多探测点双确认） |
