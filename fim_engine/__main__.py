"""
FIM Engine - Package Main Entrypoint
Enables `python -m fim_engine ...` invocation.
"""

import sys
from fim_engine.cli import main

if __name__ == "__main__":
    sys.exit(main())

