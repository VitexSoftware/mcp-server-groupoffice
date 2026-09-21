import json

import httpx
import pytest

from groupoffice_mcp_server.client import GroupOfficeClient, GroupOfficeError
from groupoffice_mcp_server.config import GroupOfficeConfig


def make_client(handler) -> GroupOfficeClient:
    config = GroupOfficeConfig(url="https://go.example.com", api_token="tok")
    return GroupOfficeClient(config, transport=httpx.MockTransport(handler))


class TestBatch:
    def test_sends_bearer_auth_and_batch_body(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=[["Contact/get", {"list": []}, "c0"]])

        client = make_client(handler)
        client.batch([("Contact/get", {"ids": ["1"]})])

        assert captured["auth"] == "Bearer tok"
        assert captured["body"] == [["Contact/get", {"ids": ["1"]}, "c0"]]

    def test_matches_results_by_client_id_regardless_of_order(self):
        # Response triples arrive out of order (c1 before c0); batch() must
        # still map each result back to its call by clientId, not position.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json=[
                    ["Contact/get", {"list": [{"id": "1"}]}, "c1"],
                    ["Contact/query", {"ids": ["1"]}, "c0"],
                ],
            )

        client = make_client(handler)
        # call 0 (index c0) = Contact/query, call 1 (index c1) = Contact/get
        results = client.batch([("Contact/query", {}), ("Contact/get", {})])
        assert results == [{"ids": ["1"]}, {"list": [{"id": "1"}]}]

    def test_raises_on_error_triple(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json=[["error", {"type": "invalidArguments", "message": "bad"}, "c0"]]
            )

        client = make_client(handler)
        with pytest.raises(GroupOfficeError, match="bad"):
            client.batch([("Contact/get", {})])

    def test_raises_on_http_error_status(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="boom")

        client = make_client(handler)
        with pytest.raises(GroupOfficeError) as exc_info:
            client.batch([("Contact/get", {})])
        assert exc_info.value.status == 500

    def test_raises_on_transport_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused")

        client = make_client(handler)
        with pytest.raises(GroupOfficeError):
            client.batch([("Contact/get", {})])


class TestGetQuerySet:
    def test_get_omits_none_params(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=[["Contact/get", {}, "c0"]])

        client = make_client(handler)
        client.get("Contact", ids=["1"])
        assert captured["body"][0] == ["Contact/get", {"ids": ["1"]}, "c0"]

    def test_query_and_get_uses_back_reference(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json=[
                    ["Contact/query", {"ids": ["1", "2"]}, "c0"],
                    ["Contact/get", {"list": [{"id": "1"}, {"id": "2"}]}, "c1"],
                ],
            )

        client = make_client(handler)
        result = client.query_and_get("Contact", filter={"addressbookId": "1"}, limit=10)

        assert captured["body"][0] == [
            "Contact/query",
            {"filter": {"addressbookId": "1"}, "limit": 10},
            "c0",
        ]
        assert captured["body"][1] == [
            "Contact/get",
            {"#ids": {"resultOf": "c0", "path": "/ids"}},
            "c1",
        ]
        assert result == [{"id": "1"}, {"id": "2"}]

    def test_set_builds_create_update_destroy(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=[["Contact/set", {"created": {}}, "c0"]])

        client = make_client(handler)
        client.set("Contact", create={"new": {"firstName": "Jan"}})
        assert captured["body"][0] == [
            "Contact/set",
            {"create": {"new": {"firstName": "Jan"}}},
            "c0",
        ]


class TestBlobs:
    def test_upload_blob_sends_headers_and_returns_blob_id(self):
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = request.headers
            captured["content"] = request.content
            return httpx.Response(200, json={"blobId": "blob-123"})

        client = make_client(handler)
        blob_id = client.upload_blob(b"hello", "hello.txt", "text/plain")

        assert blob_id == "blob-123"
        assert captured["headers"]["X-File-Name"] == "hello.txt"
        assert captured["headers"]["Content-Type"] == "text/plain"
        assert captured["content"] == b"hello"

    def test_upload_blob_accepts_http_201(self):
        # Live GroupOffice (go.vitexsoftware.com) returns 201 Created.
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(201, json={"blobId": "blob-201"})

        client = make_client(handler)
        assert client.upload_blob(b"hello", "hello.txt") == "blob-201"

    def test_download_blob_base64_shape(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"hello")

        client = make_client(handler)
        result = client.download_blob_base64("blob-123")
        assert result["blob_id"] == "blob-123"
        assert result["size"] == 5
        import base64

        assert base64.b64decode(result["base64_data"]) == b"hello"


class TestHandleApiError:
    def test_shape(self):
        error = GroupOfficeError("boom", status=500, details={"x": 1})
        result = GroupOfficeClient.handle_api_error(error, "get_contact")
        assert result == {
            "error": True,
            "operation": "get_contact",
            "message": "boom",
            "status": 500,
            "details": {"x": 1},
        }
