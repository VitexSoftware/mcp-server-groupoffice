import base64
import json
import logging
from typing import Any

from fastmcp import FastMCP

from . import __version__
from .annotations import CREATE_ANNOTATIONS, MUTATE_ANNOTATIONS, READ_ONLY_ANNOTATIONS
from .client import GroupOfficeClient, GroupOfficeError
from .config import GroupOfficeConfig
from .middleware import ReadOnlyGuardMiddleware

logger = logging.getLogger(__name__)

# Tools that create/modify/delete GroupOffice state. Blocked by
# ReadOnlyGuardMiddleware whenever config.read_only is true (the default).
# This set is not itself the enforcement mechanism (the middleware enforces
# based on each tool's annotations.read_only_hint) - it exists so a
# consistency test can catch a tool whose annotation and actual behavior
# have drifted apart. See tests/test_middleware.py.
MUTATING_TOOLS = {
    "create_contact",
    "update_contact",
    "delete_contact",
    "create_calendar_event",
    "update_calendar_event",
    "delete_calendar_event",
    "create_task",
    "update_task",
    "delete_task",
    "create_note",
    "update_note",
    "delete_note",
    "create_project",
    "update_project",
    "delete_project",
    "create_comment",
    "update_comment",
    "delete_comment",
    "upload_file",
}

# Static, hand-maintained registry describing the entities/operations this
# server exposes. Deliberately NOT introspected from a live instance's
# /api/doc.php: that page is per-instance HTML (varies with installed
# modules), not a stable, machine-readable contract.
SUPPORTED_ENTITIES = {
    "AddressBook": {"operations": ["query", "get"], "read_only": True},
    "Contact": {"operations": ["query", "get", "create", "update", "delete"], "read_only": False},
    "Calendar": {"operations": ["query", "get"], "read_only": True},
    "CalendarEvent": {
        "operations": ["query", "get", "create", "update", "delete"],
        "read_only": False,
    },
    "TaskList": {"operations": ["query", "get"], "read_only": True},
    "Task": {"operations": ["query", "get", "create", "update", "delete"], "read_only": False},
    "Note": {"operations": ["query", "get", "create", "update", "delete"], "read_only": False},
    "Project3": {
        "operations": ["query", "get", "create", "update", "delete"],
        "read_only": False,
    },
    "Comment": {"operations": ["query", "get", "create", "update", "delete"], "read_only": False},
    "History": {"operations": ["query"], "read_only": True},
    "User": {"operations": ["query", "get"], "read_only": True},
    "Group": {"operations": ["query", "get"], "read_only": True},
    "Blob": {"operations": ["upload", "download"], "read_only": False},
}


