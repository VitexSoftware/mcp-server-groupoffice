#!/usr/bin/env python3
"""Live capability scenario for GroupOffice MCP Server.

Exercises every registered MCP tool against a real GroupOffice instance:
read tools must return usable data; mutating tools must be blocked when
GROUPOFFICE_READONLY is enabled (the default). With ``--allow-writes``,
create/update/delete cycles run against the live instance.

Usage:
  export GROUPOFFICE_URL=https://go.vitexsoftware.com
  export GROUPOFFICE_API_TOKEN=...
  export GROUPOFFICE_READONLY=true
  python tests/live_capability_scenario.py --json-out /tmp/go-live.json

  # Non-production only — creates and mutates records:
  python tests/live_capability_scenario.py --allow-writes --json-out /tmp/go-write.json

Exit code is 0 only when every non-skipped check passes.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))

from fastmcp import Client  # noqa: E402

from groupoffice_mcp_server.config import GroupOfficeConfig  # noqa: E402
from groupoffice_mcp_server.server import create_server  # noqa: E402


@dataclass
class CheckResult:
    name: str
    kind: str
    ok: bool
    detail: str = ""
    sample: Any = None
    skipped: bool = False


@dataclass
class ScenarioReport:
    url: str
    results: List[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        self.results.append(result)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.ok and not r.skipped)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.ok and not r.skipped)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.skipped)


def _tool_is_readonly(tool: Any) -> bool:
    ann = getattr(tool, "annotations", None)
    if ann is None:
        return True
    if hasattr(ann, "read_only_hint"):
        return bool(ann.read_only_hint)
    if hasattr(ann, "readOnlyHint"):
        return bool(ann.readOnlyHint)
    return True


def _usable(data: Any) -> tuple[bool, str]:
    if data is None:
        return False, "null"
    if isinstance(data, dict) and data.get("error") is True:
        return False, str(data.get("message") or data)[:300]
    if isinstance(data, list):
        if data and isinstance(data[0], dict) and data[0].get("error") is True:
            return False, str(data[0].get("message") or data[0])[:300]
        return True, f"list len={len(data)}" + (" (empty ok)" if not data else "")
    if isinstance(data, dict):
        # JMAP get shape: require list non-empty or explicit notFound empty with list
        if "list" in data and "notFound" in data:
            lst = data.get("list") or []
            nf = data.get("notFound") or []
            if lst:
                return True, f"jmap get list={len(lst)}"
            if nf:
                return False, f"jmap notFound={nf}"
            return True, "jmap get empty list"
        # set() shape
        if "notCreated" in data and data.get("notCreated"):
            return False, f"notCreated={data['notCreated']}"
        if "notUpdated" in data and data.get("notUpdated"):
            return False, f"notUpdated={data['notUpdated']}"
        if "notDestroyed" in data and data.get("notDestroyed"):
            return False, f"notDestroyed={data['notDestroyed']}"
        return True, f"keys={list(data.keys())[:8]}"
    if isinstance(data, str):
        return (bool(data.strip()), "empty string" if not data.strip() else "ok string")
    return True, f"type={type(data).__name__}"


def _created_id(data: Any) -> Optional[str]:
    if not isinstance(data, dict):
        return None
    created = data.get("created") or {}
    if isinstance(created, dict) and created:
        first = next(iter(created.values()))
        if isinstance(first, dict) and first.get("id") is not None:
            return str(first["id"])
    return None


async def _call(server: Any, name: str, args: Optional[dict] = None) -> Any:
    async with Client(server) as client:
        result = await client.call_tool(name, args or {})
        if result.is_error:
            raise RuntimeError(str(result.content or result))
        return result.data


async def run_scenario(*, read_only: bool) -> ScenarioReport:
    os.environ["GROUPOFFICE_READONLY"] = "true" if read_only else "false"
    config = GroupOfficeConfig.from_env()
    server = create_server(config)
    report = ScenarioReport(url=config.url)

    tools = await server.list_tools()
    report.add(
        CheckResult(
            name="tool_catalog",
            kind="meta",
            ok=len(tools) > 0,
            detail=f"{len(tools)} tools registered; read_only={config.read_only}",
        )
    )
    report.add(
        CheckResult(
            name="read_only_flag",
            kind="meta",
            ok=config.read_only is read_only,
            detail=f"config.read_only={config.read_only} expected={read_only}",
        )
    )

    contact_id = None
    event_id = None
    task_id = None
    note_id = None
    addressbook_id = None
    calendar_id = None
    tasklist_id = None
    notebook_id = None

    listish = [
        ("list_addressbooks", {}),
        ("list_calendars", {}),
        ("list_tasklists", {}),
        ("list_notebooks", {}),
        ("query_contacts", {"limit": 5}),
        ("query_calendar_events", {"limit": 5}),
        ("query_tasks", {"limit": 5}),
        ("query_notes", {"limit": 5}),
        ("query_users", {"limit": 5}),
        ("query_groups", {"limit": 5}),
    ]
    optional_list = [("query_projects", {"limit": 5})]

    for name, args in listish:
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            report.add(CheckResult(name=name, kind="tool", ok=ok, detail=detail, sample=str(data)[:400]))
            if name == "list_addressbooks" and isinstance(data, list) and data:
                addressbook_id = data[0].get("id")
            if name == "list_calendars" and isinstance(data, list) and data:
                calendar_id = data[0].get("id")
            if name == "list_tasklists" and isinstance(data, list) and data:
                tasklist_id = data[0].get("id")
            if name == "list_notebooks" and isinstance(data, list) and data:
                notebook_id = data[0].get("id")
            if name == "query_contacts" and isinstance(data, list) and data and isinstance(data[0], dict):
                contact_id = data[0].get("id")
            if name == "query_calendar_events" and isinstance(data, list) and data and isinstance(data[0], dict):
                event_id = data[0].get("id")
            if name == "query_tasks" and isinstance(data, list) and data and isinstance(data[0], dict):
                task_id = data[0].get("id")
            if name == "query_notes" and isinstance(data, list) and data and isinstance(data[0], dict):
                note_id = data[0].get("id")
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(
                    name=name,
                    kind="tool",
                    ok=False,
                    detail=f"{type(exc).__name__}: {exc}",
                    sample=traceback.format_exc()[-500:],
                )
            )

    for name, args in optional_list:
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            if not ok and any(x in detail.lower() for x in ("not found", "forbidden", "permission", "unknown")):
                report.add(CheckResult(name=name, kind="tool", ok=True, detail=detail, skipped=True))
            else:
                report.add(CheckResult(name=name, kind="tool", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            msg = str(exc).lower()
            if any(x in msg for x in ("not found", "forbidden", "permission", "unknown", "project")):
                report.add(
                    CheckResult(
                        name=name,
                        kind="tool",
                        ok=True,
                        detail=f"optional module: {exc}",
                        skipped=True,
                    )
                )
            else:
                report.add(
                    CheckResult(name=name, kind="tool", ok=False, detail=f"{type(exc).__name__}: {exc}")
                )

    # Comments / history require entity + entity_id (verified live: filter by
    # friendly entity name works; bare limit-only calls fail validation).
    scoped = [
        ("query_comments", {"entity": "Contact", "entity_id": str(contact_id or "1"), "limit": 5}),
        ("query_history", {"entity": "Contact", "entity_id": str(contact_id or "1"), "limit": 5}),
    ]
    for name, args in scoped:
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            report.add(CheckResult(name=name, kind="tool", ok=ok, detail=detail, sample=str(data)[:400]))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name=name, kind="tool", ok=False, detail=f"{type(exc).__name__}: {exc}")
            )

    id_gets = [
        ("get_contact", {"contact_id": str(contact_id)}, contact_id),
        ("get_calendar_event", {"event_id": str(event_id)}, event_id),
        ("get_task", {"task_id": str(task_id)}, task_id),
        ("get_note", {"note_id": str(note_id)}, note_id),
    ]
    for name, args, needed in id_gets:
        if not needed:
            report.add(
                CheckResult(
                    name=name,
                    kind="tool",
                    ok=True,
                    detail="no id available from list/query",
                    skipped=True,
                )
            )
            continue
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            report.add(CheckResult(name=name, kind="tool", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(CheckResult(name=name, kind="tool", ok=False, detail=f"{type(exc).__name__}: {exc}"))

    covered = {r.name for r in report.results if r.kind == "tool"}
    for t in tools:
        if not _tool_is_readonly(t) or t.name in covered:
            continue
        report.add(
            CheckResult(
                name=t.name,
                kind="tool",
                ok=True,
                detail="no default-args probe (resource/id-specific)",
                skipped=True,
            )
        )

    if read_only:
        sample_writes = [
            ("create_contact", {"data": {"firstName": "MCP", "lastName": "Test"}}),
            ("delete_contact", {"contact_id": "1"}),
            ("create_note", {"data": {"name": "mcp-live-test"}}),
        ]
        for name, args in sample_writes:
            try:
                data = await _call(server, name, args)
                refused = isinstance(data, dict) and (
                    data.get("error") or "read-only" in str(data).lower()
                )
                report.add(
                    CheckResult(
                        name=f"readonly_guard:{name}",
                        kind="guard",
                        ok=refused,
                        detail="write returned without refusal" if not refused else "refused in payload",
                        sample=str(data)[:300],
                    )
                )
            except Exception as exc:  # noqa: BLE001
                ok = "read-only" in str(exc).lower() or "readonly" in str(exc).lower()
                report.add(
                    CheckResult(
                        name=f"readonly_guard:{name}",
                        kind="guard",
                        ok=ok,
                        detail=str(exc)[:300],
                    )
                )

        for t in tools:
            if _tool_is_readonly(t):
                continue
            report.add(
                CheckResult(
                    name=f"catalog:{t.name}",
                    kind="meta",
                    ok=True,
                    detail="write tool registered (guard-sampled separately)",
                )
            )
    else:
        await _run_write_cycle(
            server,
            report,
            addressbook_id=addressbook_id,
            calendar_id=calendar_id,
            tasklist_id=tasklist_id,
            notebook_id=notebook_id,
        )

    return report


async def _run_write_cycle(
    server: Any,
    report: ScenarioReport,
    *,
    addressbook_id: Any,
    calendar_id: Any,
    tasklist_id: Any,
    notebook_id: Any,
) -> None:
    """Create / update / delete across entities on a non-production instance."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    created_contact = None
    created_task = None
    created_note = None
    created_event = None
    created_comment = None
    blob_id = None

    # Ensure calendar exists (fresh installs may have none)
    if not calendar_id:
        try:
            # No create_calendar tool — use raw client via create path not available;
            # fall back: skip events if we cannot discover a calendar.
            report.add(
                CheckResult(
                    name="write:ensure_calendar",
                    kind="write",
                    ok=True,
                    detail="no calendar; skipping event writes",
                    skipped=True,
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(
                    name="write:ensure_calendar",
                    kind="write",
                    ok=False,
                    detail=str(exc)[:300],
                )
            )

    # Contact create → update → get → comment → history
    try:
        data = await _call(
            server,
            "create_contact",
            {
                "data": {
                    "addressBookId": str(addressbook_id or "1"),
                    "firstName": "MCP",
                    "lastName": f"Write-{stamp}",
                    "emailAddresses": [{"type": "work", "email": f"mcp-{stamp}@example.com"}],
                }
            },
        )
        ok, detail = _usable(data)
        created_contact = _created_id(data)
        report.add(
            CheckResult(
                name="write:create_contact",
                kind="write",
                ok=ok and bool(created_contact),
                detail=detail if ok else detail,
                sample=str(data)[:400],
            )
        )
    except Exception as exc:  # noqa: BLE001
        report.add(
            CheckResult(name="write:create_contact", kind="write", ok=False, detail=str(exc)[:300])
        )

    if created_contact:
        try:
            data = await _call(
                server,
                "update_contact",
                {"contact_id": created_contact, "data": {"jobTitle": "MCP Live Tester"}},
            )
            ok, detail = _usable(data)
            report.add(CheckResult(name="write:update_contact", kind="write", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:update_contact", kind="write", ok=False, detail=str(exc)[:300])
            )

        try:
            data = await _call(server, "get_contact", {"contact_id": created_contact})
            ok, detail = _usable(data)
            report.add(CheckResult(name="write:get_contact", kind="write", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:get_contact", kind="write", ok=False, detail=str(exc)[:300])
            )

        try:
            data = await _call(
                server,
                "create_comment",
                {
                    "data": {
                        "entity": "Contact",
                        "entityId": created_contact,
                        "text": f"MCP live comment {stamp}",
                    }
                },
            )
            ok, detail = _usable(data)
            created_comment = _created_id(data)
            report.add(
                CheckResult(
                    name="write:create_comment",
                    kind="write",
                    ok=ok and bool(created_comment),
                    detail=detail,
                    sample=str(data)[:400],
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:create_comment", kind="write", ok=False, detail=str(exc)[:300])
            )

        try:
            data = await _call(
                server,
                "query_history",
                {"entity": "Contact", "entity_id": created_contact, "limit": 5},
            )
            ok, detail = _usable(data)
            report.add(CheckResult(name="write:query_history", kind="write", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:query_history", kind="write", ok=False, detail=str(exc)[:300])
            )

    # Task
    if tasklist_id:
        try:
            data = await _call(
                server,
                "create_task",
                {
                    "data": {
                        "tasklistId": str(tasklist_id),
                        "title": f"MCP task {stamp}",
                        "percentComplete": 0,
                    }
                },
            )
            ok, detail = _usable(data)
            created_task = _created_id(data)
            report.add(
                CheckResult(
                    name="write:create_task",
                    kind="write",
                    ok=ok and bool(created_task),
                    detail=detail,
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:create_task", kind="write", ok=False, detail=str(exc)[:300])
            )
        if created_task:
            try:
                data = await _call(
                    server,
                    "update_task",
                    {"task_id": created_task, "data": {"percentComplete": 50}},
                )
                ok, detail = _usable(data)
                report.add(CheckResult(name="write:update_task", kind="write", ok=ok, detail=detail))
            except Exception as exc:  # noqa: BLE001
                report.add(
                    CheckResult(name="write:update_task", kind="write", ok=False, detail=str(exc)[:300])
                )
    else:
        report.add(
            CheckResult(
                name="write:create_task",
                kind="write",
                ok=True,
                detail="no tasklist",
                skipped=True,
            )
        )

    # Note
    if notebook_id:
        try:
            data = await _call(
                server,
                "create_note",
                {
                    "data": {
                        "noteBookId": str(notebook_id),
                        "name": f"MCP note {stamp}",
                        "content": "live write cycle",
                    }
                },
            )
            ok, detail = _usable(data)
            created_note = _created_id(data)
            report.add(
                CheckResult(
                    name="write:create_note",
                    kind="write",
                    ok=ok and bool(created_note),
                    detail=detail,
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:create_note", kind="write", ok=False, detail=str(exc)[:300])
            )
    else:
        report.add(
            CheckResult(
                name="write:create_note",
                kind="write",
                ok=True,
                detail="no notebook",
                skipped=True,
            )
        )

    # Calendar event
    if calendar_id:
        start = (datetime.now(timezone.utc) + timedelta(days=1)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        try:
            data = await _call(
                server,
                "create_calendar_event",
                {
                    "data": {
                        "calendarId": str(calendar_id),
                        "title": f"MCP event {stamp}",
                        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "duration": "PT1H",
                    }
                },
            )
            ok, detail = _usable(data)
            created_event = _created_id(data)
            report.add(
                CheckResult(
                    name="write:create_calendar_event",
                    kind="write",
                    ok=ok and bool(created_event),
                    detail=detail,
                )
            )
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(
                    name="write:create_calendar_event",
                    kind="write",
                    ok=False,
                    detail=str(exc)[:300],
                )
            )
    else:
        report.add(
            CheckResult(
                name="write:create_calendar_event",
                kind="write",
                ok=True,
                detail="no calendar",
                skipped=True,
            )
        )

    # Blob upload + download
    try:
        payload = base64.b64encode(f"mcp-live-{stamp}".encode()).decode()
        data = await _call(
            server,
            "upload_file",
            {
                "filename": f"mcp-live-{stamp}.txt",
                "content_base64": payload,
                "content_type": "text/plain",
            },
        )
        ok, detail = _usable(data)
        if isinstance(data, dict):
            blob_id = data.get("blob_id") or data.get("blobId")
        report.add(
            CheckResult(
                name="write:upload_file",
                kind="write",
                ok=ok and bool(blob_id),
                detail=detail if blob_id else f"no blob id in {data!r}"[:300],
                sample=str(data)[:400],
            )
        )
    except Exception as exc:  # noqa: BLE001
        report.add(
            CheckResult(name="write:upload_file", kind="write", ok=False, detail=str(exc)[:300])
        )

    if blob_id:
        try:
            data = await _call(server, "download_file", {"blob_id": str(blob_id)})
            ok, detail = _usable(data)
            report.add(CheckResult(name="write:download_file", kind="write", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name="write:download_file", kind="write", ok=False, detail=str(exc)[:300])
            )

    # Cleanup deletes (leave a trail is fine; still exercise delete_*)
    for name, args, cond in [
        ("delete_comment", {"comment_id": created_comment}, created_comment),
        ("delete_note", {"note_id": created_note}, created_note),
        ("delete_task", {"task_id": created_task}, created_task),
        ("delete_calendar_event", {"event_id": created_event}, created_event),
        ("delete_contact", {"contact_id": created_contact}, created_contact),
    ]:
        if not cond:
            continue
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            report.add(CheckResult(name=f"write:{name}", kind="write", ok=ok, detail=detail))
        except Exception as exc:  # noqa: BLE001
            report.add(
                CheckResult(name=f"write:{name}", kind="write", ok=False, detail=str(exc)[:300])
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Set GROUPOFFICE_READONLY=false and exercise create/update/delete",
    )
    args = parser.parse_args()

    if not os.getenv("GROUPOFFICE_URL") or not os.getenv("GROUPOFFICE_API_TOKEN"):
        print(
            "Missing GROUPOFFICE_URL / GROUPOFFICE_API_TOKEN. "
            "Example host: https://go.vitexsoftware.com",
            file=sys.stderr,
        )
        return 2

    report = asyncio.run(run_scenario(read_only=not args.allow_writes))
    print(f"GroupOffice MCP live scenario: {report.url}")
    print(f"passed={report.passed} failed={report.failed} skipped={report.skipped}")
    print()
    for r in report.results:
        flag = "SKIP" if r.skipped else ("PASS" if r.ok else "FAIL")
        print(f"  {flag:4} [{r.kind}] {r.name}: {r.detail}")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(
                {
                    "url": report.url,
                    "passed": report.passed,
                    "failed": report.failed,
                    "skipped": report.skipped,
                    "results": [r.__dict__ for r in report.results],
                },
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        )
        print(f"\nWrote {args.json_out}")

    return 0 if report.failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
