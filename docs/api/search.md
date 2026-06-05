# Search

`SearchOrchestrator` runs a keyword search across every configured source in
parallel, then deduplicates and merges the results into a single
[`SearchResult`](models.md). It is an async context manager.

```python
from opencite import Config
from opencite.search import SearchOrchestrator

async with SearchOrchestrator(Config.from_env()) as searcher:
    result = await searcher.search("graph neural networks", max_results=20)
```

::: opencite.search.SearchOrchestrator
