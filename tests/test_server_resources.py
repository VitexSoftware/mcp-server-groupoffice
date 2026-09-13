import json

from fastmcp import Client


class TestResources:
    async def test_lists_all_resources(self, server):
        async with Client(server) as c:
            resources = await c.list_resources()
        uris = {str(r.uri) for r in resources}
        assert uris == {
            "groupoffice://addressbooks",
            "groupoffice://calendars",
            "groupoffice://tasklists",
            "groupoffice://entities",
        }

    async def test_read_addressbooks_resource(self, server, mock_client):
        mock_client.query_and_get.return_value = [{"id": "1", "name": "Personal"}]
        async with Client(server) as c:
            result = await c.read_resource("groupoffice://addressbooks")
        data = json.loads(result[0].text)
        assert data == [{"id": "1", "name": "Personal"}]
        mock_client.query_and_get.assert_called_once_with("AddressBook", limit=200)

    async def test_read_entities_resource_is_static(self, server):
        async with Client(server) as c:
            result = await c.read_resource("groupoffice://entities")
        data = json.loads(result[0].text)
        assert "Contact" in data
        assert data["Contact"]["read_only"] is False
        assert data["User"]["read_only"] is True
