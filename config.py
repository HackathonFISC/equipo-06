"""
Configuración de HIDRO360.
Todo es local: sin internet, sin claves, sin hardware.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent


def _cargar_dotenv(ruta: Path) -> None:
    """Carga KEY=VALUE de .env SIN pisar variables ya definidas en el entorno (sin dependencias).
    .env está en .gitignore: ahí van GEMINI_API_KEY y los tokens, nunca en el código."""
    if not ruta.is_file():
        return
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, _, valor = linea.partition("=")
        valor = valor.strip().strip('"').strip("'")
        if clave.strip() and valor:
            os.environ.setdefault(clave.strip(), valor)


_cargar_dotenv(BASE_DIR / ".env")

# Base de datos SQLite local (se puede cambiar con AGUA_CLARA_DB, p. ej. para pruebas)
DB_PATH = Path(os.environ.get("AGUA_CLARA_DB", BASE_DIR / "agua_clara.db"))

APP_NAME = "HIDRO360"
EQUIPO = "TEAM VIFY AI"
APP_VERSION = "0.5.0"
VERSION_REGLAS = "reglas-2026.10.a"   # cambia si cambian pesos, topes o reglas deterministas

# Parámetros del cálculo de prioridad (deterministas y visibles en la interfaz)
PESO_HORAS = 0.40
PESO_POBLACION = 0.30
PESO_VULNERABILIDAD = 0.30
HORAS_TOPE = 96.0           # a partir de 96 h sin agua el factor llega a su máximo
PERSONAS_TOPE = 300         # a partir de 300 personas afectadas el factor llega a su máximo
VULNERABILIDAD_VALORES = {"baja": 0.25, "media": 0.5, "alta": 0.75, "crítica": 1.0}

# Parámetros del planificador
LITROS_POR_PERSONA = 15     # litros de emergencia por persona (valor ficticio de demo)
CATEGORIAS = [(70, "CRÍTICA"), (50, "ALTA"), (30, "MEDIA"), (0, "BAJA")]

# Duplicados: umbral conservador de sugerencia. Nunca se fusiona automáticamente.
UMBRAL_DUPLICADO = 0.55

# Vulnerabilidad efectiva (la confirma la persona en la revisión; ver services/prioritization.py)
VULN_SERVICIO_ESENCIAL = 1.0     # hospital/centro de salud/escuela confirmado en un reporte del sector
VULN_PERSONAS_VULNERABLES = 0.75  # adultos mayores, niños pequeños, enfermos mencionados y confirmados

# Trazas técnicas JSONL (distintas de la auditoría de negocio)
TRACE_PATH = Path(os.environ.get("AGUA_CLARA_TRACE", BASE_DIR / "logs" / "trazas.jsonl"))

# Envío duplicado accidental: mismo texto en menos de N segundos => se devuelve el reporte ya creado
IDEMPOTENCIA_SEGUNDOS = 30

# Duplicados: ventana en la que un reporte nuevo sigue "pareciendo el mismo incidente"
VENTANA_DUPLICADO_HORAS = 72

# Sectores sin reportes en este lapso se consideran "sin reportes recientes"
VENTANA_REPORTES_RECIENTES_HORAS = 72


def _env(nombre: str, defecto: str = "") -> str:
    return os.environ.get(nombre, defecto).strip()


# --- IA (Gemini opcional) -------------------------------------------------------------------
# AI_PROVIDER: "auto" (por defecto) usa Gemini SOLO si hay GEMINI_API_KEY; "gemini" lo fuerza;
# "local" desactiva todo envío externo (reglas deterministas). Si Gemini falla se usa el modo local
# y queda registrado; nunca se presenta el resultado local como si fuera de Gemini.
GEMINI_MODELO_POR_DEFECTO = "gemini-3.5-flash-lite"  # según ai.google.dev/gemini-api/docs/models (verificar; cambia con GEMINI_MODEL)


def ai_provider() -> str:
    """Proveedor efectivo: 'gemini' o 'local'."""
    p = _env("AI_PROVIDER", "auto").lower()
    if p == "auto":
        return "gemini" if GEMINI_API_KEY() else "local"
    return "gemini" if p == "gemini" else "local"


GEMINI_API_KEY = lambda: _env("GEMINI_API_KEY")  # noqa: E731
GEMINI_MODEL = lambda: _env("GEMINI_MODEL", GEMINI_MODELO_POR_DEFECTO)  # noqa: E731
AI_TIMEOUT_SECONDS = lambda: float(_env("AI_TIMEOUT_SECONDS", "15"))  # noqa: E731
AI_MAX_REINTENTOS = lambda: int(_env("AI_MAX_REINTENTOS", "1"))  # noqa: E731  (solo errores transitorios)

# Autenticación de la API (opcional pero recomendada fuera de localhost).
# Sin token configurado, la API solo acepta peticiones de escritura desde 127.0.0.1.
API_TOKEN = lambda: _env("AGUA_CLARA_API_TOKEN")        # operadores (escritura)  # noqa: E731
DEVICE_TOKEN = lambda: _env("AGUA_CLARA_DEVICE_TOKEN")  # dispositivos (lectura de /estado y confirmaciones)  # noqa: E731
