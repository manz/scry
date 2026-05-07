"""Per-backend implementations on top of the shared `SonarClient`."""

from __future__ import annotations

from scry.backends.base import Backend
from scry.backends.sonarcloud import SonarCloudBackend
from scry.backends.sonarqube import SonarQubeBackend
from scry.config import Profile


def for_profile(profile: Profile) -> Backend:
    """Pick the backend implementation appropriate for the profile."""
    if profile.kind == "sonarcloud":
        return SonarCloudBackend(profile)
    return SonarQubeBackend(profile)


__all__ = ["Backend", "SonarCloudBackend", "SonarQubeBackend", "for_profile"]
