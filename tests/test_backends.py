"""Backend behaviours via mocked Sonar Web API."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from scry.backends import SonarCloudBackend, SonarQubeBackend
from scry.client import SonarApiError
from scry.config import Profile

# ---------------------------------------------------------------------------
# SonarQube — read paths
# ---------------------------------------------------------------------------


@respx.mock
def test_issues_decodes_minimum_fields(profile: Profile) -> None:
    respx.get("http://sonar.test/api/issues/search").mock(
        return_value=Response(
            200,
            json={
                "issues": [
                    {
                        "severity": "CRITICAL",
                        "rule": "python:S3776",
                        "component": "manz_demo:src/demo/parser.py",
                        "line": 328,
                        "message": "Refactor this function to reduce its Cognitive Complexity\nwith more detail.",
                    },
                ],
                "paging": {"total": 1, "pageIndex": 1, "pageSize": 200},
            },
        )
    )
    with SonarQubeBackend(profile) as backend:
        issues = list(backend.issues("manz_demo"))
    assert len(issues) == 1
    issue = issues[0]
    assert issue.severity == "CRITICAL"
    assert issue.component == "src/demo/parser.py"
    assert issue.line == 328
    # Multi-line messages are folded to the first line.
    assert "\n" not in issue.message


@respx.mock
def test_duplications_emit_blocks_per_file(profile: Profile) -> None:
    respx.get("http://sonar.test/api/measures/component_tree").mock(
        return_value=Response(
            200,
            json={
                "components": [
                    {
                        "key": "manz_demo:src/demo/nodes.py",
                        "measures": [{"metric": "duplicated_lines", "value": "12"}],
                    },
                    {
                        "key": "manz_demo:src/demo/clean.py",
                        "measures": [{"metric": "duplicated_lines", "value": "0"}],
                    },
                ],
                "paging": {"total": 2, "pageIndex": 1, "pageSize": 200},
            },
        )
    )
    respx.get("http://sonar.test/api/duplications/show").mock(
        return_value=Response(
            200,
            json={
                "duplications": [
                    {
                        "blocks": [
                            {"_ref": "1", "from": 449, "size": 12},
                            {"_ref": "1", "from": 470, "size": 12},
                        ]
                    }
                ],
                "files": {"1": {"key": "manz_demo:src/demo/nodes.py"}},
            },
        )
    )
    with SonarQubeBackend(profile) as backend:
        groups = list(backend.duplications("manz_demo"))
    assert len(groups) == 1
    block_a, block_b = groups[0]
    assert block_a.component.endswith("nodes.py")
    assert (block_a.start_line, block_b.start_line) == (449, 470)
    assert block_a.size == 12


@respx.mock
def test_measures_returns_metrics(profile: Profile) -> None:
    respx.get("http://sonar.test/api/measures/component").mock(
        return_value=Response(
            200,
            json={
                "component": {
                    "measures": [
                        {"metric": "ncloc", "value": "5000"},
                        {"metric": "coverage"},
                    ]
                }
            },
        )
    )
    with SonarQubeBackend(profile) as backend:
        result = backend.measures("manz_demo", ["ncloc", "coverage"])
    assert {m.metric: m.value for m in result} == {"ncloc": "5000", "coverage": None}


# ---------------------------------------------------------------------------
# SonarQube — write paths
# ---------------------------------------------------------------------------


@respx.mock
def test_ensure_project_skips_when_present(profile: Profile) -> None:
    search = respx.get("http://sonar.test/api/projects/search").mock(
        return_value=Response(
            200,
            json={"components": [{"key": "manz_demo"}], "paging": {"total": 1}},
        )
    )
    create = respx.post("http://sonar.test/api/projects/create").mock(return_value=Response(200, json={}))
    with SonarQubeBackend(profile) as backend:
        backend.ensure_project("manz_demo")
    assert search.called
    assert not create.called


@respx.mock
def test_ensure_project_creates_when_missing(profile: Profile) -> None:
    respx.get("http://sonar.test/api/projects/search").mock(
        return_value=Response(200, json={"components": [], "paging": {"total": 0}})
    )
    create = respx.post("http://sonar.test/api/projects/create").mock(return_value=Response(200, json={}))
    with SonarQubeBackend(profile) as backend:
        backend.ensure_project("manz_demo")
    assert create.called


@respx.mock
def test_ensure_project_wraps_permission_error(profile: Profile) -> None:
    respx.get("http://sonar.test/api/projects/search").mock(
        return_value=Response(200, json={"components": [], "paging": {"total": 0}})
    )
    respx.post("http://sonar.test/api/projects/create").mock(
        return_value=Response(403, json={"errors": [{"msg": "Insufficient privileges"}]})
    )
    with SonarQubeBackend(profile) as backend, pytest.raises(SonarApiError) as excinfo:
        backend.ensure_project("manz_demo")
    assert "Create Projects" in str(excinfo.value)


# ---------------------------------------------------------------------------
# SonarCloud — read with org, write paths refused
# ---------------------------------------------------------------------------


@respx.mock
def test_sonarcloud_attaches_organization_on_read(cloud_profile: Profile) -> None:
    route = respx.get("https://sonarcloud.io/api/issues/search").mock(
        return_value=Response(200, json={"issues": [], "paging": {"total": 0}})
    )
    with SonarCloudBackend(cloud_profile) as backend:
        list(backend.issues("manz_demo"))
    assert route.called
    request = route.calls.last.request
    assert request.url.params.get("organization") == "manz"
    assert request.url.params.get("componentKeys") == "manz_demo"


def test_sonarcloud_refuses_create(cloud_profile: Profile) -> None:
    backend = SonarCloudBackend(cloud_profile)
    try:
        with pytest.raises(PermissionError):
            backend.create_project("foo")
    finally:
        backend.client.close()


def test_sonarcloud_refuses_analyse(cloud_profile: Profile) -> None:
    backend = SonarCloudBackend(cloud_profile)
    try:
        with pytest.raises(PermissionError):
            backend.analyse("foo", working_dir=None)  # type: ignore[arg-type]
    finally:
        backend.client.close()
