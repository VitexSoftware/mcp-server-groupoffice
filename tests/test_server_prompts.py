from fastmcp import Client


class TestPrompts:
    async def test_lists_all_prompts(self, server):
        async with Client(server) as c:
            prompts = await c.list_prompts()
        names = {p.name for p in prompts}
        assert names == {"daily_briefing", "contact_lookup", "schedule_event_safely"}

    async def test_daily_briefing_mentions_both_tools(self, server):
        async with Client(server) as c:
            result = await c.get_prompt("daily_briefing", {})
        text = result.messages[0].content.text
        assert "query_calendar_events" in text
        assert "query_tasks" in text

    async def test_contact_lookup_discourages_duplicate_creation(self, server):
        async with Client(server) as c:
            result = await c.get_prompt("contact_lookup", {"query": "Jan Novak"})
        text = result.messages[0].content.text
        assert "query_contacts" in text
        assert "Jan Novak" in text
        assert "duplicate" in text.lower()

    async def test_schedule_event_safely_checks_conflicts_first(self, server):
        async with Client(server) as c:
            result = await c.get_prompt(
                "schedule_event_safely",
                {"title": "Standup", "start": "2026-01-01T09:00:00Z", "end": "2026-01-01T09:30:00Z"},
            )
        text = result.messages[0].content.text
        assert "query_calendar_events" in text
        assert "create_calendar_event" in text
        assert "conflict" in text.lower()
