# Exceptions

OpenCite raises a small hierarchy of exceptions, all rooted at
`OpenCiteError`. Catch the base class to handle any OpenCite-specific failure,
or a specific subclass for finer control.

```python
from opencite.exceptions import OpenCiteError, APIKeyError, RateLimitError

try:
    ...
except APIKeyError:
    ...        # missing or invalid API key
except RateLimitError:
    ...        # upstream rate limit hit
except OpenCiteError:
    ...        # any other OpenCite error
```

::: opencite.exceptions
