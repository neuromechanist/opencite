# Development

Want to hack on OpenCite or understand how it fits together? Start here.

- [Architecture](architecture.md): the package layout, key design patterns, and
  how the sources are integrated.
- [Contributing](contributing.md): set up a dev environment, run the checks, and
  open a pull request.
- [Testing](testing.md): unit tests, integration tests, and what needs API keys.

## Quick setup

```bash
git clone https://github.com/neuromechanist/opencite.git
cd opencite
uv sync --extra dev
uv run opencite --version
```
