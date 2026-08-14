"""Entry point for the packaged application.

PyInstaller runs its entry script as a top-level module, so the frozen build
cannot start from `mousemod/__main__.py` (its relative imports have no parent
package). This module imports the package absolutely instead.
"""

import multiprocessing
import sys

from mousemod.cli import main

if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())
