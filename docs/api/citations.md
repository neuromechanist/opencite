# Citations

`CitationExplorer` traverses the citation graph around a paper: the papers that
cite it, the papers it references, and the canonical (most-cited) papers in a
field. It is an async context manager and returns
[`CitationResult`](models.md) objects.

```python
from opencite import Config
from opencite.citations import CitationExplorer

async with CitationExplorer(Config.from_env()) as explorer:
    citing = await explorer.citing_papers("10.1038/nature12345", max_results=20)
    refs = await explorer.references("10.1038/nature12345")
    landmarks = await explorer.canonical_papers("deep learning", min_citations=5000)
```

::: opencite.citations.CitationExplorer
