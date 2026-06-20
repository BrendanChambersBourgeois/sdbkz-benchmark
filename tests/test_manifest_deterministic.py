"""INC-48 guard: the manifest timestamp is byte-stable in deterministic mode.

`make manifest` used to embed a wall-clock generated_utc + per-seed
verified_at_utc, so every rebuild churned ~10k lines with no content change.
build_seed_manifest now supports --deterministic (single frozen timestamp,
SOURCE_DATE_EPOCH or epoch 0); the Makefile target uses it. These tests pin that
behaviour so the churn cannot silently return.
"""
from __future__ import annotations

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

from build_seed_manifest import _resolve_generated_utc  # noqa: E402


def test_deterministic_is_stable_across_calls():
    assert _resolve_generated_utc(True) == _resolve_generated_utc(True)


def test_deterministic_default_is_epoch_zero(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert _resolve_generated_utc(True) == "1970-01-01T00:00:00Z"


def test_deterministic_honours_source_date_epoch(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    assert _resolve_generated_utc(True) == "2023-11-14T22:13:20Z"


def test_nondeterministic_is_not_frozen(monkeypatch):
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    assert _resolve_generated_utc(False) != "1970-01-01T00:00:00Z"
