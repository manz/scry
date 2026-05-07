"""Command-line entry point. Subcommand → backend method → render."""

from __future__ import annotations

import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

from scry import config as cfg
from scry.backends import for_profile
from scry.backends.base import Backend
from scry.render import console, render_duplications, render_issues, render_measures

DEFAULT_METRICS = [
    "ncloc",
    "coverage",
    "duplicated_lines_density",
    "complexity",
    "violations",
]

_KEY_REQUIRED_MSG = "[red]project key required (argv or sonar-project.properties)[/]"


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    handler: callable = args.func  # type: ignore[assignment]
    return int(handler(args))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scry", description="Peer into code health.")
    p.add_argument("-p", "--profile", help="Named profile from config.toml (default: configured default).")
    sub = p.add_subparsers(dest="command", required=True)

    cfg_p = sub.add_parser("configure", help="Save / update a profile.")
    cfg_p.add_argument("--profile", default="local", help="Profile name to write (default: local).")
    cfg_p.add_argument("--url", help="Host URL (skips the prompt).")
    cfg_p.add_argument("--token", help="Token (skips the prompt — beware of shell history).")
    cfg_p.add_argument("--organization", help="Organization (SonarCloud only).")
    cfg_p.add_argument("--cloud", action="store_true", help="Mark this profile as a SonarCloud target.")
    cfg_p.set_defaults(func=cmd_configure)

    st = sub.add_parser("status", help="Check host reachability + auth.")
    st.set_defaults(func=cmd_status)

    an = sub.add_parser("analyse", aliases=["analyze"], help="Run sonar-scanner against $PWD (SonarQube only).")
    an.add_argument("key", nargs="?", help="Project key (default: from sonar-project.properties).")
    an.add_argument("scanner_args", nargs=argparse.REMAINDER, help="Pass-through args for sonar-scanner.")
    an.set_defaults(func=cmd_analyse)

    iss = sub.add_parser("issues", help="List open issues for a project.")
    iss.add_argument("key", nargs="?")
    iss.set_defaults(func=cmd_issues)

    dup = sub.add_parser("duplications", aliases=["dup"], help="List duplication blocks.")
    dup.add_argument("key", nargs="?")
    dup.set_defaults(func=cmd_duplications)

    meas = sub.add_parser("measures", help="Print headline measures.")
    meas.add_argument("key", nargs="?")
    meas.add_argument(
        "-m",
        "--metrics",
        nargs="+",
        default=DEFAULT_METRICS,
        help=f"Metric keys to fetch (default: {' '.join(DEFAULT_METRICS)}).",
    )
    meas.set_defaults(func=cmd_measures)

    return p


# ---------------------------------------------------------------------------
# command handlers
# ---------------------------------------------------------------------------


def _resolve_url(args: argparse.Namespace, name: str, existing: cfg.Profile | None) -> str | None:
    return args.url or _prompt(f"Host URL for '{name}'", existing.host_url_str if existing else "")


def _resolve_token(args: argparse.Namespace, name: str, existing: cfg.Profile | None) -> str | None:
    if args.token is not None:
        return args.token
    suffix = "keep existing, blank to reuse" if existing else "required"
    answer = getpass.getpass(f"Token for '{name}' [{suffix}]: ")
    return answer or (existing.token if existing else None)


def _resolve_organization(args: argparse.Namespace, existing: cfg.Profile | None) -> str | None:
    if args.organization is not None:
        return args.organization
    if not args.cloud:
        return None
    return _prompt("Organization", existing.organization if existing else "") or None


def cmd_configure(args: argparse.Namespace) -> int:
    config = cfg.load()
    name = args.profile
    existing = config.profiles.get(name)

    host = _resolve_url(args, name, existing)
    if not host:
        console.print("[red]host URL required[/]")
        return 2
    token = _resolve_token(args, name, existing)
    if not token:
        console.print("[red]token required[/]")
        return 2

    config.profiles[name] = cfg.Profile(
        name=name,
        host_url=host,  # type: ignore[arg-type]
        token=token,
        organization=_resolve_organization(args, existing),
        kind="sonarcloud" if args.cloud else "sonarqube",
    )
    if not config.default_profile or config.default_profile not in config.profiles:
        config.default_profile = name
    path = cfg.save(config)
    console.print(f"[green]wrote {path}[/]")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    with _backend(args) as backend:
        try:
            status = backend.system_status()
        except Exception as exc:
            console.print(f"[red]unreachable: {exc}[/]")
            return 2
        console.print(f"host:   {backend.profile.host_url_str}")
        console.print(f"status: {status.get('status', '?')} (v{status.get('version', '?')})")
        ok = backend.authenticated()
        console.print(f"auth:   {'[green]ok[/]' if ok else '[red]rejected[/]'}")
        return 0 if ok else 2


def cmd_analyse(args: argparse.Namespace) -> int:
    key = _resolve_key(args.key)
    if key is None:
        console.print(_KEY_REQUIRED_MSG)
        return 2
    with _backend(args) as backend:
        if not isinstance(backend, _AnalysisCapable):
            console.print("[red]analyse only supported for SonarQube backends[/]")
            return 2
        backend.ensure_project(key)  # type: ignore[attr-defined]
        return int(backend.analyse(key, Path.cwd(), list(args.scanner_args or [])))  # type: ignore[attr-defined]


def cmd_issues(args: argparse.Namespace) -> int:
    key = _resolve_key(args.key)
    if key is None:
        console.print(_KEY_REQUIRED_MSG)
        return 2
    with _backend(args) as backend:
        render_issues(backend.issues(key))
    return 0


def cmd_duplications(args: argparse.Namespace) -> int:
    key = _resolve_key(args.key)
    if key is None:
        console.print(_KEY_REQUIRED_MSG)
        return 2
    with _backend(args) as backend:
        render_duplications(backend.duplications(key))
    return 0


def cmd_measures(args: argparse.Namespace) -> int:
    key = _resolve_key(args.key)
    if key is None:
        console.print(_KEY_REQUIRED_MSG)
        return 2
    with _backend(args) as backend:
        render_measures(backend.measures(key, args.metrics))
    return 0


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _AnalysisCapable:
    """Marker — only SonarQubeBackend exposes write paths."""


def _backend(args: argparse.Namespace) -> Backend:
    config = cfg.load()
    profile = config.profile(args.profile)
    backend = for_profile(profile)
    # Stamp marker on SonarQube only — SonarCloud would refuse.
    if profile.kind == "sonarqube":
        backend.__class__ = type(backend.__class__.__name__, (backend.__class__, _AnalysisCapable), {})  # type: ignore[assignment]
    return backend


def _resolve_key(cli_key: str | None) -> str | None:
    if cli_key:
        return cli_key
    props = Path.cwd() / "sonar-project.properties"
    if not props.is_file():
        return None
    for line in props.read_text(encoding="utf-8").splitlines():
        if line.startswith("sonar.projectKey="):
            return line.split("=", 1)[1].strip()
    return None


def _prompt(label: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{label}{suffix}: ").strip()
    return answer or default


if __name__ == "__main__":
    sys.exit(main())
