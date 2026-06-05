# Testing

OpenCite uses pytest. Tests split into two groups: fast unit tests that run
offline, and integration tests that hit real APIs.

## Unit tests

The default suite runs without network access and is what CI checks on every
push and pull request:

```bash
uv run pytest -m "not integration"
```

Run a single file or a single test by name:

```bash
uv run pytest tests/test_models.py -v
uv run pytest -k "test_doi"
```

Coverage is reported automatically (configured in `pyproject.toml`):

```bash
uv run pytest -m "not integration" --cov=opencite --cov-report=term-missing
```

## Integration tests

Integration tests make real calls to the academic APIs and are marked with the
`integration` marker. They are **skipped** unless the relevant API keys are
present in the environment:

```bash
export SEMANTIC_SCHOLAR_API_KEY=your_key
export PUBMED_API_KEY=your_key
export OPENALEX_API_KEY=your_key

uv run pytest -m integration -v
```

In CI, the integration job runs only on merge to `main` (it is
`continue-on-error`, so a transient upstream hiccup does not block the build).

!!! tip "Keep network tests deterministic"
    Integration tests that exercise multi-source search can be slow and flaky
    because the slowest upstream gates the whole call. When a test only needs to
    verify formatting or a single code path, restrict it to one fast source
    (for example `--source openalex`) rather than searching everything.

## Markers

| Marker | Meaning |
| --- | --- |
| `integration` | Hits real APIs; needs keys |
| `slow` | Takes more than ~10 seconds |

Markers are declared in `pyproject.toml` under `[tool.pytest.ini_options]` with
`--strict-markers`, so an unknown marker is an error.
