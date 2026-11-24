"""Remove leaked secrets from the whole git history of a repository and replace the history on its remote."""

import sys

if sys.version_info < (3, 11):
    sys.exit("Python 3.11 or newer is needed (python --version)")

__version__ = "1.1.0"
