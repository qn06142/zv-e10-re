#!/usr/bin/env python3
"""Convenience CLI entry point for Sony ulogio binary log decoder."""
import os
import sys

# Ensure repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from research.log_decoder.decode_app_log import main

if __name__ == "__main__":
    sys.exit(main())
