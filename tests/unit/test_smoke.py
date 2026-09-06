"""Package bootstrap smoke tests."""

from importlib.metadata import requires, version

import pytest

import app_dataloganalysis


def test_package_import_and_distribution_metadata_agree() -> None:
    assert version("app-dataloganalysis") == app_dataloganalysis.__version__


def test_default_install_has_no_third_party_runtime_dependencies() -> None:
    requirements = requires("app-dataloganalysis") or []

    assert requirements
    assert all("extra ==" in requirement for requirement in requirements)


def test_bootstrap_entry_point(capsys: pytest.CaptureFixture[str]) -> None:
    app_dataloganalysis.main()

    assert capsys.readouterr().out == "汽车数据日志规则分析平台\n"
