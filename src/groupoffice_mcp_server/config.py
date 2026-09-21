import os

from pydantic import BaseModel, Field, field_validator


def _env_flag(name: str, *, default: bool) -> bool:
    """Parse a boolean env var fail-closed for security-sensitive defaults.

    Unset or blank → ``default``. Only explicit falsey tokens (``0`` / ``false``
    / ``no``) flip a default-True flag off; only explicit truthy tokens flip a
    default-False flag on.
    """
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    val = str(raw).strip().lower()
    if default:
        return val not in ("0", "false", "no")
    return val in ("1", "true", "yes", "on")


class GroupOfficeConfig(BaseModel):
    """Configuration for connecting to a GroupOffice instance.

    There is deliberately no default for `url`/`api_token`: a bundled demo
    host or empty-token default would be a security footgun, so `from_env()`
    raises instead of silently pointing at nothing (or worse, someone else's
    instance).
    """

    url: str = Field(
        description=(
            "Base URL of the GroupOffice instance, e.g. "
            "https://groupoffice.example.com (no trailing path - "
            "/api/jmap.php etc. are appended internally)"
        )
    )
    api_token: str = Field(
        repr=False,
        description="Bearer token from the GroupOffice 'API keys' community module",
    )
    verify_ssl: bool = Field(default=True, description="Verify TLS certificates")
    timeout: float = Field(default=30.0, description="HTTP request timeout in seconds")
    max_retries: int = Field(
        default=3,
        description="Connection-level retries for transient network errors (not 4xx/5xx bodies)",
    )
    debug: bool = Field(default=False, description="Enable debug logging")
    read_only: bool = Field(
        default=True,
        description=(
            "When true (the default), all mutating tools (create/update/delete/"
            "upload) are rejected before any API call is made. Set "
            "GROUPOFFICE_READONLY=false to allow writes."
        ),
    )

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("GROUPOFFICE_URL must be a valid HTTP/HTTPS URL")
        return v.rstrip("/")

    @classmethod
    def from_env(cls) -> "GroupOfficeConfig":
        url = os.getenv("GROUPOFFICE_URL")
        token = os.getenv("GROUPOFFICE_API_TOKEN")
        if not url:
            raise RuntimeError(
                "GROUPOFFICE_URL is required - set it to your GroupOffice "
                "instance base URL, e.g. https://groupoffice.example.com"
            )
        if not token:
            raise RuntimeError(
                "GROUPOFFICE_API_TOKEN is required - generate one via "
                "System Settings -> API Keys in your GroupOffice instance"
            )
        return cls(
            url=url,
            api_token=token,
            verify_ssl=_env_flag("GROUPOFFICE_VERIFY_SSL", default=True),
            timeout=float(os.getenv("GROUPOFFICE_TIMEOUT", "30")),
            max_retries=int(os.getenv("GROUPOFFICE_MAX_RETRIES", "3")),
            debug=_env_flag("GROUPOFFICE_DEBUG", default=False),
            read_only=_env_flag("GROUPOFFICE_READONLY", default=True),
        )

    @property
    def jmap_endpoint(self) -> str:
        return f"{self.url}/api/jmap.php"

    @property
    def upload_endpoint(self) -> str:
        return f"{self.url}/api/upload.php"

    @property
    def download_endpoint(self) -> str:
        return f"{self.url}/api/download.php"
