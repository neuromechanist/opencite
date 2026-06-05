# OpenCite

**Academic literature search, citation management, and PDF retrieval, from one command line.**

OpenCite searches Semantic Scholar, OpenAlex, PubMed, arXiv, bioRxiv, medRxiv,
OSF Preprints (PsyArXiv / SocArXiv / ...), Zenodo, Figshare, CrossRef, and CORE
**in parallel**, deduplicates the results, and gives you back clean,
citation-ready output. It also traverses citation graphs, retrieves PDFs (with
HTML full-text shortcuts for arXiv ar5iv and bioRxiv `.full`), downloads in
batch, and converts PDFs to markdown.

```bash
uv pip install opencite
export OPENALEX_API_KEY=your_key
opencite search "transformer attention mechanism"
```

## Why OpenCite

<div class="grid cards" markdown>

-   :material-magnify-scan: __One query, every source__

    A single search fans out to a dozen academic APIs concurrently, then merges
    and deduplicates by DOI and fuzzy title match, so you do not chase the same
    paper across ten tabs.

-   :material-graph-outline: __Citation graphs__

    Walk forward (papers that cite this) or backward (its references), or find
    the canonical, most-cited papers in a field.

-   :material-file-document-arrow-right-outline: __PDFs to markdown__

    Retrieve open-access PDFs and convert them to markdown, with PMC structured
    full-text shortcuts and batch downloads at controlled concurrency.

-   :material-format-list-bulleted-type: __Output that fits your workflow__

    Text, JSON, BibTeX, or CSV. Pipe JSON into the next tool, or append BibTeX
    straight into your reference manager.

</div>

## Two ways to use it

=== "Command line"

    ```bash
    opencite search "tDCS motor cortex" --max 20 -f bibtex -o refs.bib
    opencite lookup 10.1038/nature12345 --enrich
    opencite cite 10.1038/nature12345 --direction citing
    ```

    See the [CLI Reference](cli/index.md) for every command and flag.

=== "Python library"

    ```python
    import asyncio
    from opencite import Config
    from opencite.search import SearchOrchestrator


    async def main():
        async with SearchOrchestrator(Config.from_env()) as searcher:
            result = await searcher.search("transformer attention", max_results=10)
            for paper in result.papers:
                print(paper.year, paper.title)


    asyncio.run(main())
    ```

    See the [API Reference](api/index.md) for the full programmatic surface.

## Sources

| Source | Coverage | Key required |
| --- | --- | --- |
| OpenAlex | 250M+ works; PDF URLs, filters, citation counts | Yes |
| Semantic Scholar | TLDR summaries, embeddings, BibTeX styles | Yes |
| PubMed / PMC | MeSH terms, structured OA full-text | Yes |
| arXiv | Preprints, direct PDF | No |
| bioRxiv / medRxiv | Life-science preprints | No |
| OSF Preprints | PsyArXiv, SocArXiv, EarthArXiv, MetaArXiv | No |
| Zenodo | Publication preprints | No (token optional) |
| Figshare | Preprints | No |
| CrossRef | DOI metadata, preprint search | No |
| CORE | Aggregated open access | No |

## Next steps

- New here? Start with [Getting Started](getting-started.md).
- Want recipes? Browse the [Guides](guides/index.md).
- Building on top of it? Read the [API Reference](api/index.md).

!!! tip "AI-agent skill"
    OpenCite ships as an agent skill in
    [neuromechanist/research-skills](https://github.com/neuromechanist/research-skills),
    usable from Claude Code, Codex / OpenAI, and VS Code GitHub Copilot.
