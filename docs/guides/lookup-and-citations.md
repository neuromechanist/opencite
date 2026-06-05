# Lookup & Citations

Beyond keyword search, OpenCite resolves specific papers by identifier and walks
the citation graph around them.

## Look up by identifier

```bash
opencite lookup 10.1038/nature12345
```

OpenCite auto-detects the identifier type. Accepted forms:

- a DOI (e.g. `10.1038/nature12345`)
- `pmid:NNNN` (PubMed ID)
- `pmc:NNNN` (PubMed Central ID)
- `arxiv:NNNN.NNNNN` (arXiv ID)
- a Semantic Scholar paper ID
- an OpenAlex work ID

Look up several at once:

```bash
opencite lookup 10.1038/nature12345 pmid:34265844 arxiv:1706.03762
```

### Enrich across sources

By default `lookup` resolves the identifier from the most appropriate single
source. Add `--enrich` to fetch from every API and merge the results into one
richer record (more identifiers, abstract, citation counts, PDF locations):

```bash
opencite lookup 10.1038/nature12345 --enrich
```

### Append to a BibTeX library

```bash
opencite lookup 10.1038/nature12345 --append-bib refs.bib
```

This fetches the entry and appends it to an existing `.bib` file, so you can
build a reference library one paper at a time.

## Citation graphs

The `cite` command traverses citations around a paper.

```bash
# Papers that cite this work
opencite cite 10.1038/nature12345 --direction citing

# Papers this work cites (its references)
opencite cite 10.1038/nature12345 --direction references

# Both directions
opencite cite 10.1038/nature12345 --direction both
```

Refine the traversal:

```bash
opencite cite 10.1038/nature12345 \
    --direction citing \
    --max 50 \
    --sort citations \
    --min-citations 100
```

- `--max N`: cap the number of returned papers.
- `--sort citations|year`: order the neighbours.
- `--min-citations N`: keep only well-cited neighbours, useful for finding the
  influential descendants of a seminal paper.

## Convert between identifiers

When you only need to translate identifiers (not full records), `ids` uses the
NCBI ID Converter API to map between DOI, PMID, and PMCID:

```bash
opencite ids 34265844
opencite ids PMC8341181 10.1038/nature12345 -f json
```

## Use it from Python

The same traversals are available programmatically through
[`CitationExplorer`](../api/citations.md):

```python
import asyncio
from opencite import Config
from opencite.citations import CitationExplorer


async def main():
    async with CitationExplorer(Config.from_env()) as explorer:
        result = await explorer.citing_papers("10.1038/nature12345", max_results=20)
        for paper in result.papers:
            print(paper.citation_count, paper.title)


asyncio.run(main())
```
