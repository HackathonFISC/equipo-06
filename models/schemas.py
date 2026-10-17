"""
Contratos de datos estables de HIDRO360 (Pydantic).

Estos modelos son el "contrato" entre la lógica de negocio, la interfaz
(Streamlit), la API HTTP (FastAPI) y, más adelante, dispositivos externos
(Raspberry Pi 4 / ESP32-S3). Cambiar nombres de campo aquí es un cambio de
contrato: incrementar SCHEMA_VERSION.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "1.2"  # 1.2: Reporte.codigo_seguimiento (portal público)


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
    alias: List[str] = Field(default_factory=list)          # variantes de nombre
    referencias: List[str] = Field(default_factory=list)    # referencias coloquiales ("chino de ...")
    antecedentes_interrupciones: Optional[int] = None       # nº de cortes documentados; None = sin dato
    fuente_datos: str = "ficticio (demo)"
    fecha_datos: Optional[str] = None
    ficticio: bool = True


class Cisterna(BaseModel):
    id: str
    capacidad_litros: int = Field(ge=0)
    litros_disponibles: int = Field(ge=0)
    estado: EstadoCisterna = EstadoCisterna.DISPONIBLE
    sector_base: Optional[str] = None
    sectores_elegibles: Optional[List[str]] = None  # None = puede ir a cualquier sector
    ficticio: bool = True

    @model_validator(mode="after")
    def _disponible_no_excede_capacidad(self):
        if self.litros_disponibles > self.capacidad_litros:
            raise ValueError("litros_disponibles no puede exceder capacidad_litros")
        return self


# --------------------------------------------------------------------------
# Reportes
# --------------------------------------------------------------------------
class Extraccion(BaseModel):
    """Resultado de interpretar el texto. Nunca reemplaza al texto original."""
    sector: Optional[str] = None            # solo si la coincidencia es exacta/alias y no ambigua
    sector_candidatos: List[Dict[str, Any]] = Field(default_factory=list)  # opciones para el operador
    referencia_ubicacion: Optional[str] = None
    tipo_incidencia: Optional[str] = None   # sin_suministro | tuberia_rota | baja_presion | otro
    vulnerabilidades: List[str] = Field(default_factory=list)
    servicio_esencial: Optional[str] = None
    evidencia: Dict[str, str] = Field(default_factory=dict)   # campo -> fragmento literal del mensaje
    confianza_declarada: Optional[float] = Field(None, ge=0, le=1)  # subjetiva del intérprete; NO calibrada
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
    canal: str = "manual"
    referencia_ubicacion: Optional[str] = None
    tipo_incidencia: Optional[str] = None
    vulnerabilidades: List[str] = Field(default_factory=list)
    servicio_esencial: Optional[str] = None
    evidencia: Dict[str, str] = Field(default_factory=dict)
    confianza_declarada: Optional[float] = None
    interprete: str = "reglas"
    sector_candidatos: List[Dict[str, Any]] = Field(default_factory=list)
    clave_idempotencia: Optional[str] = None
    motivo_rechazo: Optional[str] = None
    codigo_seguimiento: Optional[str] = None  # HID-XXXXXXXX; reportes antiguos no lo tienen


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
    metodo: str = "flujo_maximo_lexicografico"
    version_reglas: str = ""
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
    reportes_por_revisar: int = 0
    prioridades_top: List[Dict[str, Any]] = Field(default_factory=list)
    sectores_sin_informacion: int = 0
    cisternas: List[Cisterna] = Field(default_factory=list)


class ConfirmacionDispositivo(BaseModel):
    """Lo que un dispositivo publica con POST /api/v1/dispositivos/confirmaciones."""
    dispositivo_id: str
    plan_id: int
    cisterna_id: Optional[str] = None
    tipo: str = Field(description="p. ej. 'plan_recibido', 'cisterna_en_ruta', 'entrega_realizada'")
    detalle: Dict[str, Any] = Field(default_factory=dict)
