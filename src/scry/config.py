"""Persistent configuration: profiles → host URL + token (+ org for SonarCloud).

Stored at `$XDG_CONFIG_HOME/scry/config.toml` (or `~/.config/scry/config.toml`).
The file is mode 600 so the token isn't world-readable.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "scry" / "config.toml"


class Profile(BaseModel):
    """One backend profile.

    `organization` is required for SonarCloud, ignored elsewhere.
    `kind` selects the backend implementation: `sonarqube` for
    self-hosted instances, `sonarcloud` for the hosted service.
    """

    name: str
    host_url: HttpUrl
    token: str
    organization: str | None = None
    kind: Literal["sonarqube", "sonarcloud"] = "sonarqube"

    @property
    def host_url_str(self) -> str:
        # rstripping httpx-style trailing slash; pydantic appends one.
        return str(self.host_url).rstrip("/")


class Config(BaseModel):
    default_profile: str = "local"
    profiles: dict[str, Profile] = Field(default_factory=dict)

    def profile(self, name: str | None = None) -> Profile:
        target = name or self.default_profile
        try:
            return self.profiles[target]
        except KeyError as exc:
            available = ", ".join(sorted(self.profiles)) or "<none>"
            raise KeyError(
                f"profile '{target}' not configured (have: {available}). Run `scry configure --profile {target}`."
            ) from exc


def load() -> Config:
    """Read config from disk; return an empty `Config` when absent."""
    path = config_path()
    if not path.is_file():
        return Config(profiles={})
    with path.open("rb") as fh:
        raw: dict[str, Any] = tomllib.load(fh)
    profiles_raw: dict[str, Any] = raw.get("profiles", {}) or {}
    profiles = {name: Profile.model_validate({"name": name, **data}) for name, data in profiles_raw.items()}
    return Config(default_profile=raw.get("default_profile", "local"), profiles=profiles)


def save(config: Config) -> Path:
    """Write config to disk (mode 600). Returns the file path."""
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f'default_profile = "{config.default_profile}"', ""]
    for name, profile in sorted(config.profiles.items()):
        lines.append(f"[profiles.{name}]")
        lines.append(f'host_url = "{profile.host_url_str}"')
        lines.append(f'token    = "{profile.token}"')
        lines.append(f'kind     = "{profile.kind}"')
        if profile.organization:
            lines.append(f'organization = "{profile.organization}"')
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    path.chmod(0o600)
    return path
