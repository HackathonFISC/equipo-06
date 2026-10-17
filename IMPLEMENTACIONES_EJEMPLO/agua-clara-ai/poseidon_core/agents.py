"""poseidon_core.agents · enjambre de agentes para alertas colectivas predictivas.

``AgenteOrquestadorPanamaOeste`` no decide por cada lectura aislada: acumula
lecturas de infraestructura (aire en tubería, seco, flujo normal) por sector en
una ventana temporal y, cuando un mismo sector acumula 3 o más lecturas
consecutivas de "aire", activa de forma autónoma un **sub-agente de
notificaciones** que encola alertas predictivas ("el agua llegará a su sector en
aproximadamente X minutos").

Diseño de seguridad (consistente con la arquitectura existente):
- Las alertas se **encolan** en el outbox del proyecto; nunca se envían solas.
- Cada activación queda **auditada** con hash encadenado.
- El modelo de "X minutos" es determinista y explicable (prior de corte del
  sector + racha de lecturas). No hay aleatoriedad ni LLM en la decisión.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from poseidon_core.store import ALMACEN

UMBRAL_AIRE_CONSECUTIVAS: int = 3
VENTANA_MIN: int = 30

_ESTADOS_VALIDOS = {"aire", "seco", "flujo_normal", "desconocido"}


def _norm(texto: str) -> str:
    """Minúsculas, sin acentos, sin puntuación: permite comparar nombres panameños."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _racha_aire(estados: list[str]) -> int:
    """Racha CONSECUTIVA de "aire" contando desde la lectura más reciente hacia atrás.

    Las lecturas ``desconocido`` (no se pudo clasificar: sin proveedor, media ilegible)
    se ignoran: **no son evidencia de flujo normal** y por eso NO deben borrar una
    racha ya confirmada. Solo ``flujo_normal`` o ``seco`` terminan la racha.
    """
    racha = 0
    for est in reversed(estados):
        if est == "aire":
            racha += 1
        elif est == "desconocido" or est == "":
            continue
        else:
            break
    return racha


