import pytest

from groupoffice_mcp_server.config import GroupOfficeConfig


class TestGroupOfficeConfig:
    def test_defaults(self):
        config = GroupOfficeConfig(url="https://go.example.com", api_token="tok")
        assert config.verify_ssl is True
        assert config.timeout == 30.0
        assert config.max_retries == 3
        assert config.debug is False
        assert config.read_only is True

    def test_url_strips_trailing_slash(self):
        config = GroupOfficeConfig(url="https://go.example.com/", api_token="tok")
        assert config.url == "https://go.example.com"

    def test_url_requires_http_scheme(self):
        with pytest.raises(ValueError):
            GroupOfficeConfig(url="ftp://go.example.com", api_token="tok")

    def test_endpoints(self):
        config = GroupOfficeConfig(url="https://go.example.com", api_token="tok")
        assert config.jmap_endpoint == "https://go.example.com/api/jmap.php"
        assert config.upload_endpoint == "https://go.example.com/api/upload.php"
        assert config.download_endpoint == "https://go.example.com/api/download.php"

    def test_from_env_requires_url(self, monkeypatch):
        monkeypatch.delenv("GROUPOFFICE_URL", raising=False)
        monkeypatch.setenv("GROUPOFFICE_API_TOKEN", "tok")
        with pytest.raises(RuntimeError, match="GROUPOFFICE_URL"):
            GroupOfficeConfig.from_env()

    def test_from_env_requires_token(self, monkeypatch):
        monkeypatch.setenv("GROUPOFFICE_URL", "https://go.example.com")
        monkeypatch.delenv("GROUPOFFICE_API_TOKEN", raising=False)
        with pytest.raises(RuntimeError, match="GROUPOFFICE_API_TOKEN"):
            GroupOfficeConfig.from_env()

    def test_from_env_full(self, monkeypatch):
        monkeypatch.setenv("GROUPOFFICE_URL", "https://go.example.com")
        monkeypatch.setenv("GROUPOFFICE_API_TOKEN", "tok")
        monkeypatch.setenv("GROUPOFFICE_VERIFY_SSL", "false")
        monkeypatch.setenv("GROUPOFFICE_TIMEOUT", "10")
        monkeypatch.setenv("GROUPOFFICE_MAX_RETRIES", "5")
        monkeypatch.setenv("GROUPOFFICE_DEBUG", "true")
        monkeypatch.setenv("GROUPOFFICE_READONLY", "false")

        config = GroupOfficeConfig.from_env()
        assert config.url == "https://go.example.com"
        assert config.api_token == "tok"
        assert config.verify_ssl is False
        assert config.timeout == 10.0
        assert config.max_retries == 5
        assert config.debug is True
        assert config.read_only is False

    def test_from_env_read_only_defaults_true(self, monkeypatch):
        monkeypatch.setenv("GROUPOFFICE_URL", "https://go.example.com")
        monkeypatch.setenv("GROUPOFFICE_API_TOKEN", "tok")
        monkeypatch.delenv("GROUPOFFICE_READONLY", raising=False)
        config = GroupOfficeConfig.from_env()
        assert config.read_only is True

    def test_from_env_read_only_empty_is_fail_closed(self, monkeypatch):
        monkeypatch.setenv("GROUPOFFICE_URL", "https://go.example.com")
        monkeypatch.setenv("GROUPOFFICE_API_TOKEN", "tok")
        monkeypatch.setenv("GROUPOFFICE_READONLY", "")
        config = GroupOfficeConfig.from_env()
        assert config.read_only is True

    def test_from_env_read_only_whitespace_is_fail_closed(self, monkeypatch):
        monkeypatch.setenv("GROUPOFFICE_URL", "https://go.example.com")
        monkeypatch.setenv("GROUPOFFICE_API_TOKEN", "tok")
        monkeypatch.setenv("GROUPOFFICE_READONLY", "   ")
        config = GroupOfficeConfig.from_env()
        assert config.read_only is True
