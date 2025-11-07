"""Placeholder for the hosted olmOCR CLI shim.

This file will be replaced with the upstream version from /data/projects/olmocr
once we sync dependencies and tests, but we keep the stub so callers can import
`scripts.olmocr_cli` without tripping ModuleNotFoundError during scaffolding.
"""

import sys


def main() -> None:
    """Temporary entry point that just aborts with guidance."""

    sys.exit("olmocr_cli is not yet wired in this scaffold; copy it from /data/projects/olmocr")


if __name__ == "__main__":
    main()
