"""
Policy Engine — charge les politiques depuis PostgreSQL avec cache TTL.
check_policies() évalue les conditions de blocage ET retourne la config
fusionnée pour le post-traitement (filtrage emails, sanitisation, etc.).
"""

import fnmatch
import re
import time
from datetime import datetime
from email.utils import parseaddr

_REGEX_TIMEOUT_SENTINEL = object()


def _safe_re_search(pattern: str, text: str) -> bool:
    """re.search with compilation error handling (defence against malformed patterns)."""
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
        return compiled.search(text) is not None
    except re.error:
        return False


def _addr_matches_pattern(addr: str, pattern: str) -> bool:
    """Vérifie qu'une adresse email matche un pattern de domaine (endswith, pas substring)."""
    _, email = parseaddr(addr)
    if not email:
        email = addr.strip()
    email = email.lower()
    pattern = pattern.lower()
    if pattern.startswith("@"):
        return email.endswith(pattern)
    return email == pattern or email.endswith(f"@{pattern}")

from sqlalchemy import select

from gateway.config import logger
from gateway.db import Policy, async_session
from gateway.security.audit import audit

# ─── Cache en mémoire avec TTL ──────────────────────────────────

_CACHE_TTL = 60  # secondes
_cached_policies: list[dict] = []
_cache_ts: float = 0.0


async def load_policies():
    """Charge les policies depuis PG et met à jour le cache."""
    global _cached_policies, _cache_ts

    try:
        async with async_session() as session:
            result = await session.execute(
                select(Policy)
                .where(Policy.enabled.is_(True))
                .order_by(Policy.priority.desc(), Policy.id)
            )
            rows = result.scalars().all()

        _cached_policies = [
            {
                "name": p.name,
                "description": p.description,
                "tool_pattern": p.tool_pattern,
                "action": p.action,
                "conditions": p.conditions or {},
            }
            for p in rows
        ]
        _cache_ts = time.time()
        logger.info("POLICIES | %d politique(s) chargée(s) depuis PG", len(_cached_policies))
    except Exception as e:
        logger.error("POLICIES | Échec chargement PG : %s", e)


async def _ensure_cache():
    if time.time() - _cache_ts > _CACHE_TTL:
        await load_policies()


# ─── Public API ──────────────────────────────────────────────────


