"""Entry point for `python -m opencite` and the `opencite` console script."""

import sys

from opencite.cli import main

sys.exit(main())
