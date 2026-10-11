"""Shared fixtures for zonal_heating tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Allow custom_components to load in every test."""
    yield
