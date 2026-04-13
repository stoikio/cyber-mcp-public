"""MCP tools — Notion (notion_search, notion_read_page, notion_query_database)."""

import json

from gateway.auth import get_current_user
from gateway.security.audit import audit
from gateway.security.policies import check_policies
from gateway.security.rate_limiter import rate_limiter


def register(mcp, notion):
    @mcp.tool()
    async def notion_search(query: str = "", filter_type: str = "") -> str:
        """Rechercher dans Notion. filter_type optionnel : 'page' ou 'database'."""
        user = get_current_user()

        ok, msg, _ = await check_policies("notion_search", user, {"query": query})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="notion_search")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="notion_search", query=query, filter_type=filter_type)
        results = await notion.search(query, filter_type)
        return json.dumps({
            "results": results,
            "count": len(results),
            "notion_mode": notion.mode,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def notion_read_page(page_id: str) -> str:
        """Lire le contenu complet d'une page Notion (texte, listes, titres, etc.)."""
        user = get_current_user()

        ok, msg, _ = await check_policies("notion_read_page", user, {"page_id": page_id})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="notion_read_page")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="notion_read_page", page_id=page_id)
        page = await notion.read_page(page_id)
        await audit("TOOL_OK", user=user, tool="notion_read_page", page_id=page_id,
                     title=page.get("title", ""))
        return json.dumps(page, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def notion_query_database(database_id: str, filter_json: str = "") -> str:
        """Requêter une base de données Notion. filter_json optionnel au format Notion API filter."""
        user = get_current_user()

        ok, msg, _ = await check_policies("notion_query_database", user, {"database_id": database_id, "filter_json": filter_json})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="notion_query_database")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="notion_query_database",
                     database_id=database_id, has_filter=bool(filter_json))
        results = await notion.query_database(database_id, filter_json)
        return json.dumps({
            "results": results,
            "count": len(results),
            "notion_mode": notion.mode,
        }, ensure_ascii=False, indent=2)
