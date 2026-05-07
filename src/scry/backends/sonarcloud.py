"""SonarCloud backend — read-only.

CI runs the actual analyses; scry just fetches results. We refuse the
write paths (project create, analysis driving) so a misconfigured
profile can't accidentally hit production.
"""

from __future__ import annotations

from typing import NoReturn

from scry.backends.base import Backend


class SonarCloudBackend(Backend):
    """Hosted SonarCloud. Adds the `organization` query param to every read."""

    @property
    def organization(self) -> str:
        org = self.profile.organization
        if not org:
            raise ValueError(f"profile '{self.profile.name}' targets SonarCloud but has no organization set")
        return org

    # All read methods ride on the base implementation; we add `organization`
    # by patching the underlying httpx client's default params.
    def __init__(self, profile) -> None:  # type: ignore[no-untyped-def]
        super().__init__(profile)
        # SonarCloud accepts an `organization` query string on most endpoints;
        # send it on every request via httpx's default params.
        self.client._http.params = self.client._http.params.set("organization", self.organization)

    # Refuse anything that would mutate the cloud project.
    def create_project(self, *_: object, **__: object) -> NoReturn:
        raise PermissionError("scry refuses to create projects on SonarCloud — use the cloud UI / CI.")

    def analyse(self, *_: object, **__: object) -> NoReturn:
        raise PermissionError("SonarCloud analyses run from CI, not scry.")
