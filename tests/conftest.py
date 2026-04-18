"""pytest shared fixtures + sys.path setup for the SD-BKZ benchmark
unit tests.

Every test module can import directly from scripts/_math_core.py,
scripts/_bkz_core.py, scripts/log.py, etc. without further path
gymnastics.
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
sys.path.insert(0, os.path.join(REPO, "analysis"))
