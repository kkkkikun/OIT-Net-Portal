# tasks.md — 全局任务追踪

> 最后更新: 2026-10-16
> 与 openspec/changes/ 的关系: 大改动走 `/opsx:propose` 生成 change 提案（openspec/changes/<name>/）；这里只记跨 change 的长期事项与日常待办。

## 进行中

（暂无）

## 待办

（暂无）

## 阻塞项

（暂无）

## 已完成（近期）

- [x] OpenSpec 项目初始化（specs 五域 + CLAUDE.md 索引）— 2026-10-16
- [x] daemon 网络恢复 burst 探测 + WiFi SSID 触发（`337fa06`）
- [x] Termux 日志两级降级 + 状态目录迁移（`ccc2b3c` / `a394952`）
- [x] capture 向导支持 form 无 action / Vue 隐藏密码字段（`f596fac`）

---

## 维护说明

- **开始新会话**: 读本文件 + SNAPSHOT.md
- **完成事项**: 从「进行中」移到「已完成」，注明日期与 commit
- **大改动**: 不要直接写代码，先 `/opsx:propose` 走 OpenSpec 流程
- **周期清理**: 条目膨胀时调用 openspec-archivist 清理
