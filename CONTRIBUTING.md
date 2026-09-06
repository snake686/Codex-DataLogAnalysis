# 贡献指南

## 环境准备

项目兼容 Python 3.12 和 3.13，推荐安装 [`uv`](https://docs.astral.sh/uv/)。
`.python-version` 选择推荐的本地解释器版本；CI 会同时验证两个受支持版本。

首次检出后创建包含测试与静态检查工具的可编辑环境：

```powershell
uv sync --locked
```

默认安装必须保持最小。仅在开发对应适配器时安装可选依赖：

```powershell
uv sync --locked --extra can
uv sync --locked --extra report
```

## 统一质量入口

提交前运行：

```powershell
./scripts/quality.ps1
```

在 POSIX Shell 中运行：

```sh
sh scripts/quality.sh
```

该命令依次执行 Ruff lint、Ruff format check、严格 MyPy 检查和完整 Pytest 测试。
包装脚本把 uv Cache 和 Managed Python 放在已忽略的仓库目录内，避免依赖用户级缓存状态；
首次失败后命令会立即退出，返回对应工具的非零状态码。CI 使用相同 Python 入口。

需要单独排查时可运行：

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests scripts
uv run --locked pytest
```

## 包边界

依赖方向必须遵循 `docs/architecture.md`。核心目录 `domain`、`rules`、`ingestion` 和
`results` 不得导入 `application`、`infrastructure`、`reporting`、CLI 或 UI/GUI 包；也不得
直接导入 CAN、DataFrame、报告或 GUI 库。Rule Definition 可以在持久化边界使用
Pydantic，但 Domain、Compiler IR 和 Runtime 不得依赖它。

`tests/architecture/test_import_boundaries.py` 会以 AST 检查这些约束，不需要导入被扫描
模块，因此缺失的可选适配器依赖不会削弱检查。新增顶层包或改变依赖方向时，应先同步
架构文档；重大变更还需要 ADR。

## 测试约定

测试按职责放在 `tests/unit`、`tests/architecture`，后续任务再建立 compiler、runtime、
temporal、integration 和 golden 套件。时间语义测试只能推进逻辑时间与 Watermark，禁止
调用 `sleep()` 或读取机器时钟。每项行为变更都必须包含测试，并保留稳定诊断码、UNKNOWN
和结构化原因。
