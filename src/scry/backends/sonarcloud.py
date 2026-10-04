"""SonarCloud backend — read-only.

CI runs the actual analyses; scry just fetches results. We refuse the
write paths (project create, analysis driving) so a misconfigured
profile can't accidentally hit production.
"""

from __future__ import annotations

from typing import NoReturn

from scry.backends.base import Backend, ProjectParams
from scry.client import ScryError
from scry.config import Profile


class SonarCloudBackend(Backend):
    """Hosted SonarCloud. Scopes project reads to the project's organization."""

    def __init__(self, profile: Profile) -> None:
        super().__init__(profile)
        self._project_orgs: dict[str, str] = {}

    @property
    def organization(self) -> str:
        org = self.profile.organization
        if not org:
            raise ScryError(f"profile '{self.profile.name}' targets SonarCloud but has no organization set")
        return org

    def project_params(self, project_key: str) -> ProjectParams:
        """Scope reads to the organization that owns ``project_key``.

        SonarCloud answers a query for a project outside the requested
        organization with an empty 200, not an error, so trusting the
        profile's organization silently reports "no issues" for any project
        living in another org the token can read.
        """
        if project_key not in self._project_orgs:
            self._project_orgs[project_key] = self._lookup_organization(project_key)
        return {"organization": self._project_orgs[project_key]}

    def _lookup_organization(self, project_key: str) -> str:
        payload = self.client.get("/api/components/show", component=project_key, organization=self.organization)
        owner = payload.get("component", {}).get("organization")
        if not owner:
            raise ScryError(f"couldn't determine the SonarCloud organization of project '{project_key}'")
        return str(owner)

    # Refuse anything that would mutate the cloud project.
    def create_project(self, *_: object, **__: object) -> NoReturn:
        raise PermissionError("scry refuses to create projects on SonarCloud — use the cloud UI / CI.")

    def analyse(self, *_: object, **__: object) -> NoReturn:
        raise PermissionError("SonarCloud analyses run from CI, not scry.")
