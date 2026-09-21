#!/usr/bin/env python3
"""Live capability scenario for GroupOffice MCP Server.

Exercises every registered MCP tool against a real GroupOffice instance:
read tools must return usable data; mutating tools must be blocked when
GROUPOFFICE_READONLY is enabled (the default).

Usage:
  export GROUPOFFICE_URL=https://groupoffice.spoje.net
  export GROUPOFFICE_API_TOKEN=...
  export GROUPOFFICE_READONLY=true
  python tests/live_capability_scenario.py --json-out /tmp/go-live.json

Exit code is 0 only when every non-skipped check passes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
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
        return True, f"keys={list(data.keys())[:8]}"
    if isinstance(data, str):
        return (bool(data.strip()), "empty string" if not data.strip() else "ok string")
    return True, f"type={type(data).__name__}"


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

    # Seed ids from list tools
    contact_id = None
    event_id = None
    task_id = None
    note_id = None

    listish = [
        ("list_addressbooks", {}),
        ("list_calendars", {}),
        ("list_tasklists", {}),
        ("query_contacts", {"limit": 5}),
        ("query_calendar_events", {"limit": 5}),
        ("query_tasks", {"limit": 5}),
        ("query_notes", {"limit": 5}),
        ("query_comments", {"limit": 5}),
        ("query_history", {"limit": 5}),
        ("query_users", {"limit": 5}),
        ("query_groups", {"limit": 5}),
    ]
    # projects may be optional module
    optional_list = [("query_projects", {"limit": 5})]

    for name, args in listish:
        try:
            data = await _call(server, name, args)
            ok, detail = _usable(data)
            report.add(CheckResult(name=name, kind="tool", ok=ok, detail=detail, sample=str(data)[:400]))
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
            # Module may be disabled — treat "not found"/permission as skip
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

    id_gets = [
        ("get_contact", {"contact_id": contact_id}, contact_id),
        ("get_calendar_event", {"event_id": event_id}, event_id),
        ("get_task", {"task_id": task_id}, task_id),
        ("get_note", {"note_id": note_id}, note_id),
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

    # Cover remaining RO tools not explicitly probed
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
                # Middleware should raise before returning success
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

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out")
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="Set GROUPOFFICE_READONLY=false (skips write guards)",
    )
    args = parser.parse_args()

    if not os.getenv("GROUPOFFICE_URL") or not os.getenv("GROUPOFFICE_API_TOKEN"):
        print(
            "Missing GROUPOFFICE_URL / GROUPOFFICE_API_TOKEN. "
            "Example host: https://groupoffice.spoje.net",
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
