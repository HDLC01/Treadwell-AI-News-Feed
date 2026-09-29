"""Put backend/ on the import path, the way the app itself runs (from backend/)."""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
