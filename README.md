# 汽车数据日志规则分析平台

本项目面向汽车 CAN 等时序数据，目标是提供一套确定、可解释、可扩展的规则分析核心。

项目当前处于架构与基础设施阶段。核心设计文档位于 [`docs/`](docs/architecture.md)，其中：

- [`architecture.md`](docs/architecture.md)：总体架构、领域边界与性能策略；
- [`rule-engine.md`](docs/rule-engine.md)：规则编译、IR 与运行时模型；
- [`time-semantics.md`](docs/time-semantics.md)：规范性的时间语义；
- [`rule-schema.md`](docs/rule-schema.md)：持久化规则格式；
- [`testing-strategy.md`](docs/testing-strategy.md)：测试与质量策略；
- [`development-plan.md`](docs/development-plan.md)：MVP 开发任务；
- [`implementation-contract.md`](docs/implementation-contract.md)：可直接编码的 MVP 接口与行为契约；
- [`architecture-review.md`](docs/architecture-review.md)：实现前矛盾审计、修正和剩余决策；
- [`docs/adr/`](docs/adr/README.md)：已接受的关键架构决策。

当前阶段不包含完整 BLF/ASC 解析器、规则引擎或 GUI 实现。

## 开发环境

项目支持 Python 3.12 和 3.13，并使用 `uv` 管理可复现的开发环境：

```powershell
uv sync --locked
uv run app-dataloganalysis
```

默认安装没有第三方运行时依赖。CAN/DBC 与报告适配器依赖分别通过 `can`、`report`
可选 extra 安装：

```powershell
uv sync --locked --extra can
uv sync --locked --extra report
```

提交变更前运行统一质量入口：

```powershell
./scripts/quality.ps1
```

完整开发约定见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。
