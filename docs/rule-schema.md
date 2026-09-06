# Rule Definition Schema

保存的 Rule Definition 是持久、声明式的 Authoring Contract。YAML 与 JSON 是同一 Model 的等价序列化。开始实现时应发布 JSON Schema；本文档先固定语义结构。

## 1. 设计规则

- 顶层 `schema_version` 控制文件结构；`semantic_profile` 控制行为。
- 每个 Rule、Node、Edge 都有稳定 ID。修改 Label 不改变 Identity。
- Node 通过 `(type, version)` 解析，禁止保存 Python Import Path。
- Duration 使用带单位 String，禁止使用浮点秒。
- Signal Source 使用 Logical Reference 以及预期 Type/Unit。物理 DBC Binding 由独立 Analysis Configuration 提供，使同一规则可运行于不同车型 Variant。
- Edge 必须命名 Port；Variadic Input 的顺序通过 `slot` 明确表达。
- Default 在 IR 和 Reproducibility Manifest 中必须物化；保存的 Definition 只能省略 Schema 已定义的 Default。
- GUI 坐标、颜色和折叠状态放入非语义 `presentation`。
- MVP 在语义 Section 中拒绝未知扩展字段；厂商信息放入命名空间化 `extensions`。
- YAML Adapter 必须遵循 YAML 1.2 Core Schema、拒绝 Duplicate Mapping Key，并禁止隐式 Timestamp/Object Construction。若使用 PyYAML，必须显式调整 Resolver/Constructor；仅调用默认 `safe_load` 不足以满足契约。

## 2. 顶层结构

```yaml
schema_version: "1.0"
semantic_profile: "core-temporal/1.0"
rule_set:
  id: powertrain-safety
  version: "1.2.0"
  name: 动力系统安全规则
  metadata: {}
  parameters: []
  signal_references: []
  rules: []
  policies: {}
extensions: {}
presentation: {}
```

Rule-set Parameter 是由 Analysis Configuration 固定的 Typed Input。Rule Node 通过 `core.source.parameter` 引用但不可修改它。`signal_references` 声明 Logical Source；Binding 把 Logical Key 映射到标准化 Stream Key，并在可复用 Rule 之外记录 DBC Provenance。

### MVP 规范约束

- 一个 Analysis Session 只包含一条全局有序的输入时间线。批量分析多个日志时，每个日志创建独立 Session 和 Result；MVP 不跨日志拼接时间线。
- 每个 `rule_set.id`、`rule.id`、Node ID 和 Edge ID 在各自作用域内唯一，并匹配 `[A-Za-z][A-Za-z0-9_.-]{0,127}`。
- 每个 Rule 必须恰好有一个 Terminal Result/Assertion Node。需要多个独立结论时拆成多个 Rule；Rule Set 再负责聚合。
- 每个 Semantic Node 都必须能从 Source/Literal 到达，并且能够到达 Terminal Result。不可达或无贡献 Node 是 Validation Error，不是 Warning。
- Semantic Graph 必须是 DAG。`presentation` 不参与 Cycle、Hash 或 Reachability 检查。
- 每个 Temporal Node 必须显式写出 Satisfaction、Interval Bound、Overlap 和 Incomplete Policy；这些参数不使用隐式默认值。
- Rule 默认 Scope 是当前 Analysis Session 的完整时间线。Scope-based Assertion 至少观察到一个可用 Condition 才可能 PASS；没有可用 Observation 时为 NOT_EVALUATED 或 UNKNOWN，具体规则见 `rule-engine.md`。

Parameter 的规范形状：

```yaml
parameters:
  - id: current_limit
    value_type: float
    unit: A
    required: false
    default: 0
    constraints: {minimum: -1000, maximum: 1000}
```

Analysis Configuration 可以覆盖 Parameter Value，但不能改变 `value_type` 或 Unit Dimension。实际值及其来源必须进入 Manifest。

建议的公共 Policy：

```yaml
policies:
  ordering: reject_out_of_order
  no_trigger: not_evaluated
  aggregate: worst_conclusive_then_unknown
  unknown_assertion: unknown
  resource_limits:
    max_active_instances_per_rule: 10000
    max_evidence_items_per_evaluation: 100
```

生产环境 Default 必须通过 Benchmark 确定；以上数值仅展示结构，不是规范容量。

## 3. Example A — CellTemp > 70 °C

为了使规则极性直观，Graph 计算 Violation `CellTemp > 70 °C`，再由 `assert.never` 断言该情况不得出现。

