"""MCP tools — registration de tous les outils sur le serveur FastMCP."""

from gateway.tools.gmail import register as register_gmail
from gateway.tools.slack import register as register_slack
from gateway.tools.calendar import register as register_calendar
from gateway.tools.notion import register as register_notion


def register_all_tools(mcp, *, gmail, slack, calendar, notion):
    """Enregistre tous les @mcp.tool() sur le serveur MCP."""
    register_gmail(mcp, gmail)
    register_slack(mcp, slack)
    register_calendar(mcp, calendar)
    register_notion(mcp, notion)
