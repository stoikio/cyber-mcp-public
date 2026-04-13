"""
Rate Limiter basé sur Redis sorted sets.
Remplace les RateLimiter et _AuthFailureRateLimiter in-memory.
"""

import time

from gateway.redis_client import get_redis, rate_limit_check
from gateway.security.audit import audit


class RateLimiter:
    """Rate limiter per-user pour les tool calls et les envois d'emails."""

    async def check_action(self, agent_id: str, limit: int = 50) -> tuple[bool, str]:
        key = f"rate:action:{agent_id}"
        allowed, count = await rate_limit_check(key, limit, window_seconds=3600)
        if not allowed:
            return False, f"Rate limit global dépassé : {count}/{limit} actions/heure"
        return True, ""

    async def check_email(
        self,
        agent_id: str,
        recipient: str,
        email_limit: int = 10,
        recipient_limit: int = 3,
    ) -> tuple[bool, str]:
        r = get_redis()
        key = f"rate:email:{agent_id}"
        now = time.time()
        cutoff = now - 3600

        member = f"{recipient.lower()}:{now}"
        pipe = r.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zadd(key, {member: now})
        pipe.zcard(key)
        pipe.zrangebyscore(key, cutoff, "+inf")
        pipe.expire(key, 3600)
        results = await pipe.execute()

        email_count = results[2]
        if email_count > email_limit:
            return False, f"Rate limit email dépassé : {email_count}/{email_limit}/heure"

        all_members = results[3]
        recipient_prefix = f"{recipient.lower()}:"
        recipient_count = sum(1 for m in all_members if m.startswith(recipient_prefix))
        if recipient_count > recipient_limit:
            return False, (
                f"Rate limit destinataire dépassé pour {recipient} : "
                f"{recipient_count}/{recipient_limit}/heure"
            )
        return True, ""


class AuthFailureRateLimiter:
    """Limite les tentatives d'authentification échouées par IP."""

    FAIL_LIMIT = 5
    FAIL_WINDOW = 60

    async def record_failure(self, ip: str):
        r = get_redis()
        key = f"rate:auth_fail:{ip}"
        now = time.time()
        pipe = r.pipeline()
        pipe.zadd(key, {str(now): now})
        pipe.expire(key, self.FAIL_WINDOW)
        await pipe.execute()

    async def is_blocked(self, ip: str) -> bool:
        r = get_redis()
        key = f"rate:auth_fail:{ip}"
        now = time.time()
        cutoff = now - self.FAIL_WINDOW

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.zcard(key)
        results = await pipe.execute()
        count = results[1]
        return count >= self.FAIL_LIMIT


rate_limiter = RateLimiter()
auth_failure_limiter = AuthFailureRateLimiter()
