# Output Formats

The `search`, `lookup`, `cite`, and `canonical` commands all share the same
output controls: `-f`/`--format` chooses the shape, and `-o`/`--output` writes to
a file instead of stdout.

## Formats

| Format | Flag | Best for | Available in |
| --- | --- | --- | --- |
| Text | `-f text` (default) | Reading in the terminal | all commands |
| JSON | `-f json` | Piping into other tools, batch downloads | all commands |
| BibTeX | `-f bibtex` | Reference managers, LaTeX | all commands |
| CSV | `-f csv` | Spreadsheets | `search` only |

## Text

The default. Human-readable, one paper per block, with title, authors, year,
venue, and identifiers.

```bash
opencite search "graph neural networks"
```

## JSON

Structured output, ideal as machine input. The JSON from a `search` is the
natural input for [batch downloads](pdf-and-conversion.md#batch-downloads):

```bash
opencite search "graph neural networks" --max 50 -f json -o gnn.json
opencite batch-fetch --from-json gnn.json --convert -o ./papers
```

Add `-v`/`--verbose` to include extra fields such as per-source PDF locations,
license, and version where the upstream APIs surface them.

## BibTeX

Citation entries ready for your reference manager or LaTeX bibliography:

```bash
opencite search "graph neural networks" --max 20 -f bibtex -o gnn.bib
```

`lookup` can also append to an existing library in one step:

```bash
opencite lookup 10.1038/nature12345 --append-bib refs.bib
```

## CSV

A flat, spreadsheet-friendly table. Available for `search`:

```bash
opencite search "graph neural networks" --max 100 -f csv -o gnn.csv
```

## Writing to a file

Every format respects `-o`/`--output`:

```bash
opencite canonical "reinforcement learning" --min-citations 2000 -f bibtex -o rl.bib
```

Without `-o`, output goes to stdout, so you can pipe it:

```bash
opencite search "transformers" -f json | jq '.[].title'
```
