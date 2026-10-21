# tasks.md — 全局任务追踪

> 最后更新: 2026-10-21
> 与 openspec/changes/ 的关系: 大改动走 `/opsx:propose` 生成 change 提案（openspec/changes/<name>/）；这里只记跨 change 的长期事项与日常待办。

## 进行中

### 路线B：Android 原生 App（`android/`，Debug APK 第二轮真机验收全部通过）

已接线：Compose 骨架、Chaquopy 桥接工厂、脱敏探测/单次登录桥接、手动登录（账密表单）、
首装无 protocol.json 的 SSO 表单解析（fail-closed）、本地会话关闭、网络安全配置最小例外。

第一轮真机验收（2026-10-21）发现两个缺陷并已修复：
- 首次登录误判失败 → 根因：AuthFlow 上线复测单次零容错；已加有界重试（3 次/1.5s，可注入 sleeper）
- Wi-Fi 恢复状态不刷新 → 根因：无网络监听；已加 registerDefaultNetworkCallback +
  前台恢复探测（有界重试 3 次/2s，只探测不自动登录，会话结束后静默跳过）

未接通（按 android/README.md 清单）：
- [x] 设置页（2026-10-21：网络恢复/前台自动刷新两个开关，AppSettingsStore 持久化，默认开启）
- [x] 日志查看（2026-10-21：会话内诊断事件卡，最近 50 条脱敏事件，界面展示最新 10 条）
- [ ] Capture（延后：本校协议已实测确认，移动端首装可无 protocol.json fail-closed 登录，非必需）
- [ ] 后台自动重连（前台 Service 接管认证流程 + 运行时通知权限，按用户要求仅在确需后台常驻时接入，开关保持禁用）
- [x] 凭据安全存储（2026-10-21：Android Keystore AES-256/GCM 加密 + 私目录偏好只存密文；记住密码用户明示、默认不勾选、不自动登录；登录成功才保存，取消勾选登录成功即清除）
- [x] 网络恢复回调（2026-10-21）
- [x] 首次编译 → APK 构建（2026-10-21，无 Wrapper，用本机 Gradle 8.9 + 命令行代理参数）
- [x] 第二轮真机验收全部通过（2026-10-21）：首次登录直接显示在线、Wi-Fi 断开置离线、恢复后自动刷新、重试登录、结束会话后网络事件不触发重登、重新登录

## 待办

- [ ] Jetson Nano 实机端到端验证（install_linux.sh 全流程，清单见 docs/linux-setup.md）

## 阻塞项

（暂无）

## 已完成（近期）

- [x] 移动端桥接 + 首装 SSO 适配器（`mobile_bridge.py` / `mobile_sso.py`）— 2026-10-20
- [x] Linux（systemd）支持（daemon SSID 扩展 + install/uninstall + service 模板 + docs）— 2026-10-16（`4ce38a1`）
- [x] OpenSpec 项目初始化（specs 五域 + CLAUDE.md 索引）— 2026-10-16（`dbb878d`）
- [x] 品牌：SVG logo（蓝色版定稿）+ 社交预览卡 + README 重排 + MIT LICENSE — 2026-10-16（`ffa69aa`）

---

## 维护说明

- **开始新会话**: 读本文件 + SNAPSHOT.md
- **完成事项**: 从「进行中」移到「已完成」，注明日期与 commit
- **大改动**: 不要直接写代码，先 `/opsx:propose` 走 OpenSpec 流程
- **周期清理**: 条目膨胀时调用 openspec-archivist 清理
