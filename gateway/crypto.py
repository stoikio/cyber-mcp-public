"""
Helpers de chiffrement Fernet — lecture/écriture sécurisée de fichiers et données.
Partagé entre les backends (token_store) et le module auth.
"""

import json
import os
import stat
from pathlib import Path

from gateway.config import ENCRYPTION_KEY, logger


def _get_fernet():
    """Initialise Fernet si ENCRYPTION_KEY est configuré."""
    if not ENCRYPTION_KEY:
        return None
    try:
        from cryptography.fernet import Fernet
        key = ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY
        return Fernet(key)
    except ImportError:
        logger.warning("CRYPTO | Package 'cryptography' non installé. Chiffrement désactivé.")
        return None
    except Exception as e:
        logger.error("CRYPTO | Erreur Fernet : %s", e)
        return None


fernet = _get_fernet()


def encrypt_data(plaintext: str) -> str:
    """Chiffre une chaîne avec Fernet. Lève une erreur si ENCRYPTION_KEY n'est pas configuré."""
    if fernet:
        return fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")
    raise RuntimeError(
        "ENCRYPTION_KEY non configuré — impossible de chiffrer des données sensibles. "
        "Générez une clé avec : python3 migrate_security.py --generate-encryption-key"
    )


def decrypt_data(data: str) -> str:
    """Déchiffre une chaîne Fernet. Tente le fallback plaintext si pas de clé (migration)."""
    if fernet:
        try:
            return fernet.decrypt(data.encode("ascii")).decode("utf-8")
        except Exception:
            logger.warning("CRYPTO | Échec déchiffrement — donnée probablement en clair (pré-migration)")
            return data
    logger.warning("CRYPTO | ENCRYPTION_KEY absent — lecture en clair (migration requise)")
    return data


def secure_write(path: Path, content: str):
    """Écrit un fichier chiffré (si ENCRYPTION_KEY) avec permissions 0o600."""
    if fernet:
        encrypted = fernet.encrypt(content.encode("utf-8")).decode("ascii")
        payload = json.dumps({"_encrypted": True, "data": encrypted})
    else:
        payload = content
    with open(path, "w") as f:
        f.write(payload)
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


def secure_read(path: Path) -> str:
    """Lit un fichier en le déchiffrant si nécessaire."""
    with open(path) as f:
        raw = f.read()
    try:
        wrapper = json.loads(raw)
        if isinstance(wrapper, dict) and wrapper.get("_encrypted"):
            if not fernet:
                raise RuntimeError(
                    f"Le fichier {path.name} est chiffré mais ENCRYPTION_KEY n'est pas configuré."
                )
            return fernet.decrypt(wrapper["data"].encode("ascii")).decode("utf-8")
    except (json.JSONDecodeError, KeyError):
        pass
    return raw
