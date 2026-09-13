import base64
from typing import Any

import httpx

from .config import GroupOfficeConfig


class GroupOfficeError(Exception):
    """Raised for any GroupOffice API failure: transport, HTTP, or JMAP-level errors."""

    def __init__(self, message: str, *, status: int | None = None, details: Any = None):
        super().__init__(message)
        self.status = status
        self.details = details


class GroupOfficeClient:
    """Thin transport for GroupOffice's JMAP-style batch/RPC API.

    GroupOffice publishes no OpenAPI spec and no official client library in
    any language; its API is a JMAP-inspired (not spec-compliant JMAP, no
    `.well-known/jmap` discovery) JSON batch endpoint. Every entity follows
    the same `get`/`query`/`set` method convention, so this client only needs
    a handful of generic methods - adding support for a new entity later is
    just new `@mcp.tool` functions in server.py, not new client code.
    """

    def __init__(self, config: GroupOfficeConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self._http = httpx.Client(
            verify=config.verify_ssl,
            timeout=config.timeout,
            transport=transport or httpx.HTTPTransport(retries=config.max_retries),
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "GroupOfficeClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _headers(self, content_type: str = "application/json") -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_token}",
            "Content-Type": content_type,
        }

    def batch(self, calls: list[tuple[str, dict[str, Any]]]) -> list[dict[str, Any]]:
        """POST one JMAP batch request; returns each call's result params, in
        the same order as `calls`. Raises GroupOfficeError for transport
        failures or for any ["error", {...}, id] triple in the response."""
        body = [[method, params, f"c{i}"] for i, (method, params) in enumerate(calls)]
        try:
            resp = self._http.post(self.config.jmap_endpoint, json=body, headers=self._headers())
        except httpx.HTTPError as e:
            raise GroupOfficeError(f"GroupOffice request failed: {e}") from e

        if resp.status_code != 200:
            raise GroupOfficeError(
                f"GroupOffice returned HTTP {resp.status_code}",
                status=resp.status_code,
                details=resp.text[:2000],
            )
        try:
            triples = resp.json()
        except ValueError as e:
            raise GroupOfficeError(f"GroupOffice returned non-JSON response: {e}") from e

        by_id = {client_id: (method, result) for method, result, client_id in triples}
        ordered: list[dict[str, Any]] = []
        for i in range(len(calls)):
            method, result = by_id[f"c{i}"]
            if method == "error":
                raise GroupOfficeError(result.get("message", "Unknown JMAP error"), details=result)
            ordered.append(result)
        return ordered

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return self.batch([(method, params)])[0]

    def get(
        self,
        entity: str,
        ids: list[str] | None = None,
        properties: list[str] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        params = {
            k: v
            for k, v in {"ids": ids, "properties": properties, **extra}.items()
            if v is not None
        }
        return self.call(f"{entity}/get", params)

    def query(
        self,
        entity: str,
        filter: dict[str, Any] | None = None,
        sort: list[Any] | None = None,
        limit: int | None = None,
        position: int = 0,
        **extra: Any,
    ) -> dict[str, Any]:
        params = {
            k: v
            for k, v in {
                "filter": filter,
                "sort": sort,
                "limit": limit,
                "position": position,
                **extra,
            }.items()
            if v is not None
        }
        return self.call(f"{entity}/query", params)

    def query_and_get(
        self,
        entity: str,
        filter: dict[str, Any] | None = None,
        sort: list[Any] | None = None,
        limit: int | None = None,
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """One round trip: `Entity/query` then `Entity/get` via a JMAP
        back-reference. Returns the flat `list` of full records."""
        query_params = {
            k: v for k, v in {"filter": filter, "sort": sort, "limit": limit}.items() if v is not None
        }
        get_params: dict[str, Any] = {"#ids": {"resultOf": "c0", "path": "/ids"}}
        if properties is not None:
            get_params["properties"] = properties
        results = self.batch([(f"{entity}/query", query_params), (f"{entity}/get", get_params)])
        return results[1].get("list", [])

    def set(
        self,
        entity: str,
        create: dict[str, Any] | None = None,
        update: dict[str, Any] | None = None,
        destroy: list[str] | None = None,
    ) -> dict[str, Any]:
        params = {
            k: v
            for k, v in {"create": create, "update": update, "destroy": destroy}.items()
            if v is not None
        }
        return self.call(f"{entity}/set", params)

    def upload_blob(
        self, data: bytes, filename: str, content_type: str = "application/octet-stream"
    ) -> str:
        headers = self._headers(content_type)
        headers["X-File-Name"] = filename
        headers["Content-Length"] = str(len(data))
        try:
            resp = self._http.post(self.config.upload_endpoint, content=data, headers=headers)
        except httpx.HTTPError as e:
            raise GroupOfficeError(f"Blob upload failed: {e}") from e
        if resp.status_code != 200:
            raise GroupOfficeError(
                f"Blob upload returned HTTP {resp.status_code}", status=resp.status_code
            )
        return resp.json()["blobId"]

    def download_blob(self, blob_id: str) -> bytes:
        try:
            resp = self._http.get(
                self.config.download_endpoint,
                params={"blob": blob_id},
                headers=self._headers(),
            )
        except httpx.HTTPError as e:
            raise GroupOfficeError(f"Blob download failed: {e}") from e
        if resp.status_code != 200:
            raise GroupOfficeError(
                f"Blob download returned HTTP {resp.status_code}", status=resp.status_code
            )
        return resp.content

    def download_blob_base64(self, blob_id: str) -> dict[str, Any]:
        data = self.download_blob(blob_id)
        return {
            "blob_id": blob_id,
            "size": len(data),
            "base64_data": base64.b64encode(data).decode("ascii"),
        }

    @staticmethod
    def handle_api_error(error: GroupOfficeError, operation: str) -> dict[str, Any]:
        """Format a client-layer exception into a structured error dict so
        tool functions never let exceptions escape to the MCP layer."""
        return {
            "error": True,
            "operation": operation,
            "message": str(error),
            "status": error.status,
            "details": error.details,
        }
