"""
Store centralisé pour les tokens d'intégration (Slack, Notion, etc.).
Les tokens sont chiffrés Fernet dans PostgreSQL.
Les backends appellent get_token(service) au lieu de lire des fichiers/env.
"""

from sqlalchemy import select

from gateway.config import logger
from gateway.crypto import encrypt_data, decrypt_data
from gateway.db import IntegrationToken, async_session


async def get_token(service: str) -> str | None:
    """Retourne le token déchiffré pour un service, ou None."""
    try:
        async with async_session() as session:
            row = (
                await session.execute(
                    select(IntegrationToken).where(IntegrationToken.service == service)
                )
            ).scalar_one_or_none()
        if row:
            return decrypt_data(row.encrypted_value)
    except Exception as e:
        logger.error("INTEGRATION_STORE | Erreur lecture %s : %s", service, e)
    return None


async def set_token(service: str, plaintext_value: str, label: str = "", updated_by: str = "") -> None:
    """Crée ou met à jour un token d'intégration (chiffré)."""
    encrypted = encrypt_data(plaintext_value)
    async with async_session() as session:
        row = (
            await session.execute(
                select(IntegrationToken).where(IntegrationToken.service == service)
            )
        ).scalar_one_or_none()
        if row:
            row.encrypted_value = encrypted
            if label:
                row.label = label
            row.updated_by = updated_by
        else:
            row = IntegrationToken(
                service=service,
                encrypted_value=encrypted,
                label=label,
                updated_by=updated_by,
            )
            session.add(row)
        await session.commit()
    logger.info("INTEGRATION_STORE | Token %s mis à jour par %s", service, updated_by or "system")


async def delete_token(service: str) -> bool:
    """Supprime un token d'intégration. Retourne True si trouvé."""
    async with async_session() as session:
        row = (
            await session.execute(
                select(IntegrationToken).where(IntegrationToken.service == service)
            )
        ).scalar_one_or_none()
        if not row:
            return False
        await session.delete(row)
        await session.commit()
    logger.info("INTEGRATION_STORE | Token %s supprimé", service)
    return True


def mask_token(value: str) -> str:
    """Masque un token pour l'affichage (ex: xoxb-****...****ab3f)."""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}····{value[-4:]}"
