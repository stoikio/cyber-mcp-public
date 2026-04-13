"""
Filtrage d'emails sensibles — patterns, sanitisation, vérification destinataire.
Tous les patterns sont des DEFAULTS : ils peuvent être surchargés par les policies
via get_tool_config() pour être administrables depuis le panel admin.
"""

import re

# ─── Default patterns (surchargeable via policies) ────────────────

DEFAULT_SENDER_PATTERNS = [
    r"noreply@", r"no-reply@", r"no\.reply@",
    r"security@", r"auth@", r"verify@",
    r"account[s]?@", r"password@",
    r"notification[s]?@", r"alert[s]?@",
    r"signin@", r"sign-in@",
    r"support@.*\.google\.com",
    r"@accounts\.google\.com",
    r"postmaster@", r"mailer-daemon@",
]

DEFAULT_SUBJECT_PATTERNS = [
    r"(?i)reset\s*(your)?\s*password",
    r"(?i)password\s*reset",
    r"(?i)r[eé]initialiser?\s*(votre)?\s*mot\s*de\s*passe",
    r"(?i)verification\s*code",
    r"(?i)code\s*de\s*v[eé]rification",
    r"(?i)verify\s*your\s*(email|account|identity)",
    r"(?i)v[eé]rifi(er|ez)\s*votre",
    r"(?i)confirm\s*your\s*(email|account|identity)",
    r"(?i)confirmez?\s*votre",
    r"(?i)one[- ]?time\s*(pass)?code",
    r"(?i)\bOTP\b",
    r"(?i)\b2FA\b",
    r"(?i)\bMFA\b",
    r"(?i)two[- ]?factor",
    r"(?i)multi[- ]?factor",
    r"(?i)sign[- ]?in\s*(attempt|alert|notification)",
    r"(?i)connexion\s*(suspecte|inhabitu)",
    r"(?i)security\s*(alert|notification|warning)",
    r"(?i)alerte\s*de\s*s[eé]curit[eé]",
    r"(?i)suspicious\s*(activity|sign[- ]?in|login)",
    r"(?i)new\s*(device|sign[- ]?in|login)",
    r"(?i)magic\s*link",
    r"(?i)login\s*link",
    r"(?i)lien\s*de\s*connexion",
    r"(?i)action\s*required.*account",
]

DEFAULT_BODY_PATTERNS = [
    r"https?://[^\s]*[?&](token|code|key|reset|verify|auth|confirm|challenge)=",
    r"(?:code|Code|CODE)[:\s]+\d{4,8}\b",
    r"\b\d{6}\b(?=.*(?:verification|vérification|confirm|code|enter|saisir))",
    r"(?i)reset\s*(my|your)?\s*password",
    r"(?i)réinitialiser\s*(mon|votre)?\s*mot\s*de\s*passe",
    r"(?i)verify\s*(my|your)?\s*(email|account)",
    r"(?i)confirm\s*(my|your)?\s*(email|account|identity)",
    r"(?i)click\s*(here|below)\s*to\s*(verify|confirm|reset|sign)",
    r"(?i)cliquez?\s*(ici|ci-dessous)\s*pour\s*(v[eé]rifier|confirmer|r[eé]initialiser)",
    r"accounts\.google\.com/signin",
    r"login\.microsoftonline\.com",
    r"auth0\.com",
    r"okta\.com/signin",
]

DEFAULT_AUTH_URL_PATTERNS = [
    r"(https?://[^\s]*[?&](?:token|code|key|reset|verify|auth|confirm|challenge)=)[^\s&\"']*",
    r"(https?://accounts\.google\.com/signin/[^\s\"']*)",
    r"(https?://[^\s]*oauth[^\s\"']*)",
    r"(https?://[^\s]*authorize[^\s\"']*)",
]

DEFAULT_LOOP_PATTERNS = [
    "agent@", "assistant@", "claude@", "automated", "auto-reply", "autoresponse",
]


# ─── Helpers ─────────────────────────────────────────────────────


def _safe_re_search(pattern: str, text: str) -> bool:
    try:
        return re.search(pattern, text) is not None
    except re.error:
        return False


def check_patterns(text: str, patterns: list[str]) -> list[str]:
    if not text:
        return []
    return [p for p in patterns if _safe_re_search(p, text)]


def is_sensitive_email(
    sender: str,
    subject: str,
    body: str,
    *,
    sender_patterns: list[str] | None = None,
    subject_patterns: list[str] | None = None,
    body_patterns: list[str] | None = None,
) -> tuple[bool, list[str]]:
    s_pats = sender_patterns if sender_patterns is not None else DEFAULT_SENDER_PATTERNS
    su_pats = subject_patterns if subject_patterns is not None else DEFAULT_SUBJECT_PATTERNS
    b_pats = body_patterns if body_patterns is not None else DEFAULT_BODY_PATTERNS

    all_matches = []
    sender_m = check_patterns(sender, s_pats)
    if sender_m:
        all_matches.extend([f"sender:{m}" for m in sender_m])
    subject_m = check_patterns(subject, su_pats)
    if subject_m:
        all_matches.extend([f"subject:{m}" for m in subject_m])
    body_m = check_patterns(body, b_pats)
    if body_m:
        all_matches.extend([f"body:{m}" for m in body_m])

    sensitive = bool(subject_m or body_m)
    if not sensitive and sender_m:
        auth_senders = [m for m in sender_m if any(
            kw in m for kw in ["security", "auth", "verify", "password", "signin", "sign-in"]
        )]
        sensitive = bool(auth_senders)
    return sensitive, all_matches


def sanitize_text(
    text: str,
    *,
    url_patterns: list[str] | None = None,
) -> str:
    pats = url_patterns if url_patterns is not None else DEFAULT_AUTH_URL_PATTERNS
    for pat in pats:
        try:
            text = re.sub(pat, r"\1[TOKEN_MASQUE]", text)
        except re.error:
            continue
    text = re.sub(r'(?i)(code|otp)[:\s"]+(\d{4,8})', r'\1: [CODE_MASQUE]', text)
    return text


def is_addressed_to_user(to: str, cc: str = "", user_email: str = "") -> bool:
    """Vérifie que l'email est adressé directement à l'utilisateur (To ou CC)."""
    if not user_email:
        return True
    combined = (to + " " + cc).lower()
    return user_email.lower() in combined


def detect_loop(
    recipient: str,
    *,
    loop_patterns: list[str] | None = None,
) -> bool:
    pats = loop_patterns if loop_patterns is not None else DEFAULT_LOOP_PATTERNS
    lower = recipient.lower()
    return any(ident in lower for ident in pats)
