"""Mapping Motivo → (Grupo macro, Subcategoria).

Estructura jerárquica de dos niveles:

  Grupo (macro)        Subcategoria
  ──────────────────   ──────────────────────
  Ingreso              Sueldo                ← Haberes Fundación, SBT, UCEMA
                       Otros                 ← Otros ingresos
                       Desahorro             ← Venta divisa (siempre);
                                               Inversiones cuando viene del
                                               lado del ingreso (caso dual).
  Gasto Fijo           Movilidad             ← Auto
                       Hogar                 ← Servicios, Expensas
                       Impuestos             ← Impuestos
                       Financiero            ← Pago tarjeta
  Gasto Variable       Consumo               ← Compras
                       Ocio                  ← Salidas, Viajes
                       Movilidad             ← Transportes
  Inversion            Activos financieros   ← Inversiones (lado pasivo)
                       Ahorro y Resguardo    ← Compra Divisa
  Saldo Inicial        —                     ← Caja (fila apertura)

Caso dual ("Inversiones"): si aparece en `ingresos` (cobranza, venta) cuenta
como Ingreso/Desahorro; si aparece en `pasivos` (inversión nueva) cuenta como
Inversion/Activos financieros. La lógica vive en `efective_grupo()`.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple


# Mapping default {motivo: (grupo, subcategoria)} para uso "directo".
# `efective_grupo()` puede sobrescribirlo cuando aplican reglas duales.
DEFAULT_CATEGORIAS: Dict[str, Tuple[str, Optional[str]]] = {
    # Ingresos
    "Haberes Fundación": ("Ingreso", "Sueldo"),
    "Haberes SBT":       ("Ingreso", "Sueldo"),
    "Haberes UCEMA":     ("Ingreso", "Sueldo"),
    "Otros ingresos":    ("Ingreso", "Otros"),
    "Venta divisa":      ("Ingreso", "Desahorro"),

    # Gastos fijos
    "Auto":              ("Gasto Fijo", "Movilidad"),
    "Servicios":         ("Gasto Fijo", "Hogar"),
    "Expensas":          ("Gasto Fijo", "Hogar"),
    "Impuestos":         ("Gasto Fijo", "Impuestos"),
    "Pago tarjeta":      ("Gasto Fijo", "Financiero"),

    # Gastos variables (Compra Divisa NO está acá — se mueve a Inversion).
    "Compras":           ("Gasto Variable", "Consumo"),
    "Salidas":           ("Gasto Variable", "Ocio"),
    "Viajes":            ("Gasto Variable", "Ocio"),
    "Transportes":       ("Gasto Variable", "Movilidad"),

    # Inversiones / ahorro (la macro "Inversion" es disjunta de "Gasto Variable").
    "Inversiones":       ("Inversion", "Activos financieros"),
    "Compra Divisa":     ("Inversion", "Ahorro y Resguardo"),

    # Especial: la fila del 1/1 que es saldo de apertura.
    "Caja":              ("Saldo Inicial", None),
}


# Compat hacia atrás: {motivo: grupo}. Se mantiene para código que todavía
# espera la estructura plana.
DEFAULT_GRUPOS: Dict[str, str] = {
    motivo: grupo for motivo, (grupo, _) in DEFAULT_CATEGORIAS.items()
}


# Defaults para usuarios nuevos (signup → onboarding). Sin motivos específicos
# de Franco como "Haberes Fundación / SBT / UCEMA". El nuevo usuario edita y
# crea sus propios motivos desde Configuración cuando los necesite.
DEFAULT_CATEGORIAS_NEW_USER: Dict[str, Tuple[str, Optional[str]]] = {
    # Ingresos
    "Sueldo":           ("Ingreso", "Sueldo"),
    "Otros ingresos":   ("Ingreso", "Otros"),
    "Venta divisa":     ("Ingreso", "Desahorro"),

    # Gastos fijos
    "Auto":             ("Gasto Fijo", "Movilidad"),
    "Servicios":        ("Gasto Fijo", "Hogar"),
    "Expensas":         ("Gasto Fijo", "Hogar"),
    "Impuestos":        ("Gasto Fijo", "Impuestos"),
    "Pago tarjeta":     ("Gasto Fijo", "Financiero"),

    # Gastos variables
    "Compras":          ("Gasto Variable", "Consumo"),
    "Salidas":          ("Gasto Variable", "Ocio"),
    "Viajes":           ("Gasto Variable", "Ocio"),
    "Transportes":      ("Gasto Variable", "Movilidad"),

    # Inversion
    "Inversiones":      ("Inversion", "Activos financieros"),
    "Compra Divisa":    ("Inversion", "Ahorro y Resguardo"),
}


# Motivos cuyo grupo depende de la dirección del flujo (ingreso vs pasivo).
# Si vienen como ingreso, se reclasifican a Ingreso/Desahorro.
MOTIVOS_DUAL_DESAHORRO = {"Inversiones"}


def grupo_de(motivo: str, custom_map: Optional[Dict[str, str]] = None) -> str:
    """Devuelve sólo el grupo (compat con código previo)."""
    if custom_map is None:
        custom_map = DEFAULT_GRUPOS
    return custom_map.get(motivo, "Sin categorizar")


def categoria_de(
    motivo: str,
    custom_map: Optional[Dict[str, Tuple[str, Optional[str]]]] = None,
) -> Tuple[str, Optional[str]]:
    """Devuelve (grupo, subcategoria). Si el motivo no existe, ('Sin categorizar', None)."""
    if custom_map is None:
        custom_map = DEFAULT_CATEGORIAS
    return custom_map.get(motivo, ("Sin categorizar", None))


def efective_grupo(
    motivo: str,
    pasivos: float,
    ingresos: float,
    custom_map: Optional[Dict[str, Tuple[str, Optional[str]]]] = None,
) -> Tuple[str, Optional[str]]:
    """Aplica reglas duales: si "Inversiones" llega como ingreso, → Ingreso/Desahorro.

    Para motivos no-duales, devuelve el mapping default.
    """
    if motivo in MOTIVOS_DUAL_DESAHORRO and ingresos > 0 and pasivos == 0:
        return ("Ingreso", "Desahorro")
    return categoria_de(motivo, custom_map)


def motivos_sin_categorizar(
    motivos: list[str], custom_map: Optional[Dict[str, Tuple[str, Optional[str]]]] = None
) -> list[str]:
    if custom_map is None:
        custom_map = DEFAULT_CATEGORIAS
    return sorted({m for m in motivos if m and m not in custom_map})
