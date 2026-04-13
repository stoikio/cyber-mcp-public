"""
Client Redis async — pool de connexions, helpers TTL, et stockage éphémère.
Remplace les _TTLStore in-memory pour les sessions OAuth et les codes d'autorisation.

TLS : pour un Redis managé avec chiffrement en transit, utiliser rediss:// dans REDIS_URL.
"""

import json
import time

import redis.asyncio as aioredis

from gateway.config import REDIS_URL, logger

# ─── Pool global ─────────────────────────────────────────────────

_pool: aioredis.Redis | None = None


async def init_redis() -> aioredis.Redis:
    global _pool
    _pool = aioredis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
        health_check_interval=30,
    )
    try:
        await _pool.ping()
        safe_url = REDIS_URL.split("@")[-1] if "@" in REDIS_URL else REDIS_URL
        tls = "TLS" if REDIS_URL.startswith("rediss://") else "plain"
        logger.info("REDIS | Connecté à %s (%s)", safe_url, tls)
    except Exception as e:
        logger.error("REDIS | Échec de connexion : %s", e)
        raise
    return _pool


async def close_redis():
    global _pool
    if _pool:
        await _pool.aclose()
        _pool = None


def get_redis() -> aioredis.Redis:
    if _pool is None:
        raise RuntimeError("Redis non initialisé. Appelez init_redis() au démarrage.")
    return _pool


# ─── TTL Hash Store (remplace _TTLStore in-memory) ───────────────


async def ttl_set(prefix: str, key: str, data: dict, ttl_seconds: int):
    """Stocke un dict JSON dans Redis avec TTL."""
    r = get_redis()
    redis_key = f"{prefix}:{key}"
    await r.set(redis_key, json.dumps(data, ensure_ascii=False), ex=ttl_seconds)


async def ttl_get(prefix: str, key: str) -> dict | None:
    """Récupère un dict JSON depuis Redis (None si expiré/absent)."""
    r = get_redis()
    raw = await r.get(f"{prefix}:{key}")
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


async def ttl_pop(prefix: str, key: str) -> dict | None:
    """Récupère et supprime un dict JSON (pop atomique)."""
    r = get_redis()
    redis_key = f"{prefix}:{key}"
    raw = await r.getdel(redis_key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


# ─── Sorted-Set Rate Limiter ─────────────────────────────────────


async def rate_limit_check(
    key: str, limit: int, window_seconds: int = 3600
) -> tuple[bool, int]:
    """Vérifie et incrémente un compteur rate-limit basé sur sorted set.

    Retourne (allowed: bool, current_count: int).
    Chaque appel ajoute un timestamp ; les entrées hors fenêtre sont purgées.
    """
    r = get_redis()
    now = time.time()
    cutoff = now - window_seconds

    pipe = r.pipeline()
    pipe.zremrangebyscore(key, "-inf", cutoff)
    pipe.zadd(key, {str(now): now})
    pipe.zcard(key)
    pipe.expire(key, window_seconds)
    results = await pipe.execute()

    count = results[2]
    return count <= limit, count
