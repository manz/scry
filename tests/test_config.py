"""Configuration roundtrip + validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from scry import config
from scry.config import Profile


def test_load_returns_empty_when_missing(xdg_config_home: Path) -> None:
    cfg = config.load()
    assert cfg.profiles == {}
    assert not config.config_path().exists()


def test_save_then_load_roundtrip(xdg_config_home: Path, profile: Profile) -> None:
    cfg = config.Config(default_profile="local", profiles={"local": profile})
    saved = config.save(cfg)
    assert saved.exists()
    assert (saved.stat().st_mode & 0o777) == 0o600

    loaded = config.load()
    assert loaded.default_profile == "local"
    assert loaded.profile("local").host_url_str == "http://sonar.test"


def test_profile_lookup_raises_with_helpful_message(profile: Profile) -> None:
    cfg = config.Config(default_profile="local", profiles={"local": profile})
    with pytest.raises(KeyError) as excinfo:
        cfg.profile("missing")
    assert "missing" in str(excinfo.value)
    assert "scry configure" in str(excinfo.value)


def test_invalid_host_url_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate(
            {
                "name": "broken",
                "host_url": "not a url",
                "token": "x",
            }
        )


def test_invalid_kind_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate(
            {
                "name": "broken",
                "host_url": "http://example.test",
                "token": "x",
                "kind": "elsewhere",
            }
        )


def test_host_url_str_strips_trailing_slash(profile: Profile) -> None:
    p = Profile.model_validate(
        {
            "name": "x",
            "host_url": "http://example.test:9000/",
            "token": "t",
        }
    )
    assert p.host_url_str == "http://example.test:9000"
