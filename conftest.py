"""Ensures the project root is on sys.path so `import src...` works when
pytest is invoked from any directory."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
