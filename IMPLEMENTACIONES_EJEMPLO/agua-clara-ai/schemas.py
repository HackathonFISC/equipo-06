"""Modelos compartidos (contratos entre agentes).

Todo lo que entra y sale de un agente se valida aquí. Un campo que no se pudo
extraer queda en None; nunca se inventa. La IA interpreta, el código valida.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class IncidentType(str, Enum):
    SIN_AGUA = "sin_agua"
    BAJA_PRESION = "baja_presion"
    TUBERIA_ROTA = "tuberia_rota"
    COBRO_INDEBIDO = "cobro_indebido"
    OTRO = "otro"


# ----------------------------- Catálogo -----------------------------

class Sector(BaseModel):
    id: str
    name: str
    district: str
    corregimiento: str = ""
    population: int = Field(ge=0)
    vulnerability: float = Field(ge=0, le=1)
    hourly_deprivation_weight: float = 1.0
    essential_services: List[str] = Field(default_factory=list)
    hours_without_water: float = Field(ge=0)
    prior_cut: float = Field(ge=0, le=1)
    report_propensity: float = Field(ge=0, le=1)
    latitude: float
    longitude: float
    aliases: List[str] = Field(default_factory=list)


class Tanker(BaseModel):
    id: str
    capacity_liters: int = Field(gt=0)
    shift: List[str]
    base: str
    latitude: float
    longitude: float


class FillingPoint(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    fill_minutes: int = 25


# ----------------------------- Reporte -----------------------------

class Report(BaseModel):
    id: Optional[str] = None
    created_at: Optional[str] = None
    channel: str = "texto"
    raw_text: str

    sector_hint: Optional[str] = None
    sector_id: Optional[str] = None

    incident_type: IncidentType = IncidentType.OTRO
    severity: Optional[int] = Field(default=None, ge=1, le=5)
    hours_without_water: Optional[float] = Field(default=None, ge=0, le=720)
    affected_people: Optional[int] = Field(default=None, ge=0, le=200000)
    institution_type: Optional[str] = None

    confidence: float = Field(default=0.0, ge=0, le=1)
    missing_fields: List[str] = Field(default_factory=list)

    source_hash: Optional[str] = None          # teléfono/remitente seudonimizado
    injection_flag: bool = False                # intento de inyección de instrucciones
    out_of_scope: bool = False                  # fuera de Panamá Oeste
    medical_emergency: bool = False             # mención de emergencia médica -> derivar al 911
    status: str = "recibido"                    # recibido | pendiente_confirmacion | confirmado | duplicado | rechazado
    dup_of: Optional[str] = None

    # Metadatos del pipeline (agentes nuevos): normalización, media, geo, consenso.
    meta: dict = Field(default_factory=dict)

    @field_validator("raw_text")
    @classmethod
    def _limit_len(cls, v: str) -> str:
        if len(v) > 4000:
            raise ValueError("reporte demasiado largo (máx 4000 caracteres)")
        return v


class ReportConfirm(BaseModel):
    sector_id: Optional[str] = None
    incident_type: Optional[IncidentType] = None
    hours_without_water: Optional[float] = Field(default=None, ge=0, le=720)
    affected_people: Optional[int] = Field(default=None, ge=0, le=200000)
    severity: Optional[int] = Field(default=None, ge=1, le=5)
    operator: str = "operador"


# ----------------------------- Prioridad -----------------------------

class SectorPriority(BaseModel):
    sector_id: str
    name: str
    p_cut: float
    distinct_sources: int
    hours_without_water: float
    population_affected: int
    vulnerability: float
    essential_services: List[str]
    score: float
    rank: int
    reasons: List[str]
    visibility_note: str


# ----------------------------- Plan -----------------------------

class Assignment(BaseModel):
    sector_id: str
    sector_name: str
    tanker_id: str
    liters: int
    stop_order: int
    eta_minutes: Optional[int]
    reasons: List[str]
    constraints_ok: bool = True


class Plan(BaseModel):
    id: Optional[str] = None
    created_at: Optional[str] = None
    method: str = "social"                      # social | quejas
    assignments: List[Assignment] = Field(default_factory=list)
    pending: List[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)
    explanation: str = ""
    status: str = "propuesto"                   # propuesto | aprobado | editado | rechazado


class Decision(BaseModel):
    plan_id: str
    action: str                                 # aprobar | editar | rechazar
    operator: str
    reason: str = ""
    changes: List[Assignment] = Field(default_factory=list)


# ----------------------------- Verificación de entrega (A6) -----------------------------

class DeliveryEvidence(BaseModel):
    plan_id: Optional[str] = None
    sector_id: str
    tanker_id: str
    liters_reported: int = Field(ge=0)
    tank_capacity_liters: int = Field(gt=0)
    gps_max_speed_kmh: float = 0.0
    gps_offroad_ratio: float = 0.0             # fracción del recorrido fuera de vía
    seconds_stopped_at_point: float = 0.0
    community_confirmations: int = 0
    confirmations_from_outside: int = 0
    trace_similarity_to_history: float = 0.0  # 1.0 = idéntica a una traza vieja


class DeliveryVerdict(BaseModel):
    status: str                                 # confirmada | dudosa | rechazada
    checks: List[dict]
    reasons: List[str]


# ----------------------------- WhatsApp / canal (A0) -----------------------------

class MediaItem(BaseModel):
    kind: str                                   # image | audio | video | document | sticker
    mime: Optional[str] = None
    name: Optional[str] = None
    media_id: Optional[str] = None
    url: Optional[str] = None
    caption: Optional[str] = None
    downloaded: bool = False


class WhatsAppIncoming(BaseModel):
    message_id: str
    sender: str
    sender_name: Optional[str] = None
    text: str = ""
    media: List[MediaItem] = Field(default_factory=list)
    location: Optional[dict] = None
    timestamp: Optional[str] = None
    channel: str = "whatsapp"