```yaml
schema_version: "1.0"
semantic_profile: "core-temporal/1.0"
rule_set:
  id: battery-safety
  version: "1.0.0"
  name: 电池安全
  signal_references:
    - id: cell_temp
      key: vehicle.bms.CellTemp01
      value_type: float
      unit: degC
      sampling:
        kind: observe_only
  parameters: []
  policies:
    no_trigger: not_evaluated
    aggregate: worst_conclusive_then_unknown
  rules:
    - id: BMS_TEMP_001
      version: "1.0.0"
      name: 单体温度上限
      severity: critical
      nodes:
        - id: temp
          type: core.source.signal
          version: 1
          parameters: {reference: cell_temp}
        - id: limit
          type: core.value.constant
          version: 1
          parameters: {value: 70, value_type: float, unit: degC}
        - id: too_hot
          type: core.compare.gt
          version: 1
          parameters: {clock: on_left_input}
        - id: outcome
          type: core.result.assert_never
          version: 1
          parameters:
            false_status: pass
            true_status: fail
            unknown_status: unknown
            scope_semantics: observed_samples
            message: "单体温度不得超过 70 degC"
      edges:
        - id: e1
          from: {node: temp, port: value}
          to: {node: too_hot, port: left}
        - id: e2
          from: {node: limit, port: value}
          to: {node: too_hot, port: right}
        - id: e3
          from: {node: too_hot, port: result}
          to: {node: outcome, port: condition}
```

`assert_never` 产生 Scope-based Evaluation，而不是 Trigger Instance。`observed_samples` 明确表示只约束日志中实际记录且有效的温度 Sample，不声称两个 Sample 之间温度持续安全。未来 UI 可以把它显示为连接到 Violation Stream 的 Fail Block。

## 4. Example B — 充电电流响应

每个有效 `ChargeEnable` RisingEdge 都创建独立 Instance。`PackCurrent > 0` 必须严格发生在 Trigger 之后，且不得晚于 500 ms。

```yaml
schema_version: "1.0"
semantic_profile: "core-temporal/1.0"
rule_set:
  id: charging
  version: "1.0.0"
  name: 充电行为
  signal_references:
    - id: charge_enable
      key: vehicle.vcu.ChargeEnable
      value_type: bool
      sampling: {kind: observe_only}
    - id: pack_current
      key: vehicle.bms.PackCurrent
      value_type: float
      unit: A
      sampling: {kind: hold_last, max_age: 150 ms}
  parameters: []
  policies:
    no_trigger: not_evaluated
    aggregate: worst_conclusive_then_unknown
  rules:
    - id: CHARGE_001
      version: "1.0.0"
      name: 充电电流响应
      severity: error
      nodes:
        - id: enable
          type: core.source.signal
          version: 1
          parameters: {reference: charge_enable}
        - id: enable_rise
          type: core.event.rising_edge
          version: 1
          parameters:
            initialization: require_baseline
            after_unknown: require_rebaseline
        - id: enabled
          type: core.compare.eq
          version: 1
          parameters: {clock: on_left_input}
        - id: true_value
          type: core.value.constant
          version: 1
          parameters: {value: true, value_type: bool}
        - id: current
          type: core.source.signal
          version: 1
          parameters: {reference: pack_current}
        - id: zero
          type: core.value.constant
          version: 1
          parameters: {value: 0, value_type: float, unit: A}
        - id: current_positive
          type: core.compare.gt
          version: 1
          parameters: {clock: on_left_input}
        - id: response
          type: core.temporal.within
          version: 1
          parameters:
            duration: 500 ms
            satisfaction: becomes_true
            lower_bound: open
            upper_bound: closed
            overlap: independent
            incomplete_status: unknown
        - id: outcome
          type: core.result.expectation
          version: 1
          parameters:
            satisfied_status: pass
            timeout_status: fail
            indeterminate_status: unknown
            message: "PackCurrent 必须在 500 ms 内变为正值"
      edges:
        - {id: e0, from: {node: enable, port: value}, to: {node: enabled, port: left}}
        - {id: e0b, from: {node: true_value, port: value}, to: {node: enabled, port: right}}
        - {id: e1, from: {node: enabled, port: result}, to: {node: enable_rise, port: condition}}
        - {id: e2, from: {node: current, port: value}, to: {node: current_positive, port: left}}
        - {id: e3, from: {node: zero, port: value}, to: {node: current_positive, port: right}}
        - {id: e4, from: {node: enable_rise, port: event}, to: {node: response, port: trigger}}
        - {id: e5, from: {node: current_positive, port: result}, to: {node: response, port: condition}}
        - {id: e6, from: {node: response, port: evaluation}, to: {node: outcome, port: evaluation}}
```

`ValueStream<Bool>` 不能直接连接 `TruthStream` Port，因此示例先通过显式 Equality 得到 TruthStream。Compiler 将 `satisfaction: becomes_true` Lower 为第二个显式 Edge Operator。如果 Trigger 时电流已经为正也应 PASS，则应改为 `is_true` 并选择 Closed Lower Bound。

`PackCurrent` 使用有限 Freshness：只要周期 Sample 持续刷新 FALSE，系统就能证明窗口内没有变为正值并在 Deadline FAIL；如果报文中断超过 150 ms，则窗口可观测性中断，结果为 UNKNOWN，而不是把通信缺失误判为响应失败。实际 `max_age` 应根据项目通信矩阵配置，不得从 DBC 缺省猜测。

## 5. Example C — A 持续两秒后检查 B

