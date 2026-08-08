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

# Any log line a test emits to the central pipeline.jsonl is stamped tag="test"
# so analysis + monitoring filter it out (progress_age_min, the BAD grep, etc.).
# Centralised-but-marked: we never lose test/dry-run logs, they just don't count.
os.environ.setdefault("PIPELINE_LOG_TAG", "test")
