"""MCP tools — Gmail (read_inbox, read_email, send_email, create_draft, search_emails)."""

import json

from gateway.auth import get_current_user
from gateway.security.audit import audit
from gateway.security.policies import check_policies
from gateway.security.rate_limiter import rate_limiter
from gateway.security.email_filter import (
    is_sensitive_email, sanitize_text, is_addressed_to_user,
)


def _filter_cfg(policy_config: dict) -> dict:
    """Extrait les paramètres de filtrage email depuis la config policies."""
    return {
        "sender_patterns": policy_config.get("sensitive_senders"),
        "subject_patterns": policy_config.get("sensitive_subjects"),
        "body_patterns": policy_config.get("sensitive_body_patterns"),
        "url_patterns": policy_config.get("sanitize_url_patterns"),
        "restrict_to_own": policy_config.get("restrict_to_own_emails", True),
    }


def register(mcp, gmail):
    @mcp.tool()
    async def read_inbox(query: str = "", max_results: int = 10) -> str:
        """Lire les derniers emails. Les emails sensibles (password reset, OTP, magic links) sont automatiquement filtrés."""
        user = get_current_user()
        params = {"query": query, "max_results": max_results}

        ok, msg, pcfg = await check_policies("read_inbox", user, params)
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)
        max_results = params.get("max_results", max_results)
        cfg = _filter_cfg(pcfg)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="read_inbox", reason=msg)
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="read_inbox", query=query, max_results=max_results)
        messages = await gmail.list_messages(query, max_results)

        safe_messages = []
        blocked_count = 0
        recipient_filtered = 0
        for msg_item in messages:
            sender = msg_item.get("from", "")
            subject = msg_item.get("subject", "")
            snippet = msg_item.get("snippet", "")
            to = msg_item.get("to", "")
            cc = msg_item.get("cc", "")

            if cfg["restrict_to_own"] and not is_addressed_to_user(to, cc, user):
                recipient_filtered += 1
                continue

            sensitive, matches = is_sensitive_email(
                sender, subject, snippet,
                sender_patterns=cfg["sender_patterns"],
                subject_patterns=cfg["subject_patterns"],
                body_patterns=cfg["body_patterns"],
            )
            if sensitive:
                blocked_count += 1
                continue

            msg_item["snippet"] = sanitize_text(
                msg_item.get("snippet", ""),
                url_patterns=cfg["url_patterns"],
            )
            safe_messages.append(msg_item)

        total_filtered = blocked_count + recipient_filtered
        result = {
            "emails": safe_messages,
            "count": len(safe_messages),
            "filtered_count": blocked_count,
            "recipient_filtered_count": recipient_filtered,
            "gmail_mode": gmail.mode,
        }
        if total_filtered > 0:
            notes = []
            if blocked_count > 0:
                notes.append(f"{blocked_count} email(s) de sécurité masqué(s) (password reset, OTP, magic links)")
            if recipient_filtered > 0:
                notes.append(f"{recipient_filtered} email(s) adressé(s) à des boîtes partagées masqué(s)")
            result["security_notice"] = (
                "⚠️ Politique de sécurité : " + " ; ".join(notes) + ". "
                "Ces emails n'ont pas été transmis à l'assistant pour des raisons de sécurité. "
                "Consultez directement Gmail pour y accéder."
            )
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def read_email(email_id: str) -> str:
        """Lire le contenu complet d'un email. Les emails sensibles sont bloqués, les URLs d'auth masquées."""
        user = get_current_user()

        ok, msg, pcfg = await check_policies("read_email", user, {"email_id": email_id})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)
        cfg = _filter_cfg(pcfg)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="read_email")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="read_email", email_id=email_id)
        email_data = await gmail.get_message(email_id)
        if "error" in email_data:
            return json.dumps(email_data, ensure_ascii=False)

        sender = email_data.get("from", "")
        subject = email_data.get("subject", "")
        body = email_data.get("body", email_data.get("snippet", ""))
        to = email_data.get("to", "")
        cc = email_data.get("cc", "")

        if cfg["restrict_to_own"] and not is_addressed_to_user(to, cc, user):
            await audit("BLOCKED", user=user, tool="read_email", reason="not_addressed_to_user",
                        email_id=email_id, to=to)
            return json.dumps({
                "blocked": True,
                "reason": "Cet email n'est pas adressé à votre boîte personnelle. Lecture interdite.",
                "email_id": email_id,
            }, ensure_ascii=False, indent=2)

        sensitive, matches = is_sensitive_email(
            sender, subject, body,
            sender_patterns=cfg["sender_patterns"],
            subject_patterns=cfg["subject_patterns"],
            body_patterns=cfg["body_patterns"],
        )
        if sensitive:
            await audit("BLOCKED", user=user, tool="read_email", reason="sensitive_email",
                        email_id=email_id, sender=sender, subject=subject, patterns=matches)
            return json.dumps({
                "blocked": True,
                "reason": "Email de sécurité (password reset, OTP, lien d'authentification). Lecture interdite.",
                "email_id": email_id,
            }, ensure_ascii=False, indent=2)

        email_data["body"] = sanitize_text(email_data.get("body", ""), url_patterns=cfg["url_patterns"])
        email_data["snippet"] = sanitize_text(email_data.get("snippet", ""), url_patterns=cfg["url_patterns"])
        await audit("TOOL_OK", user=user, tool="read_email", email_id=email_id, subject=subject, sender=sender)
        return json.dumps(email_data, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def send_email(to: str, subject: str, body: str) -> str:
        """Envoyer un email. Rate limité à 10/heure et 3 par destinataire/heure. Anti-boucle actif."""
        user = get_current_user()

        ok, msg, _ = await check_policies("send_email", user, {"to": to, "subject": subject, "body": body})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="send_email", to=to)
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_email(user, to)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="send_email", to=to, reason=msg)
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="send_email", to=to, subject=subject)
        result = await gmail.send_message(to, subject, body)
        await audit("EMAIL_SENT", user=user, tool="send_email", to=to, subject=subject)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def create_draft(to: str, subject: str, body: str,
                           thread_id: str = "", in_reply_to: str = "",
                           cc: str = "") -> str:
        """Créer un brouillon d'email. L'utilisateur pourra le relire et l'envoyer manuellement. Pour répondre en thread, fournir thread_id et in_reply_to (Message-ID du mail original). Pour reply-all, inclure les autres destinataires dans cc."""
        user = get_current_user()

        ok, msg, _ = await check_policies("create_draft", user, {"to": to, "subject": subject, "cc": cc, "body": body})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="create_draft")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="create_draft", to=to, cc=cc, subject=subject, thread_id=thread_id)
        result = await gmail.create_draft(to, subject, body,
                                           thread_id=thread_id,
                                           in_reply_to=in_reply_to,
                                           cc=cc)
        await audit("DRAFT_CREATED", user=user, tool="create_draft", to=to, cc=cc, subject=subject, thread_id=thread_id)
        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def search_emails(query: str, max_results: int = 20) -> str:
        """Rechercher des emails. Les emails sensibles sont filtrés des résultats."""
        user = get_current_user()
        params = {"query": query, "max_results": max_results}

        ok, msg, pcfg = await check_policies("search_emails", user, params)
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)
        max_results = params.get("max_results", max_results)
        cfg = _filter_cfg(pcfg)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="search_emails")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="search_emails", query=query, max_results=max_results)
        messages = await gmail.list_messages(query, max_results)

        safe_messages = []
        blocked_count = 0
        recipient_filtered = 0
        for msg_item in messages:
            if cfg["restrict_to_own"] and not is_addressed_to_user(msg_item.get("to", ""), msg_item.get("cc", ""), user):
                recipient_filtered += 1
                continue
            sensitive, _ = is_sensitive_email(
                msg_item.get("from", ""), msg_item.get("subject", ""), msg_item.get("snippet", ""),
                sender_patterns=cfg["sender_patterns"],
                subject_patterns=cfg["subject_patterns"],
                body_patterns=cfg["body_patterns"],
            )
            if sensitive:
                blocked_count += 1
                continue
            msg_item["snippet"] = sanitize_text(
                msg_item.get("snippet", ""),
                url_patterns=cfg["url_patterns"],
            )
            safe_messages.append(msg_item)

        total_filtered = blocked_count + recipient_filtered
        result = {"results": safe_messages, "count": len(safe_messages), "query": query}
        if total_filtered > 0:
            notes = []
            if blocked_count > 0:
                notes.append(f"{blocked_count} email(s) de sécurité masqué(s)")
            if recipient_filtered > 0:
                notes.append(f"{recipient_filtered} email(s) adressé(s) à des boîtes partagées masqué(s)")
            result["security_notice"] = (
                "⚠️ Politique de sécurité : " + " ; ".join(notes) + ". "
                "Ces emails n'ont pas été transmis à l'assistant pour des raisons de sécurité. "
                "Consultez directement Gmail pour y accéder."
            )
        return json.dumps(result, ensure_ascii=False, indent=2)