解释：每当 `SignalA == 1` 首次连续满足两秒时，在该逻辑时间点检查 `SignalB == 1`；B 的保留值不能早于 250 ms。

```yaml
schema_version: "1.0"
semantic_profile: "core-temporal/1.0"
rule_set:
  id: sequence-example
  version: "1.0.0"
  name: 时序规则示例
  signal_references:
    - id: signal_a
      key: test.SignalA
      value_type: int
      unit: none
      sampling: {kind: hold_last, max_age: 2500 ms}
    - id: signal_b
      key: test.SignalB
      value_type: int
      unit: none
      sampling: {kind: hold_last, max_age: 250 ms}
  parameters: []
  policies:
    no_trigger: not_evaluated
    aggregate: worst_conclusive_then_unknown
  rules:
    - id: SEQ_001
      version: "1.0.0"
      name: A 稳定后检查 B
      severity: error
      nodes:
        - {id: a, type: core.source.signal, version: 1, parameters: {reference: signal_a}}
        - {id: one_a, type: core.value.constant, version: 1, parameters: {value: 1, value_type: int, unit: none}}
        - {id: a_is_one, type: core.compare.eq, version: 1, parameters: {clock: on_left_input}}
        - id: a_stable
          type: core.temporal.for_at_least
          version: 1
          parameters: {duration: 2 s, unknown: break, emit: once_per_true_interval}
        - {id: b, type: core.source.signal, version: 1, parameters: {reference: signal_b}}
        - {id: one_b, type: core.value.constant, version: 1, parameters: {value: 1, value_type: int, unit: none}}
        - {id: b_is_one, type: core.compare.eq, version: 1, parameters: {clock: on_left_input}}
        - id: check_b
          type: core.temporal.at_event
          version: 1
          parameters: {missing_status: unknown}
        - id: outcome
          type: core.result.expectation
          version: 1
          parameters:
            satisfied_status: pass
            violated_status: fail
            indeterminate_status: unknown
            message: "SignalA 连续为 1 两秒后，SignalB 必须为 1"
      edges:
        - {id: e1, from: {node: a, port: value}, to: {node: a_is_one, port: left}}
        - {id: e2, from: {node: one_a, port: value}, to: {node: a_is_one, port: right}}
        - {id: e3, from: {node: a_is_one, port: result}, to: {node: a_stable, port: condition}}
        - {id: e4, from: {node: b, port: value}, to: {node: b_is_one, port: left}}
        - {id: e5, from: {node: one_b, port: value}, to: {node: b_is_one, port: right}}
        - {id: e6, from: {node: a_stable, port: event}, to: {node: check_b, port: trigger}}
        - {id: e7, from: {node: b_is_one, port: result}, to: {node: check_b, port: condition}}
        - {id: e8, from: {node: check_b, port: evaluation}, to: {node: outcome, port: evaluation}}
```

如果“然后”表示 B 必须在两秒点之后发生变化，则应使用 `Within`、`becomes_true` 和显式 Response Window。Schema 不会从 Label 中推测这种含义。

## 6. Binding 与 Analysis Configuration

Binding 必须与 Rule 分离：

```yaml
analysis:
  inputs:
    - id: drive_001
      path: logs/drive_001.blf
      sha256: "..."
  catalogs:
    - path: dbc/vehicle.dbc
      sha256: "..."
  bindings:
    vehicle.vcu.ChargeEnable:
      channel: 1
      message: VCU_Status
      signal: ChargeEnable
    vehicle.bms.PackCurrent:
      channel: 1
      message: BMS_Status
      signal: PackCurrent
```

这样可以在不编辑 Rule Artifact 的情况下适配 Variant。Resolved Catalog 和 Binding Hash 必须进入 Run Manifest。

## 7. Versioning 与 Migration

- `schema_version` 使用 `major.minor`。Reader 接受相同 Major 和已知的 Minor Addition；未知 Major 产生 INVALID。
- `semantic_profile` 独立版本化。Migration 不得静默让规则采用新的时间行为。
- Rule-set 与 Rule 的 `version` 是作者控制的 Semantic Version，用于追踪。
- 每个 Block Instance 固定整数 Definition Version；Registry Compatibility/Migration 必须显式处理。
- Migration Function 构成确定性 Chain，作用于已经验证的旧 Model，保留 ID 并输出 Migration Report。
- Analysis Manifest 保留 Original Byte/Hash、Original Version、Migration Chain/Tool Version 与 Canonical Migrated Hash。
- Migration 不得覆盖用户 Source File，除非用户明确要求。无法解析所需 Block Version 时产生 INVALID。

Canonical Hash 使用 RFC 8785 JCS：Object Key 规范排序、Array Order 保留、UTF-8；在 JCS 前由 Typed Model 将 Duration/TimePoint 和 Int Scalar 转为带 Type 约束的十进制字符串，Unit 转为 Canonical ID，避免 int64 超出 JavaScript Safe Integer。Artifact、Definition、Rule Semantic Definition 与 Execution Semantic Hash 的投影范围以 `implementation-contract.md` 为准，并在相应 Artifact/Manifest 中记录。
