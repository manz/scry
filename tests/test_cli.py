"""End-to-end CLI behaviour with respx-mocked backend calls."""

from __future__ import annotations

from pathlib import Path

import pytest
import respx
from httpx import Response

from scry import cli, config


@pytest.fixture
def configured(xdg_config_home: Path) -> Path:
    """Write a `local` SonarQube profile so commands can reach a backend."""
    cfg = config.Config(
        default_profile="local",
        profiles={
            "local": config.Profile.model_validate(
                {
                    "name": "local",
                    "host_url": "http://sonar.test",
                    "token": "squ_test",
                    "kind": "sonarqube",
                }
            ),
        },
    )
    return config.save(cfg)


# ---------------------------------------------------------------------------
# argv parsing
# ---------------------------------------------------------------------------


def test_help_exits_clean(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    out = capsys.readouterr().out
    assert "configure" in out
    assert "issues" in out


def test_resolve_key_reads_properties(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    (project / "sonar-project.properties").write_text(
        "sonar.projectKey=demo_app\nsonar.sources=src\n", encoding="utf-8"
    )
    monkeypatch.chdir(project)
    assert cli._resolve_key(None) == "demo_app"
    assert cli._resolve_key("override") == "override"


def test_resolve_key_returns_none_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert cli._resolve_key(None) is None


# ---------------------------------------------------------------------------
# configure (non-interactive)
# ---------------------------------------------------------------------------


def test_configure_writes_profile_with_flags(xdg_config_home: Path) -> None:
    rc = cli.main(
        [
            "configure",
            "--profile",
            "local",
            "--url",
            "http://morken.local:9000",
            "--token",
            "squ_abc",
        ]
    )
    assert rc == 0
    cfg = config.load()
    profile = cfg.profile("local")
    assert profile.host_url_str == "http://morken.local:9000"
    assert profile.token == "squ_abc"
    assert profile.kind == "sonarqube"


def test_configure_cloud_requires_organization(xdg_config_home: Path) -> None:
    rc = cli.main(
        [
            "configure",
            "--profile",
            "cloud",
            "--cloud",
            "--url",
            "https://sonarcloud.io",
            "--token",
            "cloud_tok",
            "--organization",
            "manz",
        ]
    )
    assert rc == 0
    cfg = config.load()
    assert cfg.profile("cloud").kind == "sonarcloud"
    assert cfg.profile("cloud").organization == "manz"


# ---------------------------------------------------------------------------
# status / issues / duplications / measures (mocked HTTP)
# ---------------------------------------------------------------------------


@respx.mock
def test_status_reports_up(configured: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get("http://sonar.test/api/system/status").mock(
        return_value=Response(200, json={"status": "UP", "version": "26.4.0.0"})
    )
    respx.get("http://sonar.test/api/authentication/validate").mock(return_value=Response(200, json={"valid": True}))
    rc = cli.main(["status"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "UP" in out
    assert "ok" in out


@respx.mock
def test_status_failed_auth_returns_two(configured: Path) -> None:
    respx.get("http://sonar.test/api/system/status").mock(
        return_value=Response(200, json={"status": "UP", "version": "x"})
    )
    respx.get("http://sonar.test/api/authentication/validate").mock(return_value=Response(200, json={"valid": False}))
    assert cli.main(["status"]) == 2


@respx.mock
def test_issues_renders_severities(configured: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get("http://sonar.test/api/issues/search").mock(
        return_value=Response(
            200,
            json={
                "issues": [
                    {
                        "severity": "MAJOR",
                        "rule": "python:S1172",
                        "component": "manz_demo:src/demo/foo.py",
                        "line": 10,
                        "message": 'Remove the unused parameter "ctx".',
                    },
                ],
                "paging": {"total": 1, "pageIndex": 1, "pageSize": 200},
            },
        )
    )
    rc = cli.main(["issues", "manz_demo"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "MAJOR" in out
    assert "S1172" in out


@respx.mock
def test_duplications_quiet_when_none(configured: Path, capsys: pytest.CaptureFixture[str]) -> None:
    respx.get("http://sonar.test/api/measures/component_tree").mock(
        return_value=Response(200, json={"components": [], "paging": {"total": 0}})
    )
    rc = cli.main(["dup", "manz_demo"])
    assert rc == 0
    assert "no duplications" in capsys.readouterr().out


@respx.mock
def test_measures_default_metrics(configured: Path, capsys: pytest.CaptureFixture[str]) -> None:
    route = respx.get("http://sonar.test/api/measures/component").mock(
        return_value=Response(
            200,
            json={
                "component": {
                    "measures": [
                        {"metric": "ncloc", "value": "5000"},
                        {"metric": "coverage", "value": "84"},
                    ]
                }
            },
        )
    )
    rc = cli.main(["measures", "manz_demo"])
    assert rc == 0
    request = route.calls.last.request
    metrics_param = request.url.params["metricKeys"]
    assert "ncloc" in metrics_param
    assert "coverage" in metrics_param
    out = capsys.readouterr().out
    assert "5000" in out
    assert "84" in out


def test_missing_key_returns_two(configured: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)  # no sonar-project.properties here
    assert cli.main(["issues"]) == 2
