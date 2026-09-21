# GroupOffice MCP Server

<img src="debian/mcp-server-groupoffice.svg" alt="mcp-server-groupoffice icon" width="96" height="96" />

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyPI version](https://badge.fury.io/py/groupoffice-mcp-server.svg)](https://pypi.org/project/groupoffice-mcp-server/)
![Packaging: deb](https://img.shields.io/badge/packaging-.deb-red?logo=debian&logoColor=white)
[![wakatime](https://wakatime.com/badge/user/5abba9ca-813e-43ac-9b5f-b1cfdf3dc1c7/project/10f2f38f-511c-4085-ac0d-ae5a15c7b8cc.svg)](https://wakatime.com/badge/user/5abba9ca-813e-43ac-9b5f-b1cfdf3dc1c7/project/10f2f38f-511c-4085-ac0d-ae5a15c7b8cc)

An [MCP](https://modelcontextprotocol.io/) (Model Context Protocol) server for
[GroupOffice](https://www.group-office.com/) groupware, built on
[FastMCP](https://github.com/Vitexus/python3-fastmcp). It talks to GroupOffice's
JMAP-style batch/RPC API and exposes Contacts, Calendars, Tasks, Notes, Projects,
Comments, History, Users, Groups, and file attachments as MCP tools.

**Defaults to read-only.** Mutating tools (create/update/delete/upload) are
rejected before any API call unless you explicitly set `GROUPOFFICE_READONLY=false`.

## Features

- **Contacts & Address Books** - search, read, create, update, delete
- **Calendars & Events** - search, read, create, update, delete
- **Tasks & Task Lists** - search, read, create, update, delete
- **Notes** - search, read, create, update, delete
- **Projects** (Projects v3 module, optional) - search, read, create, update, delete
- **Comments** - search, read, create, update, delete
- **History** (audit log, read-only) - search
- **Users & Groups** (read-only - administration is out of scope)
- **File attachments** - upload/download as GroupOffice blobs
- MCP resources for browsable lists (address books, calendars, task lists,
  supported-entity registry)
- MCP prompts encoding a "read before write" workflow (daily briefing, contact
  lookup before creating a duplicate, conflict check before scheduling an event)
- Every tool carries MCP annotations (`readOnlyHint`/`destructiveHint`/
  `idempotentHint`/`openWorldHint`) so clients can reason about risk

## Installation

```bash
pip install -e .
# or, from PyPI:
pip install groupoffice-mcp-server
```

Published on PyPI at
[pypi.org/project/groupoffice-mcp-server](https://pypi.org/project/groupoffice-mcp-server/).

This project targets the `fastmcp` build packaged at
[github.com/Vitexus/python3-fastmcp](https://github.com/Vitexus/python3-fastmcp)
(Debian `python3-fastmcp`). A generic PyPI `fastmcp` install may differ.

A Debian package (`mcp-server-groupoffice`, with a companion
`mcprack-mcp-server-groupoffice` package that registers it into a local
[mcprack](https://github.com/VitexSoftware/mcprack) MCP catalog) is also
published with each [GitHub release](https://github.com/VitexSoftware/mcp-server-groupoffice/releases).

## Configuration

Copy `.env.example` to `.env` and fill in your instance's details, or set these
environment variables directly:

| Variable | Required | Default | Description |
|---|---|---|---|
| `GROUPOFFICE_URL` | **yes** | - | Base URL of your GroupOffice instance, e.g. `https://groupoffice.example.com` |
| `GROUPOFFICE_API_TOKEN` | **yes** | - | Bearer token from System Settings -> API Keys (requires the "API key generator" community module) |
| `GROUPOFFICE_VERIFY_SSL` | no | `true` | Verify TLS certificates |
| `GROUPOFFICE_TIMEOUT` | no | `30` | HTTP request timeout, seconds |
| `GROUPOFFICE_MAX_RETRIES` | no | `3` | Connection-level retries on transient network errors |
| `GROUPOFFICE_DEBUG` | no | `false` | Enable debug logging |
| `GROUPOFFICE_READONLY` | no | `true` | When true (default), all mutating tools are rejected. Empty/unset stays fail-closed; set `false` to allow writes. |

There is deliberately no default for `GROUPOFFICE_URL`/`GROUPOFFICE_API_TOKEN` -
a bundled demo/default host would be a security footgun, so the server refuses
to start without them.

### Getting an API token

1. In GroupOffice, go to System Settings -> Modules, install the community
   **"API key generator"** module if it isn't installed yet.
2. Go to System Settings -> API Keys -> Add key.
3. Give it a name and pick the user it should act as, then save.
4. Open the key's menu (⋮) -> **View access token** (or **Copy token to
   clipboard**) to get the bearer token.

## Usage

Run directly:

```bash
groupoffice-mcp-server
```

Or add it to an MCP client (e.g. Claude Desktop) config:

```json
{
  "mcpServers": {
    "groupoffice": {
      "command": "groupoffice-mcp-server",
      "env": {
        "GROUPOFFICE_URL": "https://groupoffice.example.com",
        "GROUPOFFICE_API_TOKEN": "your-api-token"
      }
    }
  }
}
```

## Container image

A container image is published to Docker Hub at
[`docker.io/vitexsoftware/mcp-server-groupoffice`](https://hub.docker.com/r/vitexsoftware/mcp-server-groupoffice),
built from the repo's `Containerfile` (a two-stage `uv`-based Python build on
`python:3.12-slim`). Run it directly - it speaks MCP over stdio, so it must
be launched by an MCP client, not run detached:

```bash
podman run --rm -i \
  -e GROUPOFFICE_URL=https://groupoffice.example.com \
  -e GROUPOFFICE_API_TOKEN=your-api-token \
  docker.io/vitexsoftware/mcp-server-groupoffice:0.2.0
```

(or `docker run` - the image works with either).

## Kubernetes / Helm

A Helm chart lives in [`helm/`](helm/). Since the server is stdio-only (no
HTTP port to expose as a Service), the chart deploys a single always-on pod
that an MCP client reaches via `kubectl exec`, rather than a Service +
Ingress:

```bash
helm upgrade --install groupoffice-mcp helm/ \
  --set environment.GROUPOFFICE_URL=https://groupoffice.example.com \
  --set secrets.GROUPOFFICE_API_TOKEN=your-api-token
```

Never put a real token in `values.yaml` or `--set` on the command line for
anything beyond ad-hoc testing - pass it via `-f` with a values file kept out
of version control, or wire the chart's Secret up to your cluster's secret
manager (sealed-secrets, External Secrets, Vault, etc.). See
`helm/templates/NOTES.txt` (printed after install) for how to reach the pod
once it's running.

## Tools

Every entity follows the same `query_*`/`get_*`/`create_*`/`update_*`/`delete_*`
shape. `filter` accepts a raw GroupOffice JMAP filter dict for anything beyond
the named convenience parameters.

| Entity | Tools | Notes |
|---|---|---|
| AddressBook | `list_addressbooks` | read-only |
| Contact | `query_contacts`, `get_contact`, `create_contact`, `update_contact`, `delete_contact` | `addressbook_id` filters by `addressBookId` |
| Calendar | `list_calendars` | read-only |
| CalendarEvent | `query_calendar_events`, `get_calendar_event`, `create_calendar_event`, `update_calendar_event`, `delete_calendar_event` | no `end` property - events use `start` + `duration` (ISO 8601, e.g. `PT1H`) |
| TaskList | `list_tasklists` | read-only |
| Task | `query_tasks`, `get_task`, `create_task`, `update_task`, `delete_task` | `tasklist_id` filters by `tasklistId`; completion is `percentComplete` (0-100), not a boolean |
| NoteBook | `list_notebooks` | read-only; required `noteBookId` for `create_note` |
| Note | `query_notes`, `get_note`, `create_note`, `update_note`, `delete_note` | `noteBookId` is required on create |
| Project3 | `query_projects`, `get_project`, `create_project`, `update_project`, `delete_project` | optional module - errors on instances where it isn't installed |
| Comment | `query_comments`, `get_comment`, `create_comment`, `update_comment`, `delete_comment` | filter by `entity` (friendly name, e.g. "Contact") + `entity_id` |
| LogEntry (History) | `query_history` | read-only audit log; same `entity`/`entity_id` filter as Comment |
| User | `query_users`, `get_user` | read-only - user administration is out of scope |
| Group | `query_groups`, `get_group` | read-only - group administration is out of scope |
| Blob | `upload_file`, `download_file` | upload returns a `blob_id` to attach via another entity's `data`; GroupOffice responds with HTTP 201 on success |

`Instance` (multi-tenant administration) is deliberately not exposed - it is
high-privilege and out of scope for this server.

## Resources

- `groupoffice://addressbooks`, `groupoffice://calendars`, `groupoffice://tasklists`
  - browsable equivalents of the `list_*` tools
- `groupoffice://entities` - static registry of entities/operations this
  server exposes (not introspected from `/api/doc.php`, which is per-instance
  HTML, not a stable machine-readable contract)

## Prompts

- `daily_briefing(date=None)` - today's calendar events + open tasks
- `contact_lookup(query)` - search before ever suggesting `create_contact`,
  to avoid duplicates
- `schedule_event_safely(title, start, end, calendar_id=None)` - checks for
  conflicts before suggesting `create_calendar_event`

## Security considerations

- **Read-only by default.** `GROUPOFFICE_READONLY=false` is required to allow
  any create/update/delete/upload call; this is enforced centrally by a
  FastMCP middleware hook (`ReadOnlyGuardMiddleware`) that runs before every
  tool call, keyed off each tool's `readOnlyHint` annotation - a new tool
  can't accidentally skip the gate.
- The bearer token is passed via environment variable only; it is never
  logged or written to disk by this server.
- `User`/`Group` administration and the `Instance` (multi-tenant admin)
  entity are not exposed by this server at all, regardless of read-only mode,
  since they carry a much larger blast radius than typical groupware data.

## Known limitations

- Covers a curated subset of GroupOffice's 60+ entities, not the full object
  model. Adding another entity is mechanical (new `@mcp.tool` functions in
  `server.py` calling the existing generic `client.get`/`query`/`set`) - no
  transport changes needed.
- GroupOffice publishes no OpenAPI/Swagger spec; this server was built and
  verified against a live instance's actual (undocumented in places) query
  filter behavior. Filter/property names can vary by GroupOffice version -
  check your instance's `/api/doc.php` if a named convenience filter
  (`addressbook_id`, `calendar_id`, `tasklist_id`, `entity`/`entity_id`)
  doesn't behave as expected; the raw `filter` dict parameter always works as
  an escape hatch.
- `download_file` returns base64-encoded content, which inflates size by
  ~33% - fine for small attachments, not recommended for large files.
- Auth is bearer-token-only, matching GroupOffice's documented API; there is
  no OAuth2 flow (GroupOffice's own "OAuth2 Client" feature is for GroupOffice
  acting as a client to other services, not for authenticating third parties
  against GroupOffice itself).
- The Kubernetes Helm chart runs the server as a single always-on pod reached
  via `kubectl exec`, since MCP-over-stdio has no port to put behind a
  Service - it is not a horizontally-scaled deployment model.

## Development

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

Tests run entirely offline against a mocked `GroupOfficeClient` (via
`httpx.MockTransport` for client-layer tests, and dependency injection for
tool-layer tests) - no live GroupOffice instance is required.

Empty or unset ``GROUPOFFICE_READONLY`` stays fail-closed (writes blocked).
Only an explicit ``false`` / ``0`` / ``no`` enables mutating tools.

### Live capability scenario

```bash
export GROUPOFFICE_URL=https://go.vitexsoftware.com
export GROUPOFFICE_API_TOKEN=your-token
export GROUPOFFICE_READONLY=true
python tests/live_capability_scenario.py --json-out /tmp/go-live.json

# Non-production only — create/update/delete cycle:
python tests/live_capability_scenario.py --allow-writes --json-out /tmp/go-write.json
```

### Manual live smoke test

Run the server directly to confirm it starts and connects:

```bash
export GROUPOFFICE_URL=https://your-instance.example.com
export GROUPOFFICE_API_TOKEN=your-token
python -m groupoffice_mcp_server.server
# or, once installed: groupoffice-mcp-server
```

To call individual tools against a live instance without a full MCP client,
use FastMCP's in-memory `Client` (the same pattern the test suite uses):

```python
import asyncio
from fastmcp import Client
from groupoffice_mcp_server.config import GroupOfficeConfig
from groupoffice_mcp_server.server import create_server

async def main():
    mcp = create_server(GroupOfficeConfig.from_env())
    async with Client(mcp) as c:
        result = await c.call_tool("query_contacts", {"limit": 5})
        print(result.data)

        # should be refused - read-only mode is on by default
        try:
            await c.call_tool("create_contact", {"data": {"firstName": "Test"}})
        except Exception as e:
            print("blocked as expected:", e)

asyncio.run(main())
```

Only run a mutating call (`GROUPOFFICE_READONLY=false`) against a
disposable/test instance, never production data.

## License

MIT
