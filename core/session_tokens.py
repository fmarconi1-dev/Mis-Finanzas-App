"""Tokens de sesión firmados (HMAC-SHA256) para mantener la sesión entre
refreshes de página (premortem #3, F2/R9).

Problema que resuelve: `st.session_state` muere con cada refresh o cierre de
pestaña → re-login en cada visita → fricción que mata el hábito de carga.

Mecanismo: tras un login exitoso se emite un token `payload.firma` que viaja
como query param (`?s=...`). Al recargar, app.py lo valida y restaura la
sesión sin pedir credenciales.

Seguridad / activación:
  * SOLO activo si SESSION_SECRET está definido en el entorno (en Fly:
    `fly secrets set SESSION_SECRET=$(openssl rand -hex 32)`).
    Sin secret, la app se comporta exactamente como antes.
  * El token incluye expiración (default 30 días) y va firmado: no se puede
    forjar ni extender sin el secret. No contiene la contraseña.
  * Trade-off conocido: el token queda en la URL (historial del navegador).
    Aceptable para una app personal; rotar SESSION_SECRET lo invalida todo.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

TOKEN_TTL_DEFAULT = 30 * 24 * 3600  # 30 días
QUERY_PARAM = "s"


def _secret() -> Optional[bytes]:
    s = os.environ.get("SESSION_SECRET")
    return s.encode("utf-8") if s else None


def tokens_enabled() -> bool:
    """True si hay SESSION_SECRET configurado."""
    return _secret() is not None


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64d(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def issue_token(user_id: int, ttl: int = TOKEN_TTL_DEFAULT) -> Optional[str]:
    """Emite un token firmado para el user_id. None si no hay secret."""
    secret = _secret()
    if secret is None:
        return None
    payload = json.dumps(
        {"uid": int(user_id), "exp": int(time.time()) + int(ttl)},
        separators=(",", ":"),
    ).encode("utf-8")
    sig = hmac.new(secret, payload, hashlib.sha256).digest()
    return f"{_b64e(payload)}.{_b64e(sig)}"


def verify_token(token: Optional[str]) -> Optional[int]:
    """Devuelve el user_id si el token es válido y no expiró. Sino None.

    Nunca lanza: cualquier token malformado/adulterado/expirado → None.
    """
    secret = _secret()
    if secret is None or not token or "." not in token:
        return None
    try:
        payload_b64, sig_b64 = token.split(".", 1)
        payload = _b64d(payload_b64)
        sig = _b64d(sig_b64)
        expected = hmac.new(secret, payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        data = json.loads(payload)
        if int(data["exp"]) < time.time():
            return None
        return int(data["uid"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None
