#!/usr/bin/env python3
"""
Security Migration Tool (PostgreSQL)
=====================================
Migre les secrets et clés vers PostgreSQL + format sécurisé :
  - api_keys.json → table `api_keys` en PG (SHA-256 hachées + expiration)

Les tokens d'intégration (Slack, Notion) sont gérés via l'admin panel
et stockés chiffrés (Fernet) dans la table `integration_tokens`.
Les tokens Google OAuth2 (Gmail, Calendar) sont per-user dans `user_tokens`.

Usage :
  python3 migrate_security.py                          # Migration complète vers PG
  python3 migrate_security.py --add-key EMAIL          # Générer et ajouter une clé en PG
  python3 migrate_security.py --generate-encryption-key # Générer une clé Fernet
  python3 migrate_security.py --generate-jwt-secret    # Générer un secret JWT
  python3 migrate_security.py --rotate-key HASH_PREFIX EMAIL  # Révoquer + recréer en PG
  python3 migrate_security.py --list-keys              # Lister les clés en PG
"""

import argparse
import asyncio
import hashlib
import json
import os
import secrets
import stat
import uuid
from datetime import datetime, timezone, timedelta

# Import gateway.config to load .env
from gateway.config import BASE_DIR
from gateway.db import async_session, ApiKey, init_db

from sqlalchemy import select

API_KEYS_FILE = BASE_DIR / "api_keys.json"
DEFAULT_EXPIRY_DAYS = 180


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ─── Migration vers PG ──────────────────────────────────────────


async def migrate_api_keys_to_pg():
    """Migre api_keys.json vers la table PostgreSQL api_keys."""
    if not API_KEYS_FILE.exists():
        print("[SKIP] api_keys.json non trouvé.")
        return

    with open(API_KEYS_FILE) as f:
        data = json.load(f)

    if isinstance(data, dict) and data.get("version") == 2:
        keys = data.get("keys", {})
    elif isinstance(data, dict) and not data.get("version"):
        print("[ERR] Format v1 détecté. Lancez d'abord la migration v1→v2.")
        return
    else:
        print("[ERR] Format api_keys.json non reconnu.")
        return

    await init_db()

    count = 0
    async with async_session() as session:
        for key_hash, meta in keys.items():
            existing = await session.get(ApiKey, key_hash)
            if existing:
                print(f"  [SKIP] {key_hash[:16]}… ({meta['email']}) — déjà en PG")
                continue

            row = ApiKey(
                key_hash=key_hash,
                email=meta["email"],
                expires_at=datetime.fromisoformat(meta["expires_at"]) if meta.get("expires_at") else None,
            )
            session.add(row)
            count += 1
            print(f"  [ADD]  {key_hash[:16]}… → {meta['email']}")

        await session.commit()

    print(f"\n[OK] {count} clé(s) migrée(s) vers PostgreSQL.")


# ─── Ajout de clé (PG) ──────────────────────────────────────────


async def add_key_pg(email: str, expiry_days: int = DEFAULT_EXPIRY_DAYS):
    """Génère une nouvelle clé API et l'insère dans PostgreSQL."""
    await init_db()

    new_key = str(uuid.uuid4())
    key_hash = _hash_key(new_key)
    expires = datetime.now(timezone.utc) + timedelta(days=expiry_days)

    async with async_session() as session:
        row = ApiKey(key_hash=key_hash, email=email, expires_at=expires)
        session.add(row)
        await session.commit()

    print(f"[OK]   Nouvelle clé API générée pour {email}")
    print(f"       Clé (à transmettre à l'utilisateur) : {new_key}")
    print(f"       Hash (stocké en PG) : {key_hash[:16]}…")
    print(f"       Expiration : {expires.isoformat()}")
    print()
    print("  Configuration Claude Desktop de l'utilisateur :")
    print('  {')
    print('    "mcpServers": {')
    print('      "secure-mcp-gateway": {')
    print('        "url": "https://YOUR_GATEWAY_DOMAIN/mcp",')
    print(f'        "headers": {{ "X-API-Key": "{new_key}" }}')
    print('      }')
    print('    }')
    print('  }')


# ─── Rotation de clé (PG) ───────────────────────────────────────


async def rotate_key_pg(old_key_prefix: str, email: str, expiry_days: int = DEFAULT_EXPIRY_DAYS):
    """Révoque les clés correspondant au préfixe et en génère une nouvelle en PG."""
    await init_db()

    async with async_session() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.email == email, ApiKey.revoked.is_(False))
        )
        keys = result.scalars().all()

        revoked = []
        for key in keys:
            if key.key_hash.startswith(old_key_prefix):
                key.revoked = True
                revoked.append(key.key_hash[:16])

        await session.commit()

    if revoked:
        print(f"[OK]   {len(revoked)} clé(s) révoquée(s) : {', '.join(r + '…' for r in revoked)}")
    else:
        print(f"[WARN] Aucune clé trouvée pour le préfixe '{old_key_prefix}' et l'email '{email}'.")

    await add_key_pg(email, expiry_days)


