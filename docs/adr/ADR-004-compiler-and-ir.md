# ADR-004：将 Rule Definition 编译为私有、不可变 IR

- 状态：MVP 已接受
- 日期：2026-09-05

## 背景（Context）

保存的 Graph 面向可读性与长期兼容，而执行需要已解析的 Binding、Type、Topology、Policy、Subscription 和紧凑 Operator State。直接执行保存的 Node 会把 Schema、GUI 演进和 Runtime 内部实现耦合在一起。

## 决策（Decision）

先验证 Rule Definition，再编译为不可变、强类型、私有 IR。Compiler 负责解析 Block Version 与 Signal Binding、物化 Default、Lower Temporal Sugar、安排 Operator 顺序、提取 Subscription，并生成 Source Map。Runtime Object 由 IR 构建，永不写入规则文件。

## 备选方案（Alternatives）

- 直接解释 Authoring Graph：初期类较少，但会造成持久耦合并在运行时重复验证。
- 生成 Python Source：难以保障安全、诊断、迁移与可复现性。
- 立即把 IR 设为公共持久格式：在结构尚未验证之前增加第二套长期兼容承诺。

## 影响（Consequences）

系统会存在三类显式模型，因此必须测试它们之间的映射。优化和 Runtime 重构无需迁移用户规则。IR 的调试序列化允许随 Engine Version 变化，并必须标明版本。

