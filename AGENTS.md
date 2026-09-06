# AGENTS.md

## 使命

构建并维护一套确定、可解释的汽车时序规则平台。Rule Engine 是核心领域，并且必须能够处理来自 CAN、MDF、CSV、实时数据流或仿真的标准化事件。

## 架构边界

- Parser 与基础设施代码不得把 `python-can`、`cantools`、BLF、ASC、DBC、GUI、DataFrame 或报表库对象泄漏到 domain/rule package。
- GUI 只编辑和展示 Rule Definition；不得包含规则、时间、对齐、状态或聚合语义。
- Rule Definition、compiler IR、runtime operator/state 与标准化 result 必须使用相互独立的模型。
- Report Generator 只消费 result 和 manifest model；不得检查 runtime operator。
- 依赖必须按照 `docs/architecture.md` 向内指向核心。不得为图方便引入反向依赖。
- 优先使用明确的强类型领域模型，而不是无类型字典。Pydantic 应用于序列化和配置边界，不应默认渗透整个核心。

## 规则与时间语义

- 将 `docs/time-semantics.md` 视为规范。每个时间算子都必须说明区间边界、同时间戳顺序、初始化、UNKNOWN/数据间隙行为、重叠策略、Watermark 和输入结束行为。
- 将 `docs/implementation-contract.md` 视为 MVP 接口和行为基线。实现不得自行发明与其冲突的 Port、Parameter、ID、Transaction 或 Result Contract。
- 禁止使用浮点数进行时间计算。使用经过范围检查的整数纳秒以及精确的 Duration 解析。
- 禁止把缺失、过期、无效或不完整数据静默转换为 PASS 或 FAIL。除非持久化规则显式选择其他策略，否则必须保留 UNKNOWN 和结构化原因码。
- 不得根据 “within” 一词推测 `is_true`、`becomes_true` 或 `true_throughout`；必须要求明确选择语义。
- 不得添加隐式采样对齐或插值。采样时钟、值保留和新鲜度必须是显式策略。
- MVP 禁止 Cycle。不得通过绕过验证的方式添加反馈。

## Block 与兼容性

- Block Type ID 和版本是长期契约。不得重命名，也不得在改变行为后复用原版本。
- 每个新 Block 都必须提供 Definition/Port/Parameter 文档、Validation/Lowering、Runtime 行为、UNKNOWN 测试，以及适用时的时间语义测试。
- 使用显式 `BlockRegistry`。未经 ADR 批准，不得在保存的规则中加入自动 package 扫描或可执行代码。
- Schema 变更必须分析版本影响、提供迁移测试并保留原始 Artifact/Hash。语义变更需要新的 Semantic Profile，或使用 ADR 解释兼容策略。
- IR 是私有且不可变的。不得无意中把它变成需要长期兼容的公共文件格式。

## 实施纪律

- 不为假设性的功能引入不必要的依赖或抽象。仅在已证实的边界上增加接口。
- 每项行为变更都需要测试。时间语义测试必须推进逻辑时间戳和 Watermark，禁止调用 `sleep()`。
- 保持确定性顺序、稳定诊断码、Source Map 和可复现元数据。
- Runtime State 和 Evidence 必须有界。资源耗尽必须明确产生 ERROR；禁止静默丢弃 Evaluation Instance。
- 变更应保持聚焦。不得修改或重新格式化无关文件。
- 已存在的用户变更必须保留，并在其基础上工作。

## 完成任务前的必检项

1. 阅读与任务相关的 architecture、rule-engine、schema、time-semantics、implementation-contract、testing 和 ADR 文档。
2. 根据行为添加或更新相应的 unit/compiler/runtime/temporal/integration/golden test。
3. 运行项目配置的完整测试和质量检查。如果无法运行，应准确说明原因，并运行范围最大的安全子集。
4. 检查仓库状态和完整 Diff。
5. 确认外部 Parser/GUI/Report 类型没有进入核心、未引入浮点时间、未静默折叠 Missing Data 状态。
6. 报告修改文件、已执行的验证和剩余风险；不得声称未运行的检查已通过。

## 架构变更

重大决策必须记录在 `docs/adr/` 中，并包含背景（Context）、决策（Decision）、备选方案（Alternatives）和影响（Consequences）。同一变更必须同步更新规范文档与测试。如果需求与已接受 ADR 冲突，应先指出冲突，不得静默推翻架构决策。
