# Contributing

Contributions are welcome. This page covers the local workflow and the checks
that must pass before a pull request is merged.

## Set up

```bash
git clone https://github.com/neuromechanist/opencite.git
cd opencite
uv sync --extra dev          # install the package and dev dependencies
uv run opencite --version    # verify the CLI works
```

For PDF-related work, also install the `[pdf]` extra:

```bash
uv sync --extra dev --extra pdf
```

## Run the checks

The same checks run in CI. Run them locally before pushing:

```bash
uv run ruff check src/ tests/      # lint
uv run ruff format src/ tests/     # format
uv run pytest -m "not integration" # unit tests (no network)
```

The repository ships a pre-commit configuration:

```bash
uv run pre-commit install
uv run pre-commit run --all-files
```

## Code style

- Linting and formatting use [ruff](https://docs.astral.sh/ruff/), configured in
  `pyproject.toml` (line length 88, an `E/W/F/I/B/C4/UP/ARG/SIM/TCH` rule set).
- Public APIs use Google-style docstrings, which the
  [API Reference](../api/index.md) renders via mkdocstrings.
- Type hints are expected on public functions.

## Pull requests

1. Branch from `main`.
2. Make focused, atomic commits.
3. Ensure lint, format, and unit tests pass.
4. Open a PR against `main`; CI runs the unit tests on Python 3.11, 3.12, and
   3.13, plus an integration job on merge to `main`.

See [Testing](testing.md) for what the integration job covers and which keys it
needs.
