import base64

from fastmcp import Client

from groupoffice_mcp_server.client import GroupOfficeClient, GroupOfficeError


async def call(server, name, args):
    async with Client(server) as c:
        return await c.call_tool(name, args)


class TestListToolErrorShape:
    """Every query_*/list_* tool declares -> list[dict[str, Any]]. FastMCP
    validates a tool's structured output against that schema, so the error
    branch must return the error dict wrapped in a list, not the bare dict -
    a bare dict fails schema validation and surfaces as an opaque client-side
    RuntimeError instead of a clean, catchable tool error. Caught by live
    testing against a real GroupOffice instance."""

    async def test_query_contacts_error_is_wrapped_in_a_list(self, server, mock_client):
        mock_client.query_and_get.side_effect = GroupOfficeError("boom", status=500)
        mock_client.handle_api_error.side_effect = GroupOfficeClient.handle_api_error
        result = await call(server, "query_contacts", {})
        assert result.is_error is False
        assert isinstance(result.data, list)
        assert result.data[0]["error"] is True
        assert result.data[0]["message"] == "boom"

    async def test_list_addressbooks_error_is_wrapped_in_a_list(self, server, mock_client):
        mock_client.query_and_get.side_effect = GroupOfficeError("boom", status=500)
        mock_client.handle_api_error.side_effect = GroupOfficeClient.handle_api_error
        result = await call(server, "list_addressbooks", {})
        assert result.is_error is False
        assert isinstance(result.data, list)
        assert result.data[0]["error"] is True


class TestAddressBookAndCalendarAndTaskListLists:
    async def test_list_addressbooks(self, server, mock_client):
        mock_client.query_and_get.return_value = [{"id": "1", "name": "Personal"}]
        result = await call(server, "list_addressbooks", {})
        mock_client.query_and_get.assert_called_once_with("AddressBook", limit=50)
        assert result.data == [{"id": "1", "name": "Personal"}]

    async def test_list_calendars(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "list_calendars", {"limit": 10})
        mock_client.query_and_get.assert_called_once_with("Calendar", limit=10)

    async def test_list_tasklists(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "list_tasklists", {})
        mock_client.query_and_get.assert_called_once_with("TaskList", limit=50)


