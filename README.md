# scry

[![CI](https://github.com/manz/scry/actions/workflows/ci.yml/badge.svg)](https://github.com/manz/scry/actions/workflows/ci.yml)

Peer into code health. A small CLI that drives a local **SonarQube**
instance for analyses and reads results from either SonarQube or
**SonarCloud** — issues, duplications, coverage, the lot — without
leaving the terminal.

## What it does

- `scry configure` — first-run setup; saves host + token to
  `$XDG_CONFIG_HOME/scry/config.toml`. Multiple named profiles
  (`local`, `cloud`) so you can flip between a local SonarQube and
  SonarCloud with `--profile`.
- `scry analyse [key]` — create the project on the local SonarQube if
  missing, then run `sonar-scanner` against `$PWD`. Reads `sonar.projectKey`
  from `sonar-project.properties` when no key is passed. **Local
  SonarQube only** — SonarCloud analyses run from CI.
- `scry issues [key]` — list open issues. Severity, rule code, file:line, message.
- `scry duplications [key]` — list duplication blocks across the project.
- `scry measures [key]` — coverage, complexity, lines of code, etc.
- `scry status` — host reachability + auth check.

## Install

```bash
pipx install scry
```

## Configure

```bash
scry configure                 # asks for host + token, defaults profile to "local"
scry configure --profile cloud # add a SonarCloud profile
```

Config lives at `${XDG_CONFIG_HOME:-~/.config}/scry/config.toml`,
mode 600. Format:

```toml
default_profile = "local"

[profiles.local]
host_url = "http://morken.local:9000"
token    = "squ_…"

[profiles.cloud]
host_url     = "https://sonarcloud.io"
token        = "…"
organization = "manz"
```

## Status

Alpha. API may change.
