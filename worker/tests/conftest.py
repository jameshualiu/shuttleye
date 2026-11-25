"""Put worker/ on sys.path so tests can import worker packages such as `train`.

worker/ and worker/tests/ both have __init__.py, so pytest's rootdir insertion
adds the repo root, not worker/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
