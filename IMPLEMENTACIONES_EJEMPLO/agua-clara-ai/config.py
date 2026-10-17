"""Configuración y utilidades comunes (lectura de .env sin dependencias)."""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "agua_clara.sqlite"
TRACE_PATH = DATA_DIR / "traces.jsonl"
OUTBOX_DIR = DATA_DIR / "outbox"
UPLOADS_DIR = ROOT / "uploads"
TRACES_DIR = ROOT / "traces"
EVALS_DIR = ROOT / "evals"

for d in (DATA_DIR, TRACES_DIR, EVALS_DIR, UPLOADS_DIR, OUTBOX_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _load_dotenv() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def pseudonymize(value: str, salt: str = "agua-clara-demo") -> str:
    """Teléfono/remitente -> hash irreversible (privacidad)."""
    return hashlib.sha256((salt + "|" + value).encode("utf-8")).hexdigest()[:16]


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def llm_available() -> bool:
    return bool(env("AGUA_LLM_API_KEY"))


# Nuevos flags (opcionales, no rompen demo)
def _bool(key: str, default: bool = False) -> bool:
    v = env(key)
    if not v:
        return default
    return v.lower() in ("1", "true", "yes", "y", "on")


MULTIMODAL_ENABLED = _bool("MULTIMODAL_ENABLED", True)
MULTIMODAL_MAX_MB = int(env("MULTIMODAL_MAX_MB", "10")) if env("MULTIMODAL_MAX_MB") else 10
AUDIO_TRANSCRIBE_VIA_LLM = _bool("AUDIO_TRANSCRIBE_VIA_LLM", True)
IMAGE_OCR_VIA_LLM = _bool("IMAGE_OCR_VIA_LLM", True)

LLM_MODEL = env("AGUA_LLM_MODEL", "gpt-4o-mini")
LLM_BASE_URL = env("AGUA_LLM_BASE_URL", "https://api.openai.com/v1")
try:
    LLM_TEMPERATURE = float(env("AGUA_LLM_TEMPERATURE", "0.1"))
except Exception:
    LLM_TEMPERATURE = 0.1
try:
    LLM_TIMEOUT_SEC = int(env("AGUA_LLM_TIMEOUT_SEC", "30"))
except Exception:
    LLM_TIMEOUT_SEC = 30
try:
    LLM_MAX_TOKENS = int(env("AGUA_LLM_MAX_TOKENS", "4096"))
except Exception:
    LLM_MAX_TOKENS = 4096

SECTORS_SILENT_SAMPLE_PCT = 0.20
SECTORS_SILENT_MIN_SAMPLES = 3
MIN_GPS_ACC_M = 1000


# ---------------------------------------------------------------------------
# Proveedores de LLM (cadena de intentos). La primera clave disponible gana.
# Todo es opcional: sin claves la demo funciona 100% con reglas deterministas.
# ---------------------------------------------------------------------------
XAI_API_KEY = env("XAI_API_KEY")                              # xAI / Grok
XAI_BASE_URL = env("XAI_BASE_URL", "https://api.x.ai/v1")
XAI_MODEL = env("XAI_MODEL", "grok-4")
XAI_VISION_MODEL = env("XAI_VISION_MODEL", "grok-4")

OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_BASE_URL = env("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_TRANSCRIBE_MODEL = env("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")

GEMINI_API_KEY = env("GEMINI_API_KEY")
GEMINI_BASE_URL = env("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
GEMINI_MODEL = env("GEMINI_MODEL", "gemini-2.5-flash")

# Compatibilidad: la clave genérica histórica (AGUA_LLM_*). Se usa como proveedor
# "genérico" si no hay xAI/OpenAI/Gemini específicos.
LLM_API_KEY = env("AGUA_LLM_API_KEY")

# ---------------------------------------------------------------------------
# Canal WhatsApp (webhook). Sin token real, los mensajes quedan en la bandeja
# de salida. Con token, se pueden enviar respuestas reales.
# ---------------------------------------------------------------------------
WHATSAPP_VERIFY_TOKEN = env("WHATSAPP_VERIFY_TOKEN", "agua-clara-demo")
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_ID = env("WHATSAPP_PHONE_ID")
WHATSAPP_MEDIA_DIR = UPLOADS_DIR / "whatsapp"
WHATSAPP_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Agentes nuevos (Lindy-style): canal, jerga, audio, ubicación ambigua, consenso.
# ---------------------------------------------------------------------------
AGENT_LEARNING_ENABLED = _bool("AGENT_LEARNING_ENABLED", True)
CONSENSUS_MIN_SOURCES = 3
VAGUE_LOCATION_MARKERS = [
    "no se donde vivo", "no sé dónde vivo", "no se donde es", "por ahi", "por ahí",
    "cerca de", "detras de", "detrás de", "al lado de", "frente a", "por el",
    "donde", "aqui", "aquí", "barriada", "barrio", "no se como explicar",
    "no sé cómo explicar", "creo que", "mas o menos", "más o menos",
]
