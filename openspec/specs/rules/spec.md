# Rules Spec — oit-portal

> 版本: 1.0.0 | 最后更新: 2026-10-16

## Purpose

定义项目的编码规范与开发流程。本文件是规则的唯一事实来源，CLAUDE.md / AGENTS.md 只做索引不重复全文。整合三大规则体系：Karpathy Guidelines（行为约束）、务实编码原则（代码质量）、Workflow Designer（流程框架）。

## Requirements

### Requirement: 命名即文档

标识符 MUST 精准、可读、可搜索，名称 SHALL 揭示意图。

#### Scenario: 命名变量和函数

- **WHEN** 创建新的变量、函数或类
- **THEN** 避免缩写与单字母变量（循环计数器除外）；布尔值用 is/has/can/should 开头；集合用复数

### Requirement: 函数单一职责

函数 MUST 短小、只做一件事、无副作用。

#### Scenario: 编写函数

- **WHEN** 编写或重构函数
- **THEN** 理想 < 20 行，最多不超过一屏；不修改输入参数；抽象层级一致

### Requirement: 测试覆盖铁律

核心业务逻辑 MUST 有测试，先写失败测试再写实现（TDD）。所有测试 MUST 无网络。

#### Scenario: 实现新功能

- **WHEN** 实现新的业务逻辑
- **THEN** 用 pytest 编写对应用例（FakeSession + fixture 状态机），测试通过后才算完成

#### Scenario: 修改协议相关代码

- **WHEN** 修改 sso.py / eportal.py 的协议逻辑或 CAPTURED 块
- **THEN** 同步更新 tests/test_capture_wizard.py 或对应测试夹具

#### Scenario: 时间相关断言

- **WHEN** 测试涉及时间断言
- **THEN** make_config 强制 jitter_ratio = 0.0，断言精确时间值

#### Scenario: 提交前检查

- **WHEN** 准备提交代码
- **THEN** 运行 python -m pytest 全绿；确认无魔法数字/字符串；注释只解释"为什么"

### Requirement: 外科手术式修改

修改现有代码时 MUST 只改必须改的，MUST NOT 顺手"改进"相邻代码。

#### Scenario: 修改现有代码

- **WHEN** 修改现有代码
- **THEN** 不重构没坏的东西；匹配现有风格；删除自己改动产生的孤儿 import/变量，但不删除先前存在的死代码（除非被要求）

#### Scenario: 控制改动范围

- **WHEN** 每行改动都应能直接追溯到用户需求
- **THEN** 出现无法追溯的改动时回滚

### Requirement: 简单优先

MUST 用最小代码解决问题，MUST NOT 添加投机性功能。

#### Scenario: 评估实现方案

- **WHEN** 存在多种实现路径
- **THEN** 选最简单的；问自己"资深工程师会说这过度复杂吗"，是则简化

### Requirement: 编码前先思考

开发者 MUST NOT 假设、MUST NOT 隐藏困惑，MUST 暴露权衡。

#### Scenario: 需求不明确

- **WHEN** 存在多种解读或假设不确定
- **THEN** STOP，列出所有解读，问用户；不 silently 选择

### Requirement: 显式胜于隐式

依赖 MUST 显式注入，常量 MUST 命名不用裸值。

#### Scenario: 定义常量

- **WHEN** 代码中出现配置数字或字符串
- **THEN** 提取为命名常量（如 MAX_RETRY_COUNT）

### Requirement: 协议字段编辑纪律

CAPTURED 块与协议文档（docs/protocol-notes.md）MUST 同步维护。

#### Scenario: 确认协议项

- **WHEN** 某项协议字段经实测确认
- **THEN** 在 docs/protocol-notes.md 对应行把状态改为 `✅ 已确认` + 日期，不要只改代码不更新文档

#### Scenario: 表单 action 解析变更

- **WHEN** 修改 htmlutil.form_action 或 capture.py 的表单逻辑
- **THEN** 先读 tests/test_analyze_form_form_without_action_defaults_to_page_url（用户学校实测场景：form 无 action = 提交当前 URL 含原 query）

### Requirement: 工作流门控

复杂任务 MUST 按 Phase → Gate → Task 推进，Gate BLOCK MUST 记录原因。

#### Scenario: 多步任务

- **WHEN** 任务包含多个可验证步骤
- **THEN** 简述计划（步骤 → verify: 检查点），循环直到每步验证通过

#### Scenario: 被阻塞

- **WHEN** 无法继续（缺信息、测试失败、需求矛盾）
- **THEN** 明确记录阻塞原因，向用户提问，不猜测前进

### Requirement: 文档维护

SNAPSHOT.md / tasks.md 是日常状态同步点，specs/learned/ SHALL 记录踩坑。

#### Scenario: 会话开始

- **WHEN** 开始新会话
- **THEN** 读 CLAUDE.md 索引 → .claude/docs/SNAPSHOT.md → tasks.md

#### Scenario: 解决棘手问题后

- **WHEN** 花费大量时间解决一个坑（如 AES key 每次变化、form 无 action）
- **THEN** 记录到 openspec/specs/learned/spec.md，包含症状/根因/解决方案/预防
