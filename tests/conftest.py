"""Pytest configuration and fixtures for vairified tests."""

import pytest


@pytest.fixture
def api_key() -> str:
    """Test API key fixture."""
    return "vair_pk_test_123456789"


@pytest.fixture
def base_url() -> str:
    """Test base URL fixture."""
    return "https://api-next.vairified.com/api/v1"
