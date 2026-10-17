"""
Módulo 1 - Ingesta.
Interpreta texto libre y devuelve campos estructurados. Conserva el texto original
(lo guarda el workflow), marca datos faltantes e inciertos y nunca inventa valores
silenciosamente. Funciona sin IA ni internet (reglas).

Para usar IA más adelante: implementar `Interprete.extraer` y devolver una `Extraccion`.
La prioridad y el plan no dependen de quién interpretó el texto.
"""

import re
from typing import List, Optional, Protocol

from models.schemas import Extraccion, Severidad, Sector
from services.textutil import normalizar

NUMEROS_PALABRA = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12,
}
_NUM = r"(\d+|" + "|".join(NUMEROS_PALABRA) + r")"
PERSONAS_POR_FAMILIA = 4


def _a_numero(token: str) -> Optional[int]:
    token = token.strip()
    return int(token) if token.isdigit() else NUMEROS_PALABRA.get(token)


class Interprete(Protocol):
    def extraer(self, texto: str, sectores: List[Sector]) -> Extraccion: ...


class InterpreteReglas:
    """Interpretación determinista por reglas (modo demo, sin IA)."""

    def extraer(self, texto: str, sectores: List[Sector]) -> Extraccion:
        t = normalizar(texto)
        ex = Extraccion(metodo="reglas")

        ex.sector = self._sector(t, sectores, ex)
        ex.horas_sin_agua = self._horas(t, ex)
        ex.personas_afectadas = self._personas(t, ex)
        ex.severidad = self._severidad(t, ex)
        ex.calle = self._calle(texto)

        for campo in ("sector", "horas_sin_agua", "personas_afectadas", "severidad"):
            if getattr(ex, campo) is None:
                ex.datos_faltantes.append(campo)
        if ex.calle is None:
            ex.notas.append("No se detectó calle o referencia.")
        return ex

    # -- sector ---------------------------------------------------------
    def _sector(self, t: str, sectores: List[Sector], ex: Extraccion) -> Optional[str]:
        # el nombre más largo primero: "Nuevo Arraiján" gana a "Arraiján"
        candidatos = []
        for s in sectores:
            for nombre in [s.nombre, *s.alias]:
                n = normalizar(nombre)
                if re.search(rf"\b{re.escape(n)}\b", t):
                    candidatos.append((len(n), s.nombre, n))
        if not candidatos:
            ex.notas.append("Sector no identificado en el texto: elíjalo del catálogo.")
            return None
        candidatos.sort(reverse=True)
        mejor = candidatos[0]
        # sectores distintos que no son subcadena del ganador => ambiguo
        otros = {c[1] for c in candidatos if c[1] != mejor[1] and c[2] not in mejor[2]}
        if otros:
            ex.datos_inciertos.append("sector")
            ex.notas.append(f"Se mencionan varios sectores ({mejor[1]}, {', '.join(sorted(otros))}); verifique.")
        return mejor[1]

    # -- horas ----------------------------------------------------------
    def _horas(self, t: str, ex: Extraccion) -> Optional[float]:
        m = re.search(rf"{_NUM}\s*dias?", t)
        if m and _a_numero(m.group(1)):
            return float(_a_numero(m.group(1)) * 24)
        m = re.search(rf"{_NUM}\s*(?:horas?|hrs?|h)\b", t)
        if m and _a_numero(m.group(1)):
            return float(_a_numero(m.group(1)))
        if re.search(r"\banoche\b", t):
            ex.datos_inciertos.append("horas_sin_agua")
            ex.notas.append("'Anoche' interpretado como ~12 h: estimación, confirme.")
            return 12.0
        if re.search(r"\bayer\b", t):
            ex.datos_inciertos.append("horas_sin_agua")
            ex.notas.append("'Ayer' interpretado como ~24 h: estimación, confirme.")
            return 24.0
        return None

    # -- personas -------------------------------------------------------
    def _personas(self, t: str, ex: Extraccion) -> Optional[int]:
        m = re.search(rf"{_NUM}\s*(?:personas?|habitantes)", t)
        if m and _a_numero(m.group(1)):
            n = _a_numero(m.group(1))
            if re.search(r"(mas de|como|aproximadamente|unas?|unos)\s+" + re.escape(m.group(1)), t):
                ex.datos_inciertos.append("personas_afectadas")
                ex.notas.append("Cifra de personas aproximada en el texto.")
            return n
        m = re.search(rf"{_NUM}\s*(?:familias?|casas?|viviendas?|hogares)", t)
        if m and _a_numero(m.group(1)):
            n = _a_numero(m.group(1))
            ex.datos_inciertos.append("personas_afectadas")
            ex.notas.append(f"{n} familias/casas x {PERSONAS_POR_FAMILIA} personas por hogar: estimación, confirme.")
            return n * PERSONAS_POR_FAMILIA
        return None

    # -- severidad ------------------------------------------------------
    def _severidad(self, t: str, ex: Extraccion) -> Optional[Severidad]:
        if re.search(r"critic|emergencia|centro de salud|hospital", t):
            return Severidad.CRITICA
        if re.search(r"urgente|grave|anciano|adultos? mayores|enferm|ninos? pequenos|bebes?", t):
            return Severidad.ALTA
        if re.search(r"\bbaja\b", t):
            return Severidad.BAJA
        ex.datos_inciertos.append("severidad")
        ex.notas.append("Severidad no indicada: se deja vacía, no se asume.")
        return None

    # -- calle ----------------------------------------------------------
    def _calle(self, texto: str) -> Optional[str]:
        m = re.search(
            r"(calle [\wáéíóúñ ]+?|colonia [\wáéíóúñ ]+?|zona [\wáéíóúñ]+(?: [\wáéíóúñ]+)?|cerca de [\wáéíóúñ ]+?)(?=[.,;]|$| \d| un | una | hay )",
            texto, flags=re.IGNORECASE)
        return m.group(1).strip() if m else None


_interprete: Interprete = InterpreteReglas()


def interpretar(texto: str, sectores: List[Sector]) -> Extraccion:
    return _interprete.extraer(texto, sectores)
