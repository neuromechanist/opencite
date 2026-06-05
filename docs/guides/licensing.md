# Redistribution & Licensing

OpenCite retrieves PDFs and markdown for you and **reports** what it found, but
it does not enforce a redistribution policy. The publication-versus-reuse
decision belongs to you, the caller. This page explains what OpenCite reports so
you can make that decision deliberately.

## What OpenCite reports

### Open-access status

[`Paper.oa_status`](../api/models.md) carries the OpenAlex Open Access status:

- `gold`, `hybrid`, `green`, `bronze`, `closed`, `diamond`, or empty (unknown).
- `is_oa = True` collapses all open categories together; `oa_status`
  distinguishes them.

!!! warning "Bronze is free-to-read, not openly licensed"
    A `bronze` paper can be read for free on the publisher site but is **not**
    released under an open license. Free to read does not mean free to
    redistribute.

### Per-source license and version

[`PDFLocation.license`](../api/models.md) and `PDFLocation.version` record, where
the upstream API surfaces them:

- the license string (`cc-by`, `cc-by-nc`, ...)
- the version (`publishedVersion`, `acceptedVersion`, `submittedVersion`)

These are visible in `opencite lookup --format json --verbose` and in
`opencite search` output.

### The license sidecar

Every downloaded PDF gets a `<pdf>.license.json` sidecar written next to it,
containing:

```json
{
  "url": "...",
  "source": "...",
  "license": "cc-by",
  "version": "publishedVersion",
  "oa_status": "gold",
  "publisher_tdm": false,
  "doi": "10.1038/nature12345",
  "retrieved_at": "..."
}
```

A later "is this PDF safe to commit?" check can scan the sidecars without
re-querying the original metadata.

## Guidance for pipelines that publish artifacts

If your pipeline commits PDFs or markdown to a public repository, be deliberate
about which sources you enable.

- Publisher TDM tokens (Elsevier, Wiley, Springer) almost universally **prohibit
  redistribution** of the bytes they return.
- The sidecar's `publisher_tdm: true` flag is a machine-readable signal that a
  downstream scanner can use to block such files from being published.

When in doubt, prefer `gold`/`diamond`/`cc-by` sources for anything you intend
to redistribute, and treat `bronze` and publisher-TDM content as read-only.
