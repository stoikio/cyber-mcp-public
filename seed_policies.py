#!/usr/bin/env python3
"""
Charge policies.json dans la table PostgreSQL `policies`.
Idempotent : les policies existantes (par nom) sont mises à jour, les nouvelles insérées.

Usage :
  python3 seed_policies.py                    # Charge policies.json
  python3 seed_policies.py --file custom.json # Charge un fichier personnalisé
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Import gateway.config first to load .env
from gateway.config import BASE_DIR
from gateway.db import async_session, Policy, init_db

from sqlalchemy import select


async def seed(policy_file: Path):
    if not policy_file.exists():
        print(f"[ERR] Fichier non trouvé : {policy_file}")
        sys.exit(1)

    with open(policy_file) as f:
        data = json.load(f)

    policies = data.get("policies", [])
    if not policies:
        print("[WARN] Aucune politique trouvée dans le fichier.")
        return

    await init_db()

    async with async_session() as session:
        for i, p in enumerate(policies):
            name = p["name"]
            result = await session.execute(select(Policy).where(Policy.name == name))
            existing = result.scalar_one_or_none()

            if existing:
                existing.description = p.get("description", "")
                existing.tool_pattern = p.get("tool_pattern", "*")
                existing.action = p.get("action", "block")
                existing.conditions = p.get("conditions", {})
                existing.priority = len(policies) - i
                print(f"[UPD] {name}")
            else:
                row = Policy(
                    name=name,
                    description=p.get("description", ""),
                    tool_pattern=p.get("tool_pattern", "*"),
                    action=p.get("action", "block"),
                    conditions=p.get("conditions", {}),
                    priority=len(policies) - i,
                )
                session.add(row)
                print(f"[ADD] {name}")

        await session.commit()

    print(f"\n[OK] {len(policies)} politique(s) synchronisées dans PostgreSQL.")


def main():
    parser = argparse.ArgumentParser(description="Charge les politiques de sécurité dans PostgreSQL.")
    parser.add_argument("--file", default=str(BASE_DIR / "policies.json"),
                        help="Chemin vers le fichier de policies (défaut: policies.json)")
    args = parser.parse_args()

    asyncio.run(seed(Path(args.file)))


if __name__ == "__main__":
    main()
