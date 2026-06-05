# Configuration

OpenCite reads configuration from a TOML file, `.env` files, and environment
variables. You can mix all three; later sources override earlier ones.

## Quick commands

```bash
opencite config init     # create ~/.opencite/config.toml from a template
opencite config show     # print the resolved config (secrets masked)
opencite config path     # print the config file location
```

## Loading priority

Sources are merged in this order, with later entries winning:

1. `~/.opencite/config.toml`
2. `~/.opencite/.env`
3. `.env` in the current working directory
4. Environment variables

So an environment variable always overrides a value in `config.toml`, which
makes it easy to keep defaults in the file and override per shell session.

## API keys

Required for the three primary metadata sources:

```bash
export SEMANTIC_SCHOLAR_API_KEY=your_key
export PUBMED_API_KEY=your_key
export OPENALEX_API_KEY=your_key
```

!!! note "OpenAlex now requires a key"
    OpenAlex requires an API key as of February 2026. Searches that include the
    OpenAlex source fail without `OPENALEX_API_KEY`.

Optional, for PDF-to-markdown conversion via Mistral OCR:

```bash
export MISTRAL_API_KEY=your_key
```

## Publisher tokens (optional)

For authenticated PDF downloads from paywalled publishers:

```bash
export ELSEVIER_API_KEY=your_key       # Elsevier / ScienceDirect
export WILEY_TDM_TOKEN=your_token      # Wiley TDM
export SPRINGER_API_KEY=your_key       # Springer Nature
```

The same values can live in `~/.opencite/config.toml`:

```toml
[publishers]
elsevier = "your_key"
wiley_tdm = "your_token"
springer = "your_key"
```

!!! warning "Publisher TDM tokens usually prohibit redistribution"
    Tokens for Elsevier, Wiley, and Springer almost always forbid
    redistributing the bytes they return. OpenCite records a
    `publisher_tdm: true` flag in each PDF's license sidecar so downstream
    scanners can detect this. See [Redistribution & Licensing](licensing.md).

## Using config from Python

[`Config`](../api/config.md) exposes the same resolution logic:

```python
from opencite import Config

config = Config.from_env()       # TOML + .env + environment, merged
```

Pass that `config` to [`SearchOrchestrator`](../api/search.md) or
[`CitationExplorer`](../api/citations.md).
