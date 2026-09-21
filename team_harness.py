#!/usr/bin/env python3
"""Portable entrypoint; uses only Python 3.10+ standard library and Git."""
import sys
sys.dont_write_bytecode = True
from harness.cli import main
if __name__ == '__main__':
    raise SystemExit(main())
