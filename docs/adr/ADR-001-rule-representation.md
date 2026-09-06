# ADR-001：使用强类型 DAG 保存 Rule Definition

- 状态：MVP 已接受
- 日期：2026-09-05

## 背景（Context）

规则需要支持可视化编辑、脱离 GUI 保存、供 CLI/CI 复用，并能由可复用 Block 进行组合。纯 Expression Tree 无法自然共享表达式；不受限制的 Graph 则会引入语义和调度均不明确的反馈回路。

## 决策（Decision）

规则持久化为由版本化 Block Instance、命名强类型 Port 和显式 Edge 构成的有向无环图。MVP 拒绝 Cycle。GUI 展示信息不参与语义。

## 备选方案（Alternatives）

- Expression Tree/AST：结构简单，但不适合共享子图和可视化节点身份。
- 通用有环图：表达能力强，但验证、调度和时间语义明显更复杂。
- 仅使用 State Machine：适合 Sequence，不适合算术和信号 Dataflow。
- 完整 Temporal Logic 文本：精确，但目标用户不易编辑，诊断也更难解释。

## 影响（Consequences）

必须实现 Graph Validation 和稳定 ID。Authoring Graph 不直接执行。未来如需受控的状态反馈，只能通过显式 State/Delay Block 和新版本的 Compiler/Runtime 契约引入。

