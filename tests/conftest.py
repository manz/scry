"""Shared fixtures.

`xdg_config_home` redirects `~/.config` lookups to a tmp dir so tests
can roundtrip configuration without touching the real home directory.
`profile` and `cloud_profile` give canned `Profile` instances; `client`
hands back a `SonarClient` already wired to the local profile so tests
can mount respx routes against the configured base URL.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scry.client import SonarClient
from scry.config import Profile


@pytest.fixture
def xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def profile() -> Profile:
    return Profile.model_validate(
        {
            "name": "local",
            "host_url": "http://sonar.test",
            "token": "squ_test_token",
            "kind": "sonarqube",
        }
    )


@pytest.fixture
def cloud_profile() -> Profile:
    return Profile.model_validate(
        {
            "name": "cloud",
            "host_url": "https://sonarcloud.io",
            "token": "cloud_test_token",
            "organization": "manz",
            "kind": "sonarcloud",
        }
    )


@pytest.fixture
def client(profile: Profile):
    """Yield a `SonarClient`, closed after the test."""
    c = SonarClient(profile)
    try:
        yield c
    finally:
        c.close()
