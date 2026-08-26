#!/usr/bin/env python3
"""Initialize the image-prompt-manager database using the shared library code."""

import sys

from library import main


if __name__ == "__main__":
    raise SystemExit(main([*sys.argv[1:], "init"]))