# ─── Listing des clés ───────────────────────────────────────────


async def list_keys_pg():
    """Liste toutes les clés API en PostgreSQL."""
    await init_db()

    async with async_session() as session:
        result = await session.execute(select(ApiKey).order_by(ApiKey.created_at.desc()))
        keys = result.scalars().all()

    if not keys:
        print("[INFO] Aucune clé API en base.")
        return

    print(f"{'Hash (prefix)':<20} {'Email':<35} {'Expires':<25} {'Status'}")
    print("-" * 100)
    for k in keys:
        status = "REVOKED" if k.revoked else "active"
        expires = k.expires_at.isoformat() if k.expires_at else "never"
        if k.expires_at and datetime.now(timezone.utc) > k.expires_at.replace(tzinfo=timezone.utc):
            status = "EXPIRED"
        print(f"{k.key_hash[:16]}…   {k.email:<35} {expires:<25} {status}")


# ─── Génération clé Fernet ───────────────────────────────────────


def generate_encryption_key():
    from cryptography.fernet import Fernet
    key = Fernet.generate_key().decode("ascii")
    print("[OK]   Clé Fernet générée :")
    print(f"       {key}")
    print()
    print("  Ajoutez à votre fichier .env :")
    print(f'  ENCRYPTION_KEY="{key}"')


def generate_jwt_secret():
    key = secrets.token_urlsafe(32)
    print("[OK]   Secret JWT généré :")
    print(f"       {key}")
    print()
    print("  Ajoutez à votre fichier .env :")
    print(f'  JWT_SECRET="{key}"')


# ─── Permissions fichier ─────────────────────────────────────────


def fix_file_permissions():
    sensitive_files = [
        API_KEYS_FILE,
        BASE_DIR / "credentials.json",
    ]
    for path in sensitive_files:
        if path.exists():
            current = oct(os.stat(path).st_mode & 0o777)
            os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            print(f"[OK]   {path.name} : {current} → 0o600")
        else:
            print(f"[SKIP] {path.name} non trouvé.")


# ─── Main ─────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="Security Migration Tool — PostgreSQL + chiffrement."
    )
    parser.add_argument("--add-key", metavar="EMAIL",
                        help="Générer et ajouter une clé API en PostgreSQL")
    parser.add_argument("--rotate-key", nargs=2, metavar=("HASH_PREFIX", "EMAIL"),
                        help="Révoquer une clé et en générer une nouvelle en PG")
    parser.add_argument("--list-keys", action="store_true",
                        help="Lister les clés API en PostgreSQL")
    parser.add_argument("--generate-encryption-key", action="store_true",
                        help="Générer une clé Fernet pour ENCRYPTION_KEY")
    parser.add_argument("--generate-jwt-secret", action="store_true",
                        help="Générer un secret JWT pour JWT_SECRET")
    parser.add_argument("--expiry-days", type=int, default=DEFAULT_EXPIRY_DAYS,
                        help=f"Durée de validité des clés en jours (défaut: {DEFAULT_EXPIRY_DAYS})")
    parser.add_argument("--fix-permissions", action="store_true",
                        help="Appliquer chmod 0o600 sur les fichiers sensibles")

    args = parser.parse_args()

    if args.generate_encryption_key:
        generate_encryption_key()
        return

    if args.generate_jwt_secret:
        generate_jwt_secret()
        return

    if args.add_key:
        asyncio.run(add_key_pg(args.add_key, args.expiry_days))
        return

    if args.rotate_key:
        asyncio.run(rotate_key_pg(args.rotate_key[0], args.rotate_key[1], args.expiry_days))
        return

    if args.list_keys:
        asyncio.run(list_keys_pg())
        return

    if args.fix_permissions:
        fix_file_permissions()
        return

    print("=" * 60)
    print("  Security Migration Tool (PostgreSQL)")
    print("=" * 60)
    print()

    print("─── Étape 1 : Migration api_keys.json → PostgreSQL ────")
    asyncio.run(migrate_api_keys_to_pg())
    print()

    print("─── Étape 2 : Permissions fichier ─────────────────────")
    fix_file_permissions()
    print()

    print("=" * 60)
    print("  Migration terminée.")
    print()
    print("  Prochaines étapes :")
    print("  1. Charger les policies : python3 seed_policies.py")
    print("  2. Vérifier les clés    : python3 migrate_security.py --list-keys")
    print("  3. Lancer le gateway    : python3 mcp_secure_gateway.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
