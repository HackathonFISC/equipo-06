"""
Contratos de datos estables de Agua Clara AI (Pydantic).

Estos modelos son el "contrato" entre la lógica de negocio, la interfaz
(Streamlit), la API HTTP (FastAPI) y, más adelante, dispositivos externos
(Raspberry Pi 4 / ESP32-S3). Cambiar nombres de campo aquí es un cambio de
contrato: incrementar SCHEMA_VERSION.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class Severidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "crítica"


class Vulnerabilidad(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "crítica"


class EstadoReporte(str, Enum):
    POR_REVISAR = "por_revisar"      # extraído, aún sin confirmar por una persona
    CONFIRMADO = "confirmado"        # datos y ubicación confirmados
    DUPLICADO = "duplicado"          # una persona lo marcó duplicado de otro
    EN_PLAN = "en_plan"              # incluido en un plan aprobado
    RECHAZADO = "rechazado"          # descartado por una persona


class EstadoCisterna(str, Enum):
    DISPONIBLE = "disponible"
    EN_MANTENIMIENTO = "en_mantenimiento"
    FUERA_DE_SERVICIO = "fuera_de_servicio"


class EstadoPlan(str, Enum):
    PROPUESTO = "propuesto"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"


class AccionDecision(str, Enum):
    APROBAR = "aprobar"
    RECHAZAR = "rechazar"
    EDITAR = "editar"


# --------------------------------------------------------------------------
# Catálogos
# --------------------------------------------------------------------------
class Sector(BaseModel):
    nombre: str
    poblacion_estimada: int = Field(ge=0)
    vulnerabilidad: Vulnerabilidad = Vulnerabilidad.MEDIA
    lat: Optional[float] = None
    lng: Optional[float] = None
    alias: List[str] = Field(default_factory=list)
    ficticio: bool = True


class Cisterna(BaseModel):
    id: str
    capacidad_litros: int = Field(ge=0)
    litros_disponibles: int = Field(ge=0)
    estado: EstadoCisterna = EstadoCisterna.DISPONIBLE
    sector_base: Optional[str] = None
    ficticio: bool = True


# --------------------------------------------------------------------------
# Reportes
# --------------------------------------------------------------------------
class Extraccion(BaseModel):
    """Resultado de interpretar el texto. Nunca reemplaza al texto original."""
    sector: Optional[str] = None
    calle: Optional[str] = None
    horas_sin_agua: Optional[float] = Field(None, ge=0)
    personas_afectadas: Optional[int] = Field(None, ge=0)
    severidad: Optional[Severidad] = None
    datos_faltantes: List[str] = Field(default_factory=list)
    datos_inciertos: List[str] = Field(default_factory=list)
    notas: List[str] = Field(default_factory=list)
    metodo: str = "reglas"


class Reporte(BaseModel):
    id: int
    mensaje_original: str
    fecha_creacion: datetime
    estado: EstadoReporte = EstadoReporte.POR_REVISAR
    sector: Optional[str] = None
    calle: Optional[str] = None
    horas_sin_agua: Optional[float] = None
    personas_afectadas: Optional[int] = None
    severidad: Optional[Severidad] = None
    datos_faltantes: List[str] = Field(default_factory=list)
    datos_inciertos: List[str] = Field(default_factory=list)
    notas: List[str] = Field(default_factory=list)
    campos_corregidos: List[str] = Field(default_factory=list)
    duplicado_de: Optional[int] = None
    confirmado_por: Optional[str] = None
    ficticio: bool = False


class CandidatoDuplicado(BaseModel):
    reporte_id: int
    similitud: float
    motivos: List[str]
    dudoso: bool = True  # nunca se fusiona automáticamente


# --------------------------------------------------------------------------
# Prioridad y plan
# --------------------------------------------------------------------------
class FactorPrioridad(BaseModel):
    nombre: str
    valor: Optional[float] = None
    normalizado: float
    peso: float
    contribucion: float
    explicacion: str


class PrioridadSector(BaseModel):
    sector: str
    puntaje: float                      # 0-100, reproducible
    categoria: str
    factores: List[FactorPrioridad]
    reportes_ids: List[int]
    reportes_contados: int              # informativo; NO afecta el puntaje
    horas_sin_agua: Optional[float] = None
    personas_afectadas: Optional[int] = None
    severidad: Optional[Severidad] = None
    razones: List[str]


class Asignacion(BaseModel):
    sector: str
    cisterna_id: str
    litros: int = Field(gt=0)
    prioridad: float
    nota: str = ""


class SectorPendiente(BaseModel):
    sector: str
    prioridad: float
    litros_requeridos: int
    litros_cubiertos: int
    litros_faltantes: int
    motivo: str


class PropuestaPlan(BaseModel):
    id: int
    version: int = 1
    fecha_creacion: datetime
    estado: EstadoPlan = EstadoPlan.PROPUESTO
    litros_por_persona: int
    asignaciones: List[Asignacion]
    pendientes: List[SectorPendiente]
    prioridades: List[PrioridadSector]
    editado: bool = False
    resumen: Dict[str, Any] = Field(default_factory=dict)
    borradores_comunicacion: List[Dict[str, str]] = Field(default_factory=list)


class Decision(BaseModel):
    plan_id: int
    accion: AccionDecision
    responsable: str
    motivo: str = ""
    fecha: datetime = Field(default_factory=datetime.now)
    cambios: List[Dict[str, Any]] = Field(default_factory=list)


class EntradaAuditoria(BaseModel):
    id: int
    fecha: datetime
    responsable: str
    accion: str
    entidad: str
    entidad_id: str
    motivo: str = ""
    detalle: Dict[str, Any] = Field(default_factory=dict)
    hash_previo: str
    hash: str


# --------------------------------------------------------------------------
# Contratos para dispositivos futuros (Raspberry Pi 4 / ESP32-S3)
# --------------------------------------------------------------------------
class EstadoActual(BaseModel):
    """Lo que un dispositivo puede leer con GET /api/v1/estado."""
    schema_version: str = SCHEMA_VERSION
    generado: datetime
    plan_aprobado: Optional[PropuestaPlan] = None
    plan_pendiente_de_revision: Optional[PropuestaPlan] = None
    reportes_activos: int = 0
    cisternas: List[Cisterna] = Field(default_factory=list)


class ConfirmacionDispositivo(BaseModel):
    """Lo que un dispositivo publica con POST /api/v1/dispositivos/confirmaciones."""
    dispositivo_id: str
    plan_id: int
    cisterna_id: Optional[str] = None
    tipo: str = Field(description="p. ej. 'plan_recibido', 'cisterna_en_ruta', 'entrega_realizada'")
    detalle: Dict[str, Any] = Field(default_factory=dict)