async def check_policies(tool: str, user: str, params: dict) -> tuple[bool, str, dict]:
    """Évalue les politiques pour un appel d'outil donné.
    Retourne (autorisé, raison, config).
    - autorisé : False si une politique bloquante a été déclenchée
    - raison : message explicatif si bloqué
    - config : conditions fusionnées de toutes les policies qui matchent
               (pour le post-traitement par les tools : filtrage, sanitisation, etc.)
    """
    await _ensure_cache()

    merged_config: dict = {}

    for policy in _cached_policies:
        if policy["tool_pattern"] != "*" and not fnmatch.fnmatch(tool, policy["tool_pattern"]):
            continue

        conditions = policy.get("conditions", {})

        # Fusionne les conditions dans la config (haute priorité d'abord)
        for k, v in conditions.items():
            if k not in merged_config:
                merged_config[k] = v
            elif isinstance(v, list) and isinstance(merged_config[k], list):
                existing = set(str(x) for x in merged_config[k])
                merged_config[k] = merged_config[k] + [x for x in v if str(x) not in existing]

        if not conditions:
            if policy["action"] == "log":
                await audit("POLICY_LOG", user=user, tool=tool, policy=policy["name"])
            elif policy["action"] == "warn":
                await audit("POLICY_WARN", user=user, tool=tool, policy=policy["name"])
            elif policy["action"] == "block":
                reason = f"Politique '{policy['name']}' : outil {tool} interdit."
                await audit("POLICY_BLOCKED", user=user, tool=tool,
                            policy=policy["name"], reason=reason)
                return False, reason, merged_config
            continue

        # require_confirmation
        if conditions.get("require_confirmation"):
            reason = (f"Politique '{policy['name']}' : action directe interdite. "
                      "Utilisez create_draft pour créer un brouillon que l'utilisateur pourra relire avant envoi.")
            await audit("POLICY_BLOCKED", user=user, tool=tool,
                        policy=policy["name"], reason=reason)
            if policy["action"] == "block":
                return False, reason, merged_config
            elif policy["action"] == "warn":
                await audit("POLICY_WARN", user=user, tool=tool,
                            policy=policy["name"], reason=reason)

        # allowed_recipients (whitelist To + Cc)
        if "allowed_recipients" in conditions:
            allowed = conditions["allowed_recipients"]
            all_addrs: list[str] = []
            for field in ("to", "cc"):
                raw = params.get(field, "")
                if raw:
                    all_addrs.extend(a.strip() for a in raw.split(",") if a.strip())
            for addr in all_addrs:
                if not any(_addr_matches_pattern(addr, p) for p in allowed):
                    reason = (f"Politique '{policy['name']}' : destinataire {addr} "
                              f"hors liste blanche ({', '.join(allowed)}).")
                    await audit("POLICY_BLOCKED", user=user, tool=tool,
                                policy=policy["name"], reason=reason,
                                rejected_addr=addr)
                    if policy["action"] == "block":
                        return False, reason, merged_config
                    elif policy["action"] == "warn":
                        await audit("POLICY_WARN", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)

        # blocked_recipients (blacklist legacy)
        if "blocked_recipients" in conditions and "to" in params:
            to_addrs = [a.strip() for a in params["to"].split(",") if a.strip()]
            for addr in to_addrs:
                for pattern in conditions["blocked_recipients"]:
                    if _addr_matches_pattern(addr, pattern):
                        reason = f"Politique '{policy['name']}' : envoi vers {pattern} interdit."
                        await audit("POLICY_BLOCKED", user=user, tool=tool,
                                    policy=policy["name"], reason=reason,
                                    rejected_addr=addr)
                        if policy["action"] == "block":
                            return False, reason, merged_config
                        elif policy["action"] == "warn":
                            await audit("POLICY_WARN", user=user, tool=tool,
                                        policy=policy["name"], reason=reason)

        # blocked_recipient_patterns (anti-boucle — substring match sur le destinataire)
        if "blocked_recipient_patterns" in conditions and "to" in params:
            to_lower = params["to"].lower()
            for pattern in conditions["blocked_recipient_patterns"]:
                if pattern.lower() in to_lower:
                    reason = (f"Politique '{policy['name']}' : destinataire interdit "
                              f"(pattern: {pattern}).")
                    await audit("POLICY_BLOCKED", user=user, tool=tool,
                                policy=policy["name"], reason=reason,
                                rejected_to=params["to"])
                    if policy["action"] == "block":
                        return False, reason, merged_config
                    elif policy["action"] == "warn":
                        await audit("POLICY_WARN", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)

        # blocked_tools
        if "blocked_tools" in conditions and tool in conditions["blocked_tools"]:
            reason = f"Politique '{policy['name']}' : outil {tool} interdit."
            await audit("POLICY_BLOCKED", user=user, tool=tool,
                        policy=policy["name"], reason=reason)
            if policy["action"] == "block":
                return False, reason, merged_config

        # blocked_channels (Slack)
        if "blocked_channels" in conditions and "channel" in params:
            channel = params["channel"].lower().lstrip("#")
            for pattern in conditions["blocked_channels"]:
                if fnmatch.fnmatch(channel, pattern.lower()):
                    reason = f"Politique '{policy['name']}' : canal #{channel} interdit."
                    await audit("POLICY_BLOCKED", user=user, tool=tool,
                                policy=policy["name"], reason=reason)
                    if policy["action"] == "block":
                        return False, reason, merged_config
                    elif policy["action"] == "warn":
                        await audit("POLICY_WARN", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)

        # max_results_cap
        if "max_results_cap" in conditions and "max_results" in params:
            cap = conditions["max_results_cap"]
            if params["max_results"] > cap:
                params["max_results"] = cap
                await audit("POLICY_CAPPED", user=user, tool=tool,
                            policy=policy["name"], field="max_results", cap=cap)

        # max_date_range_days
        if "max_date_range_days" in conditions:
            start = params.get("start_date", "")
            end = params.get("end_date", start)
            if start and end:
                try:
                    s = datetime.strptime(start, "%Y-%m-%d")
                    e = datetime.strptime(end, "%Y-%m-%d")
                    delta = (e - s).days
                    max_days = conditions["max_date_range_days"]
                    if delta > max_days:
                        reason = (f"Politique '{policy['name']}' : plage de {delta} jours "
                                  f"dépasse le maximum autorisé de {max_days} jours.")
                        await audit("POLICY_BLOCKED", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)
                        if policy["action"] == "block":
                            return False, reason, merged_config
                        elif policy["action"] == "warn":
                            await audit("POLICY_WARN", user=user, tool=tool,
                                        policy=policy["name"], reason=reason)
                except ValueError:
                    pass

        # blocked_patterns_body (anti-exfiltration — scanne body, text, subject, description)
        if "blocked_patterns_body" in conditions:
            _TEXT_FIELDS = ("body", "text", "subject", "description")
            combined_text = " ".join(params.get(f, "") for f in _TEXT_FIELDS if params.get(f))
            if combined_text:
                for pattern in conditions["blocked_patterns_body"]:
                    if _safe_re_search(pattern, combined_text):
                        reason = (f"Politique '{policy['name']}' : contenu sensible détecté "
                                  f"dans un champ texte (pattern: {pattern}).")
                        await audit("POLICY_BLOCKED", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)
                        if policy["action"] == "block":
                            return False, reason, merged_config
                        elif policy["action"] == "warn":
                            await audit("POLICY_WARN", user=user, tool=tool,
                                        policy=policy["name"], reason=reason)

        # allowed_attendees (whitelist domaine pour invitations calendrier)
        if "allowed_attendees" in conditions and "attendees" in params:
            allowed = conditions["allowed_attendees"]
            raw_attendees = params.get("attendees", "")
            attendee_list = [a.strip() for a in raw_attendees.split(",") if a.strip()] if raw_attendees else []
            for addr in attendee_list:
                if not any(_addr_matches_pattern(addr, p) for p in allowed):
                    reason = (f"Politique '{policy['name']}' : invité {addr} "
                              f"hors liste blanche ({', '.join(allowed)}).")
                    await audit("POLICY_BLOCKED", user=user, tool=tool,
                                policy=policy["name"], reason=reason,
                                rejected_addr=addr)
                    if policy["action"] == "block":
                        return False, reason, merged_config
                    elif policy["action"] == "warn":
                        await audit("POLICY_WARN", user=user, tool=tool,
                                    policy=policy["name"], reason=reason)

        # max_attendees (limite le nombre d'invités par événement)
        if "max_attendees" in conditions and "attendees" in params:
            raw_attendees = params.get("attendees", "")
            attendee_count = len([a for a in raw_attendees.split(",") if a.strip()]) if raw_attendees else 0
            cap = conditions["max_attendees"]
            if attendee_count > cap:
                reason = (f"Politique '{policy['name']}' : {attendee_count} invité(s) "
                          f"dépasse le maximum autorisé de {cap}.")
                await audit("POLICY_BLOCKED", user=user, tool=tool,
                            policy=policy["name"], reason=reason)
                if policy["action"] == "block":
                    return False, reason, merged_config
                elif policy["action"] == "warn":
                    await audit("POLICY_WARN", user=user, tool=tool,
                                policy=policy["name"], reason=reason)

        # max_message_length (anti-exfiltration — limite la taille des messages sortants)
        if "max_message_length" in conditions:
            total_len = sum(len(params.get(f, "")) for f in ("body", "text", "description"))
            cap = conditions["max_message_length"]
            if total_len > cap:
                reason = (f"Politique '{policy['name']}' : message de {total_len} caractères "
                          f"dépasse le maximum autorisé de {cap}.")
                await audit("POLICY_BLOCKED", user=user, tool=tool,
                            policy=policy["name"], reason=reason)
                if policy["action"] == "block":
                    return False, reason, merged_config
                elif policy["action"] == "warn":
                    await audit("POLICY_WARN", user=user, tool=tool,
                                policy=policy["name"], reason=reason)

        # require_query
        if conditions.get("require_query") and not params.get("query"):
            reason = f"Politique '{policy['name']}' : une requête de recherche est obligatoire."
            await audit("POLICY_BLOCKED", user=user, tool=tool,
                        policy=policy["name"], reason=reason)
            if policy["action"] == "block":
                return False, reason, merged_config

        # require_filter (oblige un filtre pour éviter le dump complet)
        if conditions.get("require_filter") and not params.get("filter_json"):
            reason = f"Politique '{policy['name']}' : un filtre est obligatoire pour cette requête."
            await audit("POLICY_BLOCKED", user=user, tool=tool,
                        policy=policy["name"], reason=reason)
            if policy["action"] == "block":
                return False, reason, merged_config

    return True, "", merged_config
