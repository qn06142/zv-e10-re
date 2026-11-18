"""Self-test runner for retool.

Invokes the comprehensive unit and integration test suite defined in
tests/test_retool.py.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root is on sys.path
root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from tests.test_retool import main


if __name__ == "__main__":
    main()
