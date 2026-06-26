"""Contexto del usuario logueado.

En Streamlit, `st.session_state` mantiene el user_id durante la sesión.
Este módulo expone un contextvar que las queries internas pueden consultar
en Round 2 sin tener que threadear `user_id` por toda la API.

Patrón de uso en app.py:

    from core.current_user import set_current_user_id
    set_current_user_id(st.session_state["current_user_id"])

Y en las queries internas:

    from core.current_user import get_current_user_id
    uid = get_current_user_id()
    conn.execute("SELECT ... WHERE user_id = ?", (uid,))

En Round 1 todavía no filtramos queries por user_id (Franco es el único
usuario). Round 2 enchufa la separación efectiva.
"""

from __future__ import annotations

import contextvars
from typing import Optional


_current_user_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "current_user_id", default=None
)


def set_current_user_id(user_id: Optional[int]) -> None:
    _current_user_id.set(user_id)


def get_current_user_id() -> Optional[int]:
    return _current_user_id.get()


def require_current_user_id() -> int:
    uid = _current_user_id.get()
    if uid is None:
        raise RuntimeError(
            "No hay usuario activo en el contexto. ¿Olvidaste llamar a "
            "set_current_user_id() después del login?"
        )
    return uid
