"""Convenience entry point: python main.py <command> ...

The actual CLI logic lives in vtt_translator/cli.py. This file exists so
that ``python main.py`` keeps working for users who haven't pip-installed
the package.
"""

import sys

from vtt_translator.cli import main

if __name__ == "__main__":
    sys.exit(main())
