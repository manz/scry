"""Abstract backend — a thin protocol over the SonarQube / SonarCloud Web APIs.

Concrete subclasses tailor request shapes (org scoping, permissions)
without leaking those differences into the CLI layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel, Field

from scry.client import SonarApiError, SonarClient
from scry.config import Profile


class Issue(BaseModel):
    severity: str = "?"
    rule: str = "?"
    component: str = "?"
    line: int | None = None
    message: str = ""

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Issue:
        message = (raw.get("message") or "").splitlines()
        return cls(
            severity=str(raw.get("severity", "?")),
            rule=str(raw.get("rule", "?")),
            component=str(raw.get("component", "?")).split(":", 1)[-1],
            line=raw.get("line"),
            message=message[0] if message else "",
        )


class DuplicationBlock(BaseModel):
    """One side of a duplication. A duplication is a list of these blocks."""

    component: str
    start_line: int = Field(alias="from")
    size: int

    model_config = {"populate_by_name": True}


class Measure(BaseModel):
    metric: str
    value: str | None = None


class Backend:
    """Base class — concrete backends override what they need."""

    def __init__(self, profile: Profile) -> None:
        self.profile = profile
        self.client = SonarClient(profile)

    # context manager so callers can `with for_profile(p) as backend:`
    def __enter__(self) -> Backend:
        return self

    def __exit__(self, *_: object) -> None:
        self.client.close()

    # --------------------------------------------------------------
    # status / auth
    # --------------------------------------------------------------

    def system_status(self) -> dict[str, Any]:
        return dict(self.client.get("/api/system/status"))

    def authenticated(self) -> bool:
        try:
            payload = self.client.get("/api/authentication/validate")
        except SonarApiError:
            return False
        return bool(payload.get("valid"))

    # --------------------------------------------------------------
    # project-aware reads (overridden in SonarCloud to add org)
    # --------------------------------------------------------------

    def issues(self, project_key: str) -> Iterable[Issue]:
        for raw in self.client.paginate(
            "/api/issues/search",
            items_key="issues",
            componentKeys=project_key,
            resolved="false",
        ):
            yield Issue.from_api(raw)

    def duplications(self, project_key: str) -> Iterable[list[DuplicationBlock]]:
        files = self.client.paginate(
            "/api/measures/component_tree",
            items_key="components",
            component=project_key,
            metricKeys="duplicated_lines",
            qualifiers="FIL",
        )
        for component in files:
            if not _has_duplications(component):
                continue
            payload = self.client.get("/api/duplications/show", key=component["key"])
            file_index = payload.get("files", {}) or {}
            for dup in payload.get("duplications", []) or []:
                yield [
                    DuplicationBlock(
                        component=str(file_index.get(str(b.get("_ref")), {}).get("key", "?")).split(":", 1)[-1],
                        **{"from": int(b.get("from", 0))},
                        size=int(b.get("size", 0)),
                    )
                    for b in dup.get("blocks", []) or []
                ]

    def measures(self, project_key: str, metrics: list[str]) -> list[Measure]:
        payload = self.client.get(
            "/api/measures/component",
            component=project_key,
            metricKeys=",".join(metrics),
        )
        return [Measure.model_validate(m) for m in payload.get("component", {}).get("measures", []) or []]


def _has_duplications(component: dict[str, Any]) -> bool:
    return any(int(m.get("value", "0") or "0") > 0 for m in component.get("measures", []) or [])
