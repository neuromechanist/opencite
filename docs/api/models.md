# Models

The data models returned throughout OpenCite. `Paper` is the central record;
`IDSet` is the frozen, immutable bundle of identifiers that makes cross-API
lookup and deduplication possible.

::: opencite.models
    options:
      members:
        - Paper
        - Author
        - IDSet
        - Source
        - PDFLocation
        - SearchResult
        - CitationResult
        - parse_identifier
