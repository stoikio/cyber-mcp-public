"""MCP tools — Slack (send_slack_message, send_slack_dm, list_slack_channels, read_slack_channel)."""

import json

from gateway.auth import get_current_user
from gateway.security.audit import audit
from gateway.security.policies import check_policies
from gateway.security.rate_limiter import rate_limiter


def register(mcp, slack):

    @mcp.tool()
    async def send_slack_message(channel: str, text: str) -> str:
        """Envoyer un message dans un canal Slack."""
        user = get_current_user()

        ok, msg, _ = await check_policies("send_slack_message", user, {"channel": channel})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="send_slack_message")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="send_slack_message", channel=channel,
                     text_length=len(text))
        result = await slack.send_message(channel, text)
        await audit("SLACK_SENT", user=user, tool="send_slack_message", channel=channel)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def send_slack_dm(user_target: str, text: str) -> str:
        """Envoyer un message direct Slack à un utilisateur."""
        caller = get_current_user()

        ok, msg, _ = await check_policies("send_slack_dm", caller, {"user": user_target})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(caller)
        if not ok:
            await audit("RATE_LIMITED", user=caller, tool="send_slack_dm")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=caller, tool="send_slack_dm", target_user=user_target,
                     text_length=len(text))
        result = await slack.send_dm(user_target, text)
        await audit("SLACK_DM_SENT", user=caller, tool="send_slack_dm", target_user=user_target)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def list_slack_channels() -> str:
        """Lister les canaux Slack autorisés en lecture. Seuls les canaux configurés par un administrateur dans le panneau d'admin sont accessibles. Utilisez cette liste pour connaître les canaux disponibles avant d'appeler read_slack_channel."""
        user = get_current_user()

        ok, msg, _ = await check_policies("list_slack_channels", user, {})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="list_slack_channels")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="list_slack_channels")
        channels = await slack.get_allowed_channels()
        await audit("TOOL_OK", user=user, tool="list_slack_channels", count=len(channels))
        return json.dumps({"channels": channels, "count": len(channels)}, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def read_slack_channel(channel: str, limit: int = 20) -> str:
        """Lire les derniers messages d'un canal Slack autorisé. Le canal doit être dans la liste des canaux configurés (voir list_slack_channels). Les canaux RH et sensibles sont filtrés par les politiques de sécurité. Le paramètre limit est plafonné au maximum configuré par l'administrateur pour chaque canal."""
        user = get_current_user()

        ok, msg, _ = await check_policies("read_slack_channel", user, {"channel": channel, "max_results": limit})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="read_slack_channel")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="read_slack_channel",
                     channel=channel, limit=limit)
        result = await slack.read_channel(channel, limit)

        if "error" in result:
            await audit("TOOL_OK", user=user, tool="read_slack_channel",
                         channel=channel, error=result["error"])
        else:
            await audit("SLACK_CHANNEL_READ", user=user, tool="read_slack_channel",
                         channel=channel, message_count=result.get("count", 0))
        return json.dumps(result, ensure_ascii=False, indent=2)
