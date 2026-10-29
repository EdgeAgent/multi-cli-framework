#!/usr/bin/env python3
"""Executable wrapper: python run.py run "hello"  (same as python -m framework)."""
import sys

from framework.cli import main

if __name__ == "__main__":
    sys.exit(main())