def create_server(config: GroupOfficeConfig, client: GroupOfficeClient | None = None) -> FastMCP:
    """Build a GroupOffice MCP server bound to `config`/`client`.

    A factory (rather than a module-level singleton) so tests can inject a
    mocked client and a specific read_only value without env vars or
    monkeypatching, and so multiple independent server instances can coexist
    in the same process.
    """
    client = client or GroupOfficeClient(config)

    mcp: FastMCP = FastMCP(
        "groupoffice-mcp-server",
        version=__version__,
        instructions=(
            "MCP server for GroupOffice groupware. Defaults to read-only: "
            "mutating tools are rejected unless GROUPOFFICE_READONLY=false. "
            "Prefer query_*/get_*/list_* tools to inspect current state "
            "before calling create_*/update_*/delete_* tools."
        ),
        middleware=[ReadOnlyGuardMiddleware(config)],
    )

    # ---------------------------------------------------------------- AddressBook

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def list_addressbooks(limit: int = 50) -> list[dict[str, Any]]:
        """List available address books."""
        try:
            return client.query_and_get("AddressBook", limit=limit)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "list_addressbooks")

    # -------------------------------------------------------------------- Contact

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_contacts(
        addressbook_id: str | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search contacts. `addressbook_id` is merged into the filter as
        GroupOffice's `addressBookId` property (confirmed against a live
        instance's /api/doc.php); pass a raw `filter` dict for anything else."""
        f = dict(filter or {})
        if addressbook_id is not None:
            f["addressBookId"] = addressbook_id
        try:
            return client.query_and_get("Contact", filter=f or None, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_contacts")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_contact(contact_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Contact by ID."""
        try:
            return client.get("Contact", ids=[contact_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_contact")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_contact(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Contact. `data` follows GroupOffice's Contact/set
        create schema (e.g. firstName, lastName, emailAddresses, addressBookId)."""
        try:
            return client.set("Contact", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_contact")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_contact(contact_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing Contact."""
        try:
            return client.set("Contact", update={contact_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_contact")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_contact(contact_id: str) -> dict[str, Any]:
        """Delete a Contact by ID."""
        try:
            return client.set("Contact", destroy=[contact_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_contact")

    # ------------------------------------------------------------------- Calendar

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def list_calendars(limit: int = 50) -> list[dict[str, Any]]:
        """List available calendars."""
        try:
            return client.query_and_get("Calendar", limit=limit)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "list_calendars")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_calendar_events(
        calendar_id: str | None = None,
        start: str | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search calendar events. `calendar_id`/`start` are merged into the
        filter as GroupOffice's confirmed `calendarId`/`start` properties.
        Note: CalendarEvent has no `end` property - event length is a
        `duration` (ISO 8601 duration string, e.g. "PT1H") relative to
        `start`, not a separate end timestamp. Query-time range filtering
        (e.g. "events between two dates") is not documented as a stable
        filter contract - check your instance's /api/doc.php, or fetch a
        broader result set and filter by start/duration client-side."""
        f = dict(filter or {})
        if calendar_id is not None:
            f["calendarId"] = calendar_id
        if start is not None:
            f["start"] = start
        try:
            return client.query_and_get(
                "CalendarEvent", filter=f or None, limit=limit, properties=properties
            )
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_calendar_events")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_calendar_event(event_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single CalendarEvent by ID."""
        try:
            return client.get("CalendarEvent", ids=[event_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_calendar_event")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_calendar_event(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new CalendarEvent. `data` follows GroupOffice's
        CalendarEvent/set create schema (e.g. title, start, duration, calendarId -
        note "duration" not "end", e.g. duration="PT1H" for a 1-hour event)."""
        try:
            return client.set("CalendarEvent", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_calendar_event")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_calendar_event(event_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing CalendarEvent."""
        try:
            return client.set("CalendarEvent", update={event_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_calendar_event")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_calendar_event(event_id: str) -> dict[str, Any]:
        """Delete a CalendarEvent by ID."""
        try:
            return client.set("CalendarEvent", destroy=[event_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_calendar_event")

    # ------------------------------------------------------------------- TaskList

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def list_tasklists(limit: int = 50) -> list[dict[str, Any]]:
        """List available task lists."""
        try:
            return client.query_and_get("TaskList", limit=limit)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "list_tasklists")

    # ------------------------------------------------------------------------ Task

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_tasks(
        tasklist_id: str | None = None,
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search tasks. `tasklist_id` is merged into the filter as
        GroupOffice's confirmed `tasklistId` property (lowercase "l" -
        not `taskListId`). Completion is tracked via the `percentComplete`
        property (0-100), not a boolean `completed` field - pass
        `filter={"percentComplete": 100}` yourself if your instance's query
        supports filtering on it."""
        f = dict(filter or {})
        if tasklist_id is not None:
            f["tasklistId"] = tasklist_id
        try:
            return client.query_and_get("Task", filter=f or None, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_tasks")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_task(task_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Task by ID."""
        try:
            return client.get("Task", ids=[task_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_task")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_task(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Task. `data` follows GroupOffice's Task/set create
        schema (e.g. title, due, tasklistId, responsibleUserId, priority)."""
        try:
            return client.set("Task", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_task")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_task(task_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing Task."""
        try:
            return client.set("Task", update={task_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_task")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_task(task_id: str) -> dict[str, Any]:
        """Delete a Task by ID."""
        try:
            return client.set("Task", destroy=[task_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_task")

    # ------------------------------------------------------------------------ Note

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_notes(
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search notes."""
        try:
            return client.query_and_get("Note", filter=filter, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_notes")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_note(note_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Note by ID."""
        try:
            return client.get("Note", ids=[note_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_note")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_note(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Note. `data` follows GroupOffice's Note/set create schema."""
        try:
            return client.set("Note", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_note")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_note(note_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing Note."""
        try:
            return client.set("Note", update={note_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_note")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_note(note_id: str) -> dict[str, Any]:
        """Delete a Note by ID."""
        try:
            return client.set("Note", destroy=[note_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_note")

    # -------------------------------------------------------------------- Project3

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_projects(
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search projects (GroupOffice Projects v3 module, entity Project3).
        Note: this module is optional - it returns an error on instances
        where it isn't installed. Check your instance's /api/doc.php."""
        try:
            return client.query_and_get("Project3", filter=filter, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_projects")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_project(project_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Project3 record by ID."""
        try:
            return client.get("Project3", ids=[project_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_project")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_project(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new project. `data` follows GroupOffice's Project3/set
        create schema (e.g. name, description)."""
        try:
            return client.set("Project3", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_project")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_project(project_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing project."""
        try:
            return client.set("Project3", update={project_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_project")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_project(project_id: str) -> dict[str, Any]:
        """Delete a project by ID."""
        try:
            return client.set("Project3", destroy=[project_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_project")

    # --------------------------------------------------------------------- Comment

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_comments(
        entity_type_id: int,
        entity_id: str,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List comments attached to a record, filtered by GroupOffice's
        confirmed `entityTypeId` (int)/`entityId` properties. `entityTypeId`
        is an internal numeric type ID, not a friendly name like "Contact" -
        GroupOffice does not document a public name-to-ID lookup table; find
        it by inspecting the `entityTypeId` field on an existing Comment/
        LogEntry record for the record type you care about, or via your
        instance's /api/doc.php."""
        f = {"entityTypeId": entity_type_id, "entityId": entity_id}
        try:
            return client.query_and_get("Comment", filter=f, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_comments")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_comment(comment_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Comment by ID."""
        try:
            return client.get("Comment", ids=[comment_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_comment")

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def create_comment(data: dict[str, Any]) -> dict[str, Any]:
        """Create a new Comment. `data` follows GroupOffice's Comment/set
        create schema (e.g. entityTypeId, entityId, text)."""
        try:
            return client.set("Comment", create={"new": data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "create_comment")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def update_comment(comment_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Update fields on an existing Comment."""
        try:
            return client.set("Comment", update={comment_id: data})
        except GroupOfficeError as e:
            return client.handle_api_error(e, "update_comment")

    @mcp.tool(annotations=MUTATE_ANNOTATIONS)
    def delete_comment(comment_id: str) -> dict[str, Any]:
        """Delete a Comment by ID."""
        try:
            return client.set("Comment", destroy=[comment_id])
        except GroupOfficeError as e:
            return client.handle_api_error(e, "delete_comment")

    # --------------------------------------------------------------------- History

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_history(
        entity_type_id: int,
        entity_id: str,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """List audit-log entries for a record. GroupOffice's history/audit
        entity is actually named `LogEntry` (not "History"), filtered by its
        confirmed `entityTypeId` (int)/`entityId` properties - see
        `query_comments` for how to find `entity_type_id`. Read-only and
        generated automatically by GroupOffice; there are no
        create/update/delete tools for it."""
        f = {"entityTypeId": entity_type_id, "entityId": entity_id}
        try:
            return client.query_and_get("LogEntry", filter=f, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_history")

    # ------------------------------------------------------------------------ User

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_users(
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search users. Read-only: user administration (create/update/delete)
        is deliberately not exposed by this server - it is high-privilege and
        out of scope."""
        try:
            return client.query_and_get("User", filter=filter, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_users")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_user(user_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single User by ID."""
        try:
            return client.get("User", ids=[user_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_user")

    # ----------------------------------------------------------------------- Group

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def query_groups(
        filter: dict[str, Any] | None = None,
        limit: int = 50,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search groups. Read-only: group administration is out of scope."""
        try:
            return client.query_and_get("Group", filter=filter, limit=limit, properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "query_groups")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def get_group(group_id: str, properties: list[str] | None = None) -> dict[str, Any]:
        """Get a single Group by ID."""
        try:
            return client.get("Group", ids=[group_id], properties=properties)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "get_group")

    # ------------------------------------------------------------------ File/blob

    @mcp.tool(annotations=CREATE_ANNOTATIONS)
    def upload_file(
        filename: str, content_base64: str, content_type: str = "application/octet-stream"
    ) -> dict[str, Any]:
        """Upload a file as a GroupOffice blob. `content_base64` is the raw
        file content, base64-encoded. Returns a `blob_id` to attach to
        another entity's create/update `data` (e.g. a Contact photo or a
        CalendarEvent/Note attachment field)."""
        try:
            data = base64.b64decode(content_base64)
            blob_id = client.upload_blob(data, filename, content_type)
            return {"blob_id": blob_id, "filename": filename, "size": len(data)}
        except GroupOfficeError as e:
            return client.handle_api_error(e, "upload_file")

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS)
    def download_file(blob_id: str) -> dict[str, Any]:
        """Download a GroupOffice blob by ID. Returns base64-encoded content;
        large files will produce a large response (base64 inflates size by
        ~33%) - prefer this only for reasonably small attachments."""
        try:
            return client.download_blob_base64(blob_id)
        except GroupOfficeError as e:
            return client.handle_api_error(e, "download_file")

    # ------------------------------------------------------------------- Resources

    @mcp.resource("groupoffice://addressbooks")
    def addressbooks_resource() -> str:
        """Browsable list of address books."""
        try:
            data = client.query_and_get("AddressBook", limit=200)
        except GroupOfficeError as e:
            data = client.handle_api_error(e, "addressbooks_resource")
        return json.dumps(data, indent=2)

    @mcp.resource("groupoffice://calendars")
    def calendars_resource() -> str:
        """Browsable list of calendars."""
        try:
            data = client.query_and_get("Calendar", limit=200)
        except GroupOfficeError as e:
            data = client.handle_api_error(e, "calendars_resource")
        return json.dumps(data, indent=2)

    @mcp.resource("groupoffice://tasklists")
    def tasklists_resource() -> str:
        """Browsable list of task lists."""
        try:
            data = client.query_and_get("TaskList", limit=200)
        except GroupOfficeError as e:
            data = client.handle_api_error(e, "tasklists_resource")
        return json.dumps(data, indent=2)

    @mcp.resource("groupoffice://entities")
    def entities_resource() -> str:
        """Static registry of entities/operations this server exposes."""
        return json.dumps(SUPPORTED_ENTITIES, indent=2)

    # --------------------------------------------------------------------- Prompts

    @mcp.prompt
    def daily_briefing(date: str | None = None) -> str:
        """Summarize today's calendar events and open tasks."""
        target = date or "today"
        return (
            f"Give me a daily briefing for {target}. First call `query_calendar_events` "
            f"for that date's window, then call `query_tasks` with completed=false. "
            "Summarize both lists concisely, highlighting anything time-sensitive."
        )

    @mcp.prompt
    def contact_lookup(query: str) -> str:
        """Look up contacts before ever creating a new one, to avoid duplicates."""
        return (
            f"Search for existing contacts matching '{query}' using `query_contacts` "
            "(pass query as part of a `filter` dict, or narrow by `addressbook_id` if "
            "known). Show me the matches. Only suggest `create_contact` if there is "
            "clearly no existing match - never create a duplicate."
        )

    @mcp.prompt
    def schedule_event_safely(
        title: str, start: str, end: str, calendar_id: str | None = None
    ) -> str:
        """Check for conflicts before scheduling a new calendar event."""
        return (
            f"I want to schedule '{title}' from {start} to {end}"
            + (f" on calendar {calendar_id}" if calendar_id else "")
            + ". First call `query_calendar_events` with that time window to check for "
            "conflicts. Report any overlapping events. Only call "
            "`create_calendar_event` after confirming there is no conflict, or after "
            "I explicitly say to proceed anyway."
        )

    return mcp


def main() -> None:
    config = GroupOfficeConfig.from_env()
    logging.basicConfig(level=logging.DEBUG if config.debug else logging.INFO)
    logger.info(
        "Read-only mode: %s", "enabled" if config.read_only else "DISABLED (writes allowed)"
    )
    mcp = create_server(config)
    mcp.run()


if __name__ == "__main__":
    main()