class AgenteOrquestadorPanamaOeste:
    """Motor de enjambre: acumula lecturas sectoriales y dispara alertas colectivas."""

    def __init__(self, almacen=None, umbral: int = UMBRAL_AIRE_CONSECUTIVAS,
                 ventana_min: int = VENTANA_MIN) -> None:
        self.almacen = almacen or ALMACEN
        self.umbral = int(umbral)
        self.ventana_min = int(ventana_min)

    # ------------------------------ catálogo ------------------------------
    def _catalogo(self) -> List[Dict[str, Any]]:
        try:
            from services import catalog, memory  # import perezoso: evita ciclos
        except Exception:
            return []
        sectores = []
        try:
            for s in catalog.sectors():
                sectores.append({
                    "id": s.id, "nombre": s.name,
                    "candidatos": [s.name, s.corregimiento, *s.aliases],
                    "prior_corte": float(getattr(s, "prior_cut", 0.0) or 0.0),
                    "distrito": getattr(s, "district", "") or "",
                })
        except Exception:
            return []
        # Añade referencias locales y alias aprendidos, si existen.
        try:
            for lm in catalog.landmarks():
                sid = lm.get("sector_id")
                if sid:
                    for s in sectores:
                        if s["id"] == sid:
                            s["candidatos"].append(lm.get("name", ""))
                            s["candidatos"].extend(lm.get("aliases", []))
            for s in sectores:
                s["candidatos"].extend(sorted(memory.aliases_for(s["id"])))
        except Exception:
            pass
        return sectores

    def resolver_sector(self, texto: str) -> Tuple[Optional[str], str, float]:
        """Resuelve una barriada escrita libremente -> (sector_id, nombre, score)."""
        objetivo = _norm(texto)
        if not objetivo:
            return None, "", 0.0
        mejor: Tuple[Optional[str], str, float] = (None, texto or "", 0.0)
        for s in self._catalogo():
            score = 0.0
            for cand in s["candidatos"]:
                c = _norm(cand)
                if not c:
                    continue
                if c in objetivo:
                    score = max(score, 1.0)
                    continue
                r = SequenceMatcher(None, c, objetivo).ratio()
                lm = SequenceMatcher(None, c, objetivo).find_longest_match(0, len(c), 0, len(objetivo))
                r = max(r, lm.size / max(len(c), 1))
                score = max(score, r)
            if score > mejor[2]:
                mejor = (s["id"], s["nombre"], round(score, 3))
        return mejor

    def _prior(self, sector_id: Optional[str]) -> float:
        for s in self._catalogo():
            if s["id"] == sector_id:
                return s["prior_corte"]
        return 0.0

    # ------------------------------ núcleo agéntico ------------------------------
    def procesar_lectura_sectorial(self, sector: str, lectura_infraestructura: Dict[str, Any]) -> Dict[str, Any]:
        """Evalúa una lectura de infraestructura y decide si hay crisis colectiva.

        Args:
            sector: barriada escrita libremente (p. ej. ``"Burunga"``).
            lectura_infraestructura: dict con ``estado`` (aire/seco/flujo_normal),
                ``confianza`` y opcionalmente ``segundo``, ``tipo``, ``phone``.

        Returns:
            dict con la decisión: racha, nivel (normal/vigilancia/alerta_predictiva),
            mensaje de alerta, minutos estimados, lecturas en ventana y acciones.
        """
        sid, nombre, score = self.resolver_sector(sector)
        estado = str((lectura_infraestructura or {}).get("estado") or "desconocido").lower()
        if estado not in _ESTADOS_VALIDOS:
            estado = "desconocido"
        try:
            confianza = max(0.0, min(1.0, float((lectura_infraestructura or {}).get("confianza") or 0.0)))
        except Exception:
            confianza = 0.0

        # 1) persistir la lectura (Supabase o SQLite)
        registro = self.almacen.guardar_lectura({
            "phone": (lectura_infraestructura or {}).get("phone"),
            "sector_id": sid, "barriada": sector,
            "tipo": (lectura_infraestructura or {}).get("tipo") or "audio",
            "estado": estado, "confianza": confianza,
            "segundo": int((lectura_infraestructura or {}).get("segundo") or 0),
            "meta": {"score_sector": score, "nivel_sector": nombre,
                     "backend": self.almacen.backend},
        })

        # 2) ventana de lecturas del sector (ascendente en el tiempo)
        recientes = self.almacen.lecturas_recientes(sid, self.ventana_min) if sid else []
        recientes = sorted(recientes, key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
        estados = [str(r.get("estado") or "") for r in recientes]

        # 3) racha CONSECUTIVA de "aire" hacia atrás desde la lectura más reciente
        racha = _racha_aire(estados)
        aire_en_ventana = sum(1 for e in estados if e == "aire")

        # 4) modelo determinista de minutos a la llegada del agua
        prior = self._prior(sid)
        minutos = int(max(15, round(35 + prior * 20 - 5 * max(0, racha - self.umbral))))

        alerta = bool(sid and racha >= self.umbral)
        if alerta:
            nivel = "alerta_predictiva"
        elif racha >= 1 or aire_en_ventana >= 1:
            nivel = "vigilancia"
        else:
            nivel = "normal"

        decision: Dict[str, Any] = {
            "sector_escrito": sector,
            "sector_id": sid,
            "sector_nombre": nombre,
            "score_sector": score,
            "estado": estado,
            "confianza": confianza,
            "nivel": nivel,
            "lecturas_en_ventana": len(recientes),
            "lecturas_aire_ventana": aire_en_ventana,
            "lecturas_consecutivas_aire": racha,
            "umbral": self.umbral,
            "ventana_min": self.ventana_min,
            "alerta_activada": alerta,
            "minutos_estimados": minutos if alerta else None,
            "mensaje_alerta": None,
            "acciones": [],
            "lectura_id": registro.get("id"),
            "backend": registro.get("backend"),
        }

        # 5) sub-agente de notificaciones (encola; nunca envía solo)
        if alerta:
            mensaje = (
                f"⚠️ [Agua Clara AI · Poseidón] {nombre}: se detectó aire en la red "
                f"en {racha} lecturas consecutivas. El agua llegará a su sector en "
                f"aproximadamente {minutos} minutos. Mantenga los grifos cerrados "
                f"hasta que salga el agua limpia."
            )
            decision["mensaje_alerta"] = mensaje
            decision["acciones"] = self._subagente_notificaciones(sid, nombre, mensaje, minutos, racha)

        return decision

    def _subagente_notificaciones(self, sector_id: str, nombre: str, mensaje: str,
                                  minutos: int, racha: int) -> List[Dict[str, Any]]:
        """Sub-agente que encola las alertas predictivas y deja trazabilidad."""
        acciones: List[Dict[str, Any]] = []
        try:
            from services import storage
        except Exception:
            return acciones

        for canal, texto in (("whatsapp", mensaje), ("sms", mensaje[:150])):
            try:
                oid = storage.insert_outbox(canal, f"sector:{sector_id}", texto)
                acciones.append({"canal": canal, "outbox_id": oid,
                                 "destinatario": f"sector:{sector_id}"})
            except Exception as exc:  # noqa: BLE001
                acciones.append({"canal": canal, "error": str(exc)})
        try:
            storage.audit("A_Poseidon_Notificador", "alerta_predictiva_encolada", {
                "sector_id": sector_id, "sector": nombre, "minutos": minutos,
                "racha_aire": racha, "acciones": [a.get("canal") for a in acciones],
            })
        except Exception:
            pass
        return acciones

    # ------------------------------ consulta ------------------------------
    def resumen_sector(self, sector: str, minutos: int = 120) -> Dict[str, Any]:
        """Estado agregado de un sector para la interfaz/consulta."""
        sid, nombre, score = self.resolver_sector(sector)
        lecturas = self.almacen.lecturas_recientes(sid, minutos) if sid else []
        lecturas = sorted(lecturas, key=lambda r: (r.get("created_at") or "", r.get("id") or 0))
        conteo: Dict[str, int] = {}
        for r in lecturas:
            e = str(r.get("estado") or "desconocido")
            conteo[e] = conteo.get(e, 0) + 1
        racha = _racha_aire([str(r.get("estado") or "") for r in lecturas])
        return {
            "sector_escrito": sector, "sector_id": sid, "sector_nombre": nombre,
            "score_sector": score, "lecturas": len(lecturas), "conteo": conteo,
            "racha_aire": racha, "alerta": bool(sid and racha >= self.umbral),
            "detalle": lecturas[-15:],
        }


# Instancia compartida (se inicializa una sola vez en el servidor).
ORQUESTADOR = AgenteOrquestadorPanamaOeste()
