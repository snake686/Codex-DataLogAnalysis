# ADR-002：使用按时间戳分批的事件驱动执行模型

- 状态：MVP 已接受
- 日期：2026-09-05

## 背景（Context）

CAN Signal 稀疏、异步且周期不同。整份日志重采样可能制造并不存在的值并消耗大量内存。离线分析与未来实时分析应共享同一套语义。

## 决策（Decision）

标准化事件按 Timestamp Batch 进入增量 Dataflow Scheduler。Stateful Temporal Operator 使用显式状态机和调度 Deadline。Watermark 用于证明时间窗口完整。固定时间栅格重采样只是一种需要记录策略的可选预处理，不是 Engine 的规范执行模型。

## 备选方案（Alternatives）

- 整份日志使用 DataFrame/向量化执行：方便，但内存占用高，并且不适合实时 Stream 和逐 Trigger 状态。
- 固定周期仿真循环：类似 Simulink，但会人为选择时钟并隐藏插值或保持策略。
- 通用 CEP 框架：能力强，但在工作负载尚未证明必要性前会引入沉重依赖和外部语义。

## 影响（Consequences）

Runtime State 必须跨 Chunk 保留，内存规模取决于规则和时间窗口，而不是日志长度。Alignment、Freshness、Ordering 和 Watermark 都必须显式定义。未来可在不改变语义契约的前提下对纯计算子图进行向量化。

