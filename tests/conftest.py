"""Shared pytest fixtures for maestarr.

Every test runs against a fresh, empty data directory and no `.env`, so the
developer's own database and configuration can never leak into (or be
modified by) the test suite.
"""

from __future__ import annotations

import pytest

from maestarr.config import Settings, get_config_store, get_settings


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("MAESTARR_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in Settings.model_fields:
        if name != "MAESTARR_DATA_DIR":
            monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    get_config_store.cache_clear()
    yield
    get_settings.cache_clear()
    get_config_store.cache_clear()
