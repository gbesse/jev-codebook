# Purpose: Allow `python -m jev_codebook ...` as an equivalent of the `jev-codebook` console script.
"""Module entry point delegating to the CLI."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
