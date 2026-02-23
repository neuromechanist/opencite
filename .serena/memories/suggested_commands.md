# Suggested Commands

## Install & Setup
```bash
uv sync --extra dev
```

## Run CLI
```bash
uv run opencite --version
uv run opencite search "query"
uv run opencite lookup DOI
uv run opencite cite DOI
uv run opencite canonical "topic"
uv run opencite pdf DOI -o paper.pdf --convert
uv run opencite batch-fetch dois.txt --convert -o ./papers
uv run opencite config init
```

## Testing
```bash
uv run pytest
uv run pytest tests/test_models.py -v
uv run pytest -k "test_doi"
uv run pytest -m integration
uv run pytest --cov=opencite
```

## Linting & Formatting
```bash
uv run ruff check src/ tests/
uv run ruff check --fix src/ tests/
uv run ruff format src/ tests/
```