class TestContact:
    async def test_query_contacts_merges_addressbook_id_into_filter(self, server, mock_client):
        mock_client.query_and_get.return_value = [{"id": "1"}]
        await call(server, "query_contacts", {"addressbook_id": "5", "limit": 20})
        mock_client.query_and_get.assert_called_once_with(
            "Contact", filter={"addressBookId": "5"}, limit=20, properties=None
        )

    async def test_query_contacts_without_addressbook_id_passes_none_filter(
        self, server, mock_client
    ):
        mock_client.query_and_get.return_value = []
        await call(server, "query_contacts", {})
        mock_client.query_and_get.assert_called_once_with(
            "Contact", filter=None, limit=50, properties=None
        )

    async def test_get_contact(self, server, mock_client):
        mock_client.get.return_value = {"list": [{"id": "1", "firstName": "Jan"}], "notFound": []}
        result = await call(server, "get_contact", {"contact_id": "1"})
        mock_client.get.assert_called_once_with("Contact", ids=["1"], properties=None)
        assert result.data["list"][0]["firstName"] == "Jan"

    async def test_create_contact(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        data = {"firstName": "Jan", "lastName": "Novak"}
        await call(writable_server, "create_contact", {"data": data})
        mock_client.set.assert_called_once_with("Contact", create={"new": data})

    async def test_update_contact(self, writable_server, mock_client):
        mock_client.set.return_value = {"updated": {"1": None}}
        await call(writable_server, "update_contact", {"contact_id": "1", "data": {"lastName": "X"}})
        mock_client.set.assert_called_once_with("Contact", update={"1": {"lastName": "X"}})

    async def test_delete_contact(self, writable_server, mock_client):
        mock_client.set.return_value = {"destroyed": ["1"]}
        await call(writable_server, "delete_contact", {"contact_id": "1"})
        mock_client.set.assert_called_once_with("Contact", destroy=["1"])


class TestCalendarEvent:
    async def test_query_calendar_events_merges_start_filter(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(
            server,
            "query_calendar_events",
            {"calendar_id": "1", "start": "2026-01-01"},
        )
        mock_client.query_and_get.assert_called_once_with(
            "CalendarEvent",
            filter={"calendarId": "1", "start": "2026-01-01"},
            limit=50,
            properties=None,
        )

    async def test_create_calendar_event(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        data = {"title": "Meeting", "start": "2026-01-01T10:00:00Z", "duration": "PT1H"}
        await call(writable_server, "create_calendar_event", {"data": data})
        mock_client.set.assert_called_once_with("CalendarEvent", create={"new": data})

    async def test_delete_calendar_event(self, writable_server, mock_client):
        mock_client.set.return_value = {"destroyed": ["1"]}
        await call(writable_server, "delete_calendar_event", {"event_id": "1"})
        mock_client.set.assert_called_once_with("CalendarEvent", destroy=["1"])


class TestTask:
    async def test_query_tasks_merges_tasklist_id(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_tasks", {"tasklist_id": "3"})
        mock_client.query_and_get.assert_called_once_with(
            "Task", filter={"tasklistId": "3"}, limit=50, properties=None
        )

    async def test_create_task(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        await call(writable_server, "create_task", {"data": {"name": "Do stuff"}})
        mock_client.set.assert_called_once_with("Task", create={"new": {"name": "Do stuff"}})


class TestNote:
    async def test_query_notes(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_notes", {})
        mock_client.query_and_get.assert_called_once_with(
            "Note", filter=None, limit=50, properties=None
        )

    async def test_create_and_delete_note(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        await call(writable_server, "create_note", {"data": {"title": "hi"}})
        mock_client.set.assert_called_with("Note", create={"new": {"title": "hi"}})

        mock_client.set.return_value = {"destroyed": ["1"]}
        await call(writable_server, "delete_note", {"note_id": "1"})
        mock_client.set.assert_called_with("Note", destroy=["1"])


class TestProject:
    async def test_query_projects(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_projects", {})
        mock_client.query_and_get.assert_called_once_with(
            "Project3", filter=None, limit=50, properties=None
        )

    async def test_create_project(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        await call(writable_server, "create_project", {"data": {"name": "New Project"}})
        mock_client.set.assert_called_once_with("Project3", create={"new": {"name": "New Project"}})


class TestComment:
    async def test_query_comments_builds_entity_filter(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_comments", {"entity": "Contact", "entity_id": "42"})
        mock_client.query_and_get.assert_called_once_with(
            "Comment", filter={"entity": "Contact", "entityId": "42"}, limit=50, properties=None
        )

    async def test_create_comment(self, writable_server, mock_client):
        mock_client.set.return_value = {"created": {"new": {"id": "1"}}}
        data = {"entity": "Contact", "entityId": "42", "text": "hello"}
        await call(writable_server, "create_comment", {"data": data})
        mock_client.set.assert_called_once_with("Comment", create={"new": data})


class TestHistory:
    async def test_query_history_builds_entity_filter(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_history", {"entity": "Contact", "entity_id": "42"})
        mock_client.query_and_get.assert_called_once_with(
            "LogEntry", filter={"entity": "Contact", "entityId": "42"}, limit=50, properties=None
        )


class TestUserAndGroup:
    async def test_query_users(self, server, mock_client):
        mock_client.query_and_get.return_value = []
        await call(server, "query_users", {})
        mock_client.query_and_get.assert_called_once_with(
            "User", filter=None, limit=50, properties=None
        )

    async def test_get_group(self, server, mock_client):
        mock_client.get.return_value = {"list": [{"id": "1"}], "notFound": []}
        await call(server, "get_group", {"group_id": "1"})
        mock_client.get.assert_called_once_with("Group", ids=["1"], properties=None)

    async def test_no_user_or_group_write_tools_exist(self, server):
        tools = await server.list_tools()
        names = {t.name for t in tools}
        for forbidden in (
            "create_user",
            "update_user",
            "delete_user",
            "create_group",
            "update_group",
            "delete_group",
        ):
            assert forbidden not in names


class TestFileBlob:
    async def test_upload_file_decodes_base64_and_calls_client(self, writable_server, mock_client):
        mock_client.upload_blob.return_value = "blob-123"
        content = base64.b64encode(b"hello world").decode("ascii")
        result = await call(
            writable_server,
            "upload_file",
            {"filename": "hello.txt", "content_base64": content, "content_type": "text/plain"},
        )
        mock_client.upload_blob.assert_called_once_with(b"hello world", "hello.txt", "text/plain")
        assert result.data["blob_id"] == "blob-123"
        assert result.data["size"] == 11

    async def test_download_file(self, server, mock_client):
        mock_client.download_blob_base64.return_value = {
            "blob_id": "blob-123",
            "size": 5,
            "base64_data": base64.b64encode(b"hello").decode("ascii"),
        }
        result = await call(server, "download_file", {"blob_id": "blob-123"})
        mock_client.download_blob_base64.assert_called_once_with("blob-123")
        assert result.data["blob_id"] == "blob-123"
