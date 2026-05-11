import sys
from pathlib import Path

# Ensure the project root is on sys.path so root-level modules can be imported in tests.
sys.path.insert(0, str(Path(__file__).resolve().parent))
