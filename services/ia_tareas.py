"""
Tareas de IA de apoyo (opcionales). Gemini REDACTA; el código valida y decide qué se muestra.

  - explicar_prioridad: resumen en lenguaje natural de un puntaje YA calculado por reglas. No envía
    texto de ciudadanos: solo sector, puntaje y factores. Se rechaza si introduce cifras que no estaban
    en la entrada.
  - borrador_comunicacion: borrador informativo para un sector. Se rechaza si promete hora de llegada o
    supera el largo máximo; el aviso «BORRADOR» lo añade siempre el código.
Si Gemini no está configurado o falla, se devuelve el texto local y `origen` lo dice ("local"). Nunca se
presenta texto local como si fuera de Gemini. Ninguna de estas tareas aprueba, envía ni asigna nada.
"""

import json
import re
from typing import Dict, List

import config
from models.schemas import PrioridadSector
from services import communication, ia_gemini, tracing

PROMESA_HORA = re.compile(r"\b\d{1,2}[:h]\d{2}\b|llegar[aá]\s+(a las|en|hoy|mañana)|llegaremos|en \d+ (minutos|horas)", re.I)

_SISTEMA_RESUMEN = ("Redactas, en español claro y en máximo 3 frases, por qué un sector tiene cierta prioridad de "
                    "atención de agua. Usa SOLO los datos del JSON recibido; no inventes cifras ni causas. "
                    "Devuelve un JSON {\"resumen\": \"...\"}.")
_SISTEMA_BORRADOR = ("Redactas un borrador breve (máx. 4 frases) de aviso informativo para una comunidad sin agua. "
                     "Tono claro y respetuoso. NO prometas ninguna hora ni fecha de llegada; di que se informará cuando "
                     "esté confirmada. Usa SOLO los datos del JSON recibido. Devuelve un JSON {\"texto\": \"...\"}.")


def _usar_gemini() -> bool:
    return config.ai_provider() == "gemini"


def _numeros(texto: str) -> set:
    return set(re.findall(r"\d+(?:[.,]\d+)?", texto))


def explicar_prioridad(p: PrioridadSector) -> Dict[str, str]:
    local = " ".join(p.razones)
    if not _usar_gemini():
        return {"texto": local, "origen": "local"}
    entrada = json.dumps({"sector": p.sector, "puntaje": p.puntaje, "categoria": p.categoria,
                          "factores": [{"nombre": f.nombre, "puntos": f.contribucion, "explicacion": f.explicacion}
                                       for f in p.factores], "reportes": p.reportes_contados}, ensure_ascii=False)
    try:
        resumen = str(json.loads(ia_gemini.generar_json(_SISTEMA_RESUMEN, entrada, tarea="resumen"))["resumen"]).strip()
        if not resumen or len(resumen) > 600:
            raise ia_gemini.ErrorIA("resumen vacío o demasiado largo")
        if not _numeros(resumen) <= _numeros(entrada):
            raise ia_gemini.ErrorIA("el resumen introduce cifras que no estaban en los datos")
        return {"texto": resumen, "origen": "gemini"}
    except Exception as e:
        tracing.emitir("ia", "explicar_prioridad", "fallback", {"sector": p.sector}, {"motivo": str(e)[:120]})
        return {"texto": local, "origen": "local (Gemini no disponible)"}


def borrador_comunicacion(sector: str, litros: int, cisternas: List[str]) -> Dict[str, str]:
    local = communication.borrador_asignacion(sector, litros, cisternas)
    if not _usar_gemini():
        return {"texto": local, "origen": "local"}
    entrada = json.dumps({"sector": sector, "litros_previstos": litros, "cisternas": cisternas}, ensure_ascii=False)
    try:
        texto = str(json.loads(ia_gemini.generar_json(_SISTEMA_BORRADOR, entrada, tarea="borrador"))["texto"]).strip()
        if not texto or len(texto) > 700:
            raise ia_gemini.ErrorIA("borrador vacío o demasiado largo")
        if PROMESA_HORA.search(texto):
            raise ia_gemini.ErrorIA("el borrador promete una hora de llegada")
        if not _numeros(texto) <= _numeros(entrada):
            raise ia_gemini.ErrorIA("el borrador introduce cifras que no estaban en los datos")
        return {"texto": texto + "\n\n" + communication.AVISO, "origen": "gemini"}
    except Exception as e:
        tracing.emitir("ia", "borrador_comunicacion", "fallback", {"sector": sector}, {"motivo": str(e)[:120]})
        return {"texto": local, "origen": "local (Gemini no disponible)"}
