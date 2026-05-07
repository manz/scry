VERSION ?= 0.0.0.dev0
V = 0
Q = $(if $(filter 1,$V),,@)

M = $(shell if [ "$$(tput colors 2> /dev/null || echo 0)" -ge 8 ]; then printf "\033[34;1m▶\033[0m"; else printf "▶"; fi)

# Use the project's editable venv if present, else fall back to the
# user's interpreter. Keeps `make` usable inside CI containers without
# a pre-baked .venv.
PY ?= $(shell test -x .venv/bin/python && echo .venv/bin/python || command -v python3)

export VERSION

.SUFFIXES:

.PHONY: help
help: ## Show this help
	$(Q) awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.PHONY: all
all: | check tests wheel ## Lint + type + test + build wheel

.PHONY: env
env: ## Create / refresh the dev virtualenv at .venv
	$(info $(M) creating .venv ...)
	$(Q) python3 -m venv .venv
	$(Q) .venv/bin/pip install --upgrade pip
	$(Q) .venv/bin/pip install -e ".[dev]"

.PHONY: format
format: ## Auto-format with ruff
	$(info $(M) formatting ...)
	$(Q) $(PY) -m ruff check --fix src tests
	$(Q) $(PY) -m ruff format src tests

.PHONY: check
check: ## Lint + format check + type check
	$(info $(M) ruff check ...)
	$(Q) $(PY) -m ruff check src tests
	$(info $(M) ruff format check ...)
	$(Q) $(PY) -m ruff format --check src tests
	$(info $(M) mypy ...)
	$(Q) $(PY) -m mypy src

.PHONY: tests
tests: ## Run pytest with coverage (writes coverage.xml)
	$(info $(M) running tests ...)
	$(Q) $(PY) -m pytest --cov=scry --cov-report=xml --cov-report=term

.PHONY: wheel
wheel: ## Build wheel + sdist into dist/
	$(info $(M) building wheel ...)
	$(Q) rm -Rf dist
	$(Q) $(PY) -m pip install --quiet build
	$(Q) $(PY) -m build

.PHONY: sonar
sonar: tests ## Push a local SonarQube analysis for the configured profile
	$(info $(M) sonar analysis ...)
	$(Q) $(PY) -m scry analyse

.PHONY: clean
clean: ## Remove build / cache artefacts
	$(info $(M) cleaning ...)
	$(Q) rm -Rf dist build *.egg-info src/*.egg-info
	$(Q) rm -Rf coverage.xml .coverage htmlcov
	$(Q) rm -Rf .mypy_cache .pytest_cache .ruff_cache .scannerwork

.PHONY: distclean
distclean: clean ## clean + drop the virtualenv
	$(Q) rm -Rf .venv
