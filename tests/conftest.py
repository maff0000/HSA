"""Shared pytest fixtures for the HSA contract tests.

Fixture documents live in ``tests/fixtures/valid`` and
``tests/fixtures/invalid`` and are named predictably: ``<kind>.json`` for
the canonical example of each contract kind, plus a few extra files whose
names say what they exercise. Later work items are expected to reuse them
rather than hand-rolling documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
VALID_DIR = FIXTURE_DIR / "valid"
INVALID_DIR = FIXTURE_DIR / "invalid"


def _load(path: Path):
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def valid_doc():
    """Load a valid fixture document by name, e.g. ``valid_doc("chain")``."""

    def loader(name: str):
        return _load(VALID_DIR / (name + ".json"))

    return loader


@pytest.fixture
def invalid_doc():
    """Load an invalid fixture document by name."""

    def loader(name: str):
        return _load(INVALID_DIR / (name + ".json"))

    return loader


@pytest.fixture
def valid_path():
    """Path to a valid fixture document, for CLI tests."""

    def resolver(name: str) -> Path:
        return VALID_DIR / (name + ".json")

    return resolver


@pytest.fixture
def invalid_path():
    """Path to an invalid fixture document, for CLI tests."""

    def resolver(name: str) -> Path:
        return INVALID_DIR / (name + ".json")

    return resolver
