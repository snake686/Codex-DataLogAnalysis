# ADR-005：保留 UNKNOWN，禁止静默映射 Missing Data

- 状态：MVP 已接受
- 日期：2026-09-05

## 背景（Context）

车辆日志可能缺少 Signal、Value 可能过期、存在数据间隙、Decode Failure 或未完成的结束窗口。把所有缺失都视为失败会产生误报；视为通过则会隐藏风险。

## 决策（Decision）

Condition 使用 Kleene 三值逻辑。缺失、过期或无效 Operand 产生 UNKNOWN；静态 Type/Unit 不兼容则使 Rule 为 INVALID。Evaluation Result 区分 PASS、FAIL、UNKNOWN、ERROR、NOT_EVALUATED、INVALID 和 SKIPPED，并包含 `DATA_MISSING`、`INCOMPLETE_WINDOW` 等结构化原因码。Runtime 必须追踪 Window Coverage：没有 Target 只有在 Baseline 已知且窗口完整可观测时才能判 FAIL。任何将 UNKNOWN 映射为其他结果的策略都必须显式保存并写入报告。

## 备选方案（Alternatives）

- Missing = FAIL：混淆产品行为违反与证据质量问题。
- Missing = PASS：不安全且具有误导性。
- 所有 Missing 都抛出异常：阻碍有效的部分分析，并混淆数据状况与 Engine Fault。
- 仅使用 Null 而没有三值逻辑：会导致不同 Operator 对缺失值的行为不一致。

## 影响（Consequences）

所有 Block 都需要 UNKNOWN/Coverage 测试，Report 必须清晰展示无法确定的结果，Aggregation 也会更细致。GapEnd 不恢复旧 Held Value，必须等待新 Good Sample。若需要检查数据可用性，应编写独立、显式的规则。
