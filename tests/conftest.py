import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Ensure tests exercise this repo's src/ tree, not any installed package.
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from groupoffice_mcp_server.client import GroupOfficeClient  # noqa: E402
from groupoffice_mcp_server.config import GroupOfficeConfig  # noqa: E402
from groupoffice_mcp_server.server import create_server  # noqa: E402


@pytest.fixture
def config() -> GroupOfficeConfig:
    return GroupOfficeConfig(url="https://go.example.com", api_token="test-token")


@pytest.fixture
def writable_config() -> GroupOfficeConfig:
    return GroupOfficeConfig(url="https://go.example.com", api_token="test-token", read_only=False)


@pytest.fixture
def mock_client() -> MagicMock:
    return MagicMock(spec=GroupOfficeClient)


@pytest.fixture
def server(config, mock_client):
    return create_server(config, client=mock_client)


@pytest.fixture
def writable_server(writable_config, mock_client):
    return create_server(writable_config, client=mock_client)
