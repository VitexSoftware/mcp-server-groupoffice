---
name: groupoffice-operations
description: Operate a GroupOffice groupware instance through the groupoffice-mcp-server MCP server -- look up and manage contacts, calendar events, tasks, notes, projects, comments, and file attachments. Use when a user asks about GroupOffice contacts, appointments, tasks, notes, or wants a daily briefing. Defaults to read-only.
---

# GroupOffice Operations

This skill uses the tools, resources, and prompts exposed by the
`groupoffice-mcp-server` MCP server to operate a
[GroupOffice](https://www.group-office.com/) instance -- an open-source
groupware/CRM suite (contacts, calendar, tasks, notes, projects, files).

The server defaults to **read-only**: `create_*`/`update_*`/`delete_*`/
`upload_file` tools are rejected unless the operator has explicitly set
`GROUPOFFICE_READONLY=false`. Expect write attempts to fail with a clear
"read-only mode" error on a default deployment -- that is expected behavior,
not a bug.

## Core principle: read before write

Always prefer `query_*`/`get_*`/`list_*` tools to inspect current state before
calling a `create_*`/`update_*`/`delete_*` tool. This matters even when writes
are enabled:

- Before creating a contact, use `query_contacts` (or the `contact_lookup`
  prompt) to check it doesn't already exist.
- Before scheduling a calendar event, use `query_calendar_events` (or the
  `schedule_event_safely` prompt) to check for conflicts in that time window.
- Before deleting or updating anything, `get_*` it first and confirm you have
  the right record.

## Daily briefing

Use the `daily_briefing` prompt (optionally with a `date`) to get a summary of
that day's calendar events and open tasks in one pass.

## Looking up a contact

Use `query_contacts`, optionally narrowed by `addressbook_id` or a raw
`filter` dict. Prefer the `contact_lookup` prompt when the goal is "find or
create" -- it explicitly checks for existing matches before suggesting
`create_contact`, to avoid duplicate contacts.

## Scheduling without conflicts

Use the `schedule_event_safely` prompt rather than calling
`create_calendar_event` directly -- it checks `query_calendar_events` for the
proposed time window first and reports overlaps before proceeding.

## Comments and history on a record

`query_comments` and `query_history` both filter by `entity` (the friendly
GroupOffice entity name, e.g. `"Contact"`) and `entity_id`. `query_history`
(GroupOffice's `LogEntry` entity) is a read-only audit log -- there is no way
to create/update/delete history entries, by design.

## File attachments

`upload_file` takes base64-encoded content and returns a `blob_id`; attach it
to another entity by including that `blob_id` in the relevant field of a
`create_*`/`update_*` call's `data`. `download_file` returns base64-encoded
content -- fine for small attachments, but avoid it for large files since
base64 inflates size by roughly a third.

## Everything else

Tasks, notes, and (where the optional Projects v3 module is installed)
projects all follow the same `query_*`/`get_*`/`create_*`/`update_*`/
`delete_*` shape -- see the server's README for the full tool table. `User`/
`Group` tools are read-only by design; user and group administration is
deliberately out of scope for this server.
