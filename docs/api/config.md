# Config

`Config` resolves settings from `~/.opencite/config.toml`, `.env` files, and
environment variables, merging them with environment variables taking
precedence. Build one with `Config.from_env()` and pass it to an orchestrator.

```python
from opencite import Config

config = Config.from_env()
```

See the [Configuration guide](../guides/configuration.md) for the precedence
rules and the keys OpenCite reads.

::: opencite.config.Config
