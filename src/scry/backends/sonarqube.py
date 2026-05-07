"""Self-hosted SonarQube backend. Adds project-create + analysis driving."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from scry.backends.base import Backend
from scry.client import SonarApiError


class SonarQubeBackend(Backend):
    """Local SonarQube — full read/write surface, including analysis."""

    # ----- project lifecycle -------------------------------------------------

    def project_exists(self, project_key: str) -> bool:
        payload = self.client.get("/api/projects/search", projects=project_key)
        components = payload.get("components", []) or []
        return any(c.get("key") == project_key for c in components)

    def create_project(self, project_key: str, name: str | None = None) -> None:
        self.client.post(
            "/api/projects/create",
            project=project_key,
            name=name or project_key,
        )

    def ensure_project(self, project_key: str, name: str | None = None) -> None:
        if self.project_exists(project_key):
            return
        try:
            self.create_project(project_key, name)
        except SonarApiError as exc:
            raise SonarApiError(
                exc.status,
                f"couldn't create '{project_key}': {exc}. Token likely lacks the 'Create Projects' global permission.",
            ) from exc

    # ----- analysis ----------------------------------------------------------

    def analyse(self, project_key: str, working_dir: Path, extra_args: list[str] | None = None) -> int:
        """Shell out to `sonar-scanner` against the working directory.

        Caller is responsible for ensuring the project exists and that
        `coverage.xml` (or whatever else the scanner reads) is in
        place. Returns the scanner's exit code.
        """
        scanner = shutil.which("sonar-scanner")
        if scanner is None:
            raise FileNotFoundError("sonar-scanner not on PATH (install Sonar Scanner CLI).")
        cmd = [
            scanner,
            f"-Dsonar.host.url={self.profile.host_url}",
            f"-Dsonar.token={self.profile.token}",
            f"-Dsonar.projectKey={project_key}",
            *(extra_args or []),
        ]
        return subprocess.run(cmd, cwd=working_dir, check=False).returncode
