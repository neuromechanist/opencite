# API Reference

OpenCite is a library as well as a CLI. The programmatic surface centers on two
async orchestrators and a set of data models, all configured by a single
`Config` object.

## At a glance

| Symbol | Module | Use it for |
| --- | --- | --- |
| [`SearchOrchestrator`](search.md) | `opencite.search` | Parallel multi-source search with dedup/merge |
| [`CitationExplorer`](citations.md) | `opencite.citations` | Citation-graph traversal and canonical papers |
| [`Config`](config.md) | `opencite.config` | Load and merge configuration |
| [`Paper`, `IDSet`, ...](models.md) | `opencite.models` | Data models returned by the orchestrators |
| [`OpenCiteError`, ...](exceptions.md) | `opencite.exceptions` | Error hierarchy to catch |

## Typical usage

Both orchestrators are async context managers. Open one, run your queries, and
let the `async with` block close the underlying HTTP clients:

```python
import asyncio
from opencite import Config
from opencite.search import SearchOrchestrator


async def main():
    config = Config.from_env()
    async with SearchOrchestrator(config) as searcher:
        result = await searcher.search(
            "transformer attention",
            max_results=10,
            sources=("openalex", "s2"),
            sort="citations",
        )
        print(f"{len(result.papers)} papers, by source: {result.total_by_source}")
        for paper in result.papers:
            print(paper.year, paper.title)


asyncio.run(main())
```

## Top-level exports

The package re-exports the data models and `Config` for convenience:

::: opencite
    options:
      members:
        - Config
        - Paper
        - Author
        - IDSet
        - Source
        - PDFLocation
        - SearchResult
        - CitationResult
      show_root_heading: false
      show_source: false
