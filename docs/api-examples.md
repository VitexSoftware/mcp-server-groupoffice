# GroupOffice JMAP API examples

These examples show the raw JMAP-style batch requests this server's
`GroupOfficeClient` sends under the hood, for reference when adding new
entities or debugging a filter that doesn't behave as expected.

## Batch request/response shape

A single `query_contacts` MCP tool call issues one HTTP POST containing two
JMAP calls (a query, then a get via back-reference):

```
POST /api/jmap.php
Authorization: Bearer <token>
Content-Type: application/json

[
  ["Contact/query", {"filter": {"addressBookId": "1"}, "limit": 50}, "c0"],
  ["Contact/get", {"#ids": {"resultOf": "c0", "path": "/ids"}}, "c1"]
]
```

Response (array of `[method, result, clientId]` triples, order not
guaranteed - matched back to the request by `clientId`):

```json
[
  ["Contact/get", {"list": [{"id": "3", "firstName": "Jan", "lastName": "Novak"}], "notFound": []}, "c1"],
  ["Contact/query", {"ids": ["3"], "queryState": "..."}, "c0"]
]
```

## A JMAP-level error

Querying with an unsupported filter property returns an `error` triple, not
an HTTP error status - `GroupOfficeClient.batch()` raises `GroupOfficeError`
for this case:

```
POST /api/jmap.php  ->  200 OK
[["error", {"type": "unsupportedFilter", "message": "The filter 'entitytypeid' is not supported for entity 'LogEntry' by the server."}, "c0"]]
```

This is a real example found while building this server: GroupOffice's
`/api/doc.php` documents `LogEntry`/`Comment` as having an `entityTypeId`
*property*, but the working **query filter** is `entity` (a friendly name
like `"Contact"`) + `entityId`, not `entityTypeId`. Documented properties and
supported query filters are not always the same set - verified empirically
against a live instance, not assumed from the docs page alone.

## A blocked write (read-only mode, the default)

```python
from fastmcp import Client
from groupoffice_mcp_server.config import GroupOfficeConfig
from groupoffice_mcp_server.server import create_server

mcp = create_server(GroupOfficeConfig.from_env())  # GROUPOFFICE_READONLY unset -> True

async with Client(mcp) as c:
    result = await c.call_tool("delete_contact", {"contact_id": "3"})
```

No HTTP request is made at all - `ReadOnlyGuardMiddleware` intercepts the
call before it reaches the tool body, because `delete_contact`'s
`ToolAnnotations.read_only_hint` is `False`:

```json
{
  "error": true,
  "tool": "delete_contact",
  "message": "Tool 'delete_contact' is disabled: the server is running in read-only mode (default). Set GROUPOFFICE_READONLY=false to allow writes."
}
```

## The same call with writes enabled

```python
config = GroupOfficeConfig.from_env()
config = config.model_copy(update={"read_only": False})
mcp = create_server(config)

async with Client(mcp) as c:
    result = await c.call_tool("delete_contact", {"contact_id": "3"})
```

This now reaches the API and sends:

```
POST /api/jmap.php
[["Contact/set", {"destroy": ["3"]}, "c0"]]
```

with a response like:

```json
[["Contact/set", {"destroyed": ["3"], "notDestroyed": {}}, "c0"]]
```
