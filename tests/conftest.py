"""Shared pytest fixtures for maestarr.

This file stays at the `tests/` root, unsplit: pytest discovers `conftest.py`
upward, so these fixtures reach `unit/`, `integration/`, and `e2e/` alike.
"""

from __future__ import annotations

import pytest

from maestarr.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache():
    """Reset the settings singleton around every test.

    Settings are cached with lru_cache, so a test that monkeypatches the
    environment would otherwise see a stale singleton built by an earlier test.
    """
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
