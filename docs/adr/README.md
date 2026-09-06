# Architecture Decision Record 索引

ADR 一旦标记为“已接受”，不得通过实现细节静默推翻。需要修改时，应新增 ADR 将旧决策标记为 Superseded，并同步更新规范与测试。

- [ADR-001：使用强类型 DAG 保存 Rule Definition](ADR-001-rule-representation.md)
- [ADR-002：使用按时间戳分批的事件驱动执行模型](ADR-002-event-driven-execution.md)
- [ADR-003：使用有符号 int64 纳秒表示分析时间](ADR-003-integer-nanosecond-time.md)
- [ADR-004：将 Rule Definition 编译为私有、不可变 IR](ADR-004-compiler-and-ir.md)
- [ADR-005：保留 UNKNOWN，禁止静默映射 Missing Data](ADR-005-missing-data.md)
- [ADR-006：同 Timestamp 使用 Microstep 与分阶段 Temporal Matching](ADR-006-same-timestamp-scheduling.md)

