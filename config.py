"""
Configuración de Agua Clara AI.
Todo es local: sin internet, sin claves, sin hardware.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).parent

# Base de datos SQLite local (se puede cambiar con AGUA_CLARA_DB, p. ej. para pruebas)
DB_PATH = Path(os.environ.get("AGUA_CLARA_DB", BASE_DIR / "agua_clara.db"))

APP_NAME = "Agua Clara AI"
APP_VERSION = "0.2.0-mvp"

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

# Interpretación de texto: solo "reglas" (offline). Un intérprete con IA puede
# añadirse luego implementando services.ingest.Interprete; la prioridad y el
# plan seguirán siendo deterministas.
INTERPRETE = "reglas"
