"""Executable import-boundary contracts for the architecture."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from importlib.util import resolve_name
from pathlib import Path

import pytest

PACKAGE_NAME = "app_dataloganalysis"
CORE_ROOTS = frozenset({"domain", "ingestion", "results", "rules"})
OUTER_ROOTS = frozenset({"application", "cli", "gui", "infrastructure", "reporting", "ui"})
ADAPTER_AND_PRESENTATION_DEPENDENCIES = frozenset(
    {"PySide6", "can", "cantools", "jinja2", "pandas", "plotly", "polars"}
)
PYDANTIC_BOUNDARY_AREAS = frozenset({"results", "rules.definition"})
FORBIDDEN_INTERNAL_PREFIXES: dict[str, tuple[str, ...]] = {
    "results": (f"{PACKAGE_NAME}.rules.runtime",),
    "rules.definition": (
        f"{PACKAGE_NAME}.rules.compiler",
        f"{PACKAGE_NAME}.rules.ir",
        f"{PACKAGE_NAME}.rules.runtime",
    ),
    "rules.ir": (
        f"{PACKAGE_NAME}.rules.compiler",
        f"{PACKAGE_NAME}.rules.definition",
        f"{PACKAGE_NAME}.rules.runtime",
    ),
    "rules.runtime": (
        f"{PACKAGE_NAME}.rules.compiler",
        f"{PACKAGE_NAME}.rules.definition",
    ),
}


@dataclass(frozen=True, slots=True)
class ImportViolation:
    path: Path
    line: int
    imported: str


def _module_name(package_root: Path, path: Path) -> str:
    relative_parts = path.relative_to(package_root.parent).with_suffix("").parts
    if relative_parts[-1] == "__init__":
        relative_parts = relative_parts[:-1]
    return ".".join(relative_parts)


def _import_targets(node: ast.Import | ast.ImportFrom, package: str) -> tuple[str, ...]:
    if isinstance(node, ast.Import):
        return tuple(alias.name for alias in node.names)

    if node.level == 0:
        if node.module is None:
            return ()
        base = node.module
    else:
        relative_name = "." * node.level + (node.module or "")
        base = resolve_name(relative_name, package)

    imported_names = tuple(f"{base}.{alias.name}" for alias in node.names)
    return (base, *imported_names)


def _matches_prefix(imported: str, prefix: str) -> bool:
    return imported == prefix or imported.startswith(f"{prefix}.")


def _is_forbidden(imported: str, core_module: str) -> bool:
    parts = imported.split(".")
    if parts[0] in ADAPTER_AND_PRESENTATION_DEPENDENCIES:
        return True
    if len(parts) > 1 and parts[0] == PACKAGE_NAME and parts[1] in OUTER_ROOTS:
        return True

    core_parts = core_module.split(".")[1:]
    core_area = core_parts[0]
    if core_area == "rules" and len(core_parts) > 1:
        core_area = f"rules.{core_parts[1]}"
    if parts[0] == "pydantic" and core_area not in PYDANTIC_BOUNDARY_AREAS:
        return True
    return any(
        _matches_prefix(imported, prefix)
        for prefix in FORBIDDEN_INTERNAL_PREFIXES.get(core_area, ())
    )


def find_import_violations(package_root: Path) -> tuple[ImportViolation, ...]:
    """Find forbidden imports made anywhere below a core package root."""
    violations: list[ImportViolation] = []
    for root_name in sorted(CORE_ROOTS):
        core_root = package_root / root_name
        if not core_root.exists():
            continue
        for path in sorted(core_root.rglob("*.py")):
            module_name = _module_name(package_root, path)
            package = module_name if path.name == "__init__.py" else module_name.rpartition(".")[0]
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import | ast.ImportFrom):
                    for imported in _import_targets(node, package):
                        if _is_forbidden(imported, module_name):
                            violations.append(ImportViolation(path, node.lineno, imported))
                            break
    return tuple(sorted(violations, key=lambda item: (str(item.path), item.line, item.imported)))


def test_core_packages_do_not_import_outer_layers_or_adapter_libraries() -> None:
    project_root = Path(__file__).resolve().parents[2]
    violations = find_import_violations(project_root / "src" / PACKAGE_NAME)

    details = "\n".join(
        f"{violation.path}:{violation.line}: forbidden import {violation.imported}"
        for violation in violations
    )
    assert not violations, details


def test_boundary_checker_detects_absolute_relative_and_external_imports(tmp_path: Path) -> None:
    package_root = tmp_path / PACKAGE_NAME
    domain_root = package_root / "domain"
    domain_root.mkdir(parents=True)
    (domain_root / "absolute.py").write_text(
        "from app_dataloganalysis import infrastructure\nimport can\nimport pydantic\n",
        encoding="utf-8",
    )
    (domain_root / "relative.py").write_text("from .. import reporting\n", encoding="utf-8")

    imports = {violation.imported for violation in find_import_violations(package_root)}

    assert imports == {
        "app_dataloganalysis.infrastructure",
        "app_dataloganalysis.reporting",
        "can",
        "pydantic",
    }


def test_boundary_checker_keeps_definition_ir_runtime_and_results_models_separate(
    tmp_path: Path,
) -> None:
    package_root = tmp_path / PACKAGE_NAME
    examples = {
        "results/models.py": "from app_dataloganalysis.rules.runtime import operators\n",
        "rules/definition/models.py": (
            "from app_dataloganalysis.rules import ir\n"
            "from app_dataloganalysis.rules import runtime\n"
        ),
        "rules/ir/models.py": "from app_dataloganalysis.rules.definition import models\n",
        "rules/runtime/state.py": "from app_dataloganalysis.rules.compiler import compiler\n",
    }
    for relative_path, source in examples.items():
        path = package_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    imports = {violation.imported for violation in find_import_violations(package_root)}

    assert imports == {
        "app_dataloganalysis.rules.compiler",
        "app_dataloganalysis.rules.definition",
        "app_dataloganalysis.rules.ir",
        "app_dataloganalysis.rules.runtime",
    }


@pytest.mark.parametrize(
    ("source", "package", "expected"),
    [
        (
            "from app_dataloganalysis import infrastructure",
            "app_dataloganalysis.domain",
            ("app_dataloganalysis", "app_dataloganalysis.infrastructure"),
        ),
        (
            "from app_dataloganalysis.rules import runtime",
            "app_dataloganalysis.rules.definition",
            ("app_dataloganalysis.rules", "app_dataloganalysis.rules.runtime"),
        ),
        (
            "from .. import reporting",
            "app_dataloganalysis.domain",
            ("app_dataloganalysis", "app_dataloganalysis.reporting"),
        ),
        (
            "from . import compiler",
            "app_dataloganalysis.rules",
            ("app_dataloganalysis.rules", "app_dataloganalysis.rules.compiler"),
        ),
    ],
)
def test_import_targets_include_parent_module_and_imported_alias(
    source: str, package: str, expected: tuple[str, ...]
) -> None:
    node = ast.parse(source).body[0]

    assert isinstance(node, ast.ImportFrom)
    assert _import_targets(node, package) == expected
