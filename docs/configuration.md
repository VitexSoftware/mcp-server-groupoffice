# Configuration

All configuration is via environment variables (see `.env.example`), read by
`GroupOfficeConfig.from_env()`.

## Required

| Variable | Description |
|---|---|
| `GROUPOFFICE_URL` | Base URL of the GroupOffice instance, e.g. `https://groupoffice.example.com`. No trailing path - `/api/jmap.php`, `/api/upload.php`, `/api/download.php` are appended internally. Trailing slashes are stripped automatically. |
| `GROUPOFFICE_API_TOKEN` | Bearer token from System Settings -> API Keys (requires the "API key generator" community module to be installed). |

There is no default for either - `from_env()` raises `RuntimeError` if they
are unset, rather than silently pointing at a demo host or an empty token.

## Optional

| Variable | Default | Description |
|---|---|---|
| `GROUPOFFICE_VERIFY_SSL` | `true` | Verify TLS certificates. Only disable against a trusted internal instance with a self-signed cert. |
| `GROUPOFFICE_TIMEOUT` | `30` | HTTP request timeout, in seconds. |
| `GROUPOFFICE_MAX_RETRIES` | `3` | Connection-level retries on transient network errors (connection refused, timeout) - does not retry on HTTP 4xx/5xx responses or JMAP-level errors. |
| `GROUPOFFICE_DEBUG` | `false` | Enable debug logging. |
| `GROUPOFFICE_READONLY` | `true` | When true, all mutating tools (`create_*`/`update_*`/`delete_*`/`upload_file`) are rejected before any API call is made. Set to `false` to allow writes. |

## Example presets

**Local development against a test instance, read-only (safe default):**

```bash
export GROUPOFFICE_URL=https://go-test.example.com
export GROUPOFFICE_API_TOKEN=xxxxxxxx
export GROUPOFFICE_DEBUG=true
```

**Allowing writes, e.g. for integration testing against a disposable instance:**

```bash
export GROUPOFFICE_URL=https://go-test.example.com
export GROUPOFFICE_API_TOKEN=xxxxxxxx
export GROUPOFFICE_READONLY=false
```

**Running the automated test suite:** no environment variables are needed -
`tests/conftest.py` builds a `GroupOfficeConfig` directly with a fixture URL/
token and injects a mocked `GroupOfficeClient`, so `pytest tests/` runs fully
offline.
