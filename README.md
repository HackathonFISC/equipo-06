# Agua Clara AI — MVP local

Agua Clara AI es un sistema de coordinación para la respuesta a reportes de falta de agua, orientado a asignar cisternas con **supervisión humana** en cada paso.

- **Problema que aborda**: coordinar reportes sobre falta de agua, detectar posibles duplicados, priorizar sectores y proponer asignaciones de cisternas sin automatizar decisiones sensibles.
- **A quién ayuda**: equipos que reciben reportes de la comunidad y necesitan tomar decisiones fundamentadas sobre el uso limitado de cisternas de agua.
- **Estado actual**: versión demo funcional de forma **100% local**. Funciona con Python, SQLite, Streamlit y FastAPI. Todos los datos incluidos en la demo son **ficticios**.
- **Principios**: determinista (sin IA externa), supervisión humana obligatoria, texto original conservado, auditoría inmutable con encadenamiento de hashes, sin promesas sobre horarios de llegada.

## Estado actual

- **Funciona**: ingestión de reportes desde texto libre (reglas), revisión y corrección humana, sugerencia de duplicados (nunca fusiona), cálculo de prioridad por sector (máximo entre reportes, no suma de quejas), planificador por capacidad/disponibilidad, borradores de comunicación (sin envío automático), auditoría append-only verificable, interfaz Streamlit, API REST para dispositivos futuros.
- **En desarrollo**: integración con Raspberry Pi 4 y ESP32-S3 (solo contratos definidos), mejoras a la edición del plan, autenticación para responsables y dispositivos.
- **No implementado**: envío de mensajes, rutas/distancias/tiempos de llegada, sensores/firmware, IA para extracción (aunque hay interfaz `Interprete` lista para extenderse).

## Funciones implementadas (seis roles)

1. **Ingesta (services.ingest)** — Extrae información del texto libre con reglas offline. Conserva el `mensaje_original`, marca `datos_faltantes` e `incertidumbre`, nunca inventa valores. Admite estimaciones documentadas (ej.: familias×4). Interfaz `Interprete` permite reemplazarlo por IA en el futuro sin afectar lógica de negocio.
2. **Geolocalización y deduplicación (services.geoloc)** — Resuelve sector contra catálogo local, calcula similitud para sugerir duplicados entre reportes del mismo sector. **Nunca** fusiona automáticamente; la decisión (sí/no duplicado) la toma una persona. Sugerencias se marcan como `dudoso`.
3. **Priorización (services.prioritization)** — Puntaje 0-100 determinista: `puntaje = 100*(0.40*horas + 0.30*población + 0.30*vulnerabilidad)`. Cada factor normalizado a [0,1]. **Por sector se toma el máximo** de horas y personas entre reportes confirmados (no suma). Reportes marcados como duplicados no se cuentan. Categorización según `config.CATEGORIAS`.
4. **Planificación (services.planner)** — Recorre sectores por prioridad desc y asigna litros de cisternas **disponibles**, sin superar `litros_disponibles`. Prefiere cisternas con `sector_base` igual al sector, luego las de mayor disponibilidad. Puede usar varias cisternas por sector. Genera sectores **pendientes** con motivo cuando no alcanza. No calcula rutas ni horas.
5. **Comunicación (services.communication)** — Redacta **borradores** informativos. No envía nada, no promete hora de llegada, incluye marca "BORRADOR - no enviado. Requiere revisión humana antes de cualquier uso".
6. **Supervisión humana + Auditoría (services.audit + workflow)** — Todas las acciones relevantes se registran en bitácora append-only con `hash_previo` y `hash` propio (encadenamiento). `verificar_integridad()` detecta alteraciones. La interfaz obliga a responsable, motivos cuando corresponda, y audita ediciones (antes/después), aprobaciones/rechazos.

## Flujo (desde reporte hasta decisión humana)

1. **Reporte** (tab 1): usuario ingresa texto → `workflow.crear_reporte()` guarda texto original + extracción por reglas (queda `por_revisar`).
2. **Revisar datos** (tab 2): revisar/corregir sector, horas, personas, severidad, calle. Confirmar exige sector válido del catálogo. Rechazar exige motivo.
3. **Ubicación y duplicados** (tab 3): muestra datos del sector, mapa si hay coordenadas, y candidatos de duplicados. El operador decide Sí/No; **nada se fusiona**.
4. **Prioridad** (tab 4): muestra prioridades por sector con desglose de factores, razones, reportes considerados y `reportes_contados` (informativo).
5. **Plan y aprobación** (tab 5): `generar_plan()` calcula asignaciones y pendientes. Tabla editable solo para plan `propuesto`: cambiar `litros` (0 = quitar), reasignar `cisterna_id` (de las disponibles). Guardar modificaciones exige motivo; aprobar plan editado exige comentario. Rechazar exige motivo. **No envía nada**. Borradores visibles.
6. **Auditoría** (tab 6): bitácora con responsable, fecha, acción, entidad/id, motivo, detalle JSON y verificación de integridad.

## Tecnologías utilizadas

- **Python 3.10+**
- **Streamlit** >=1.38 (interfaz solo presentación)
- **Pydantic** >=2.9 (contratos/validación)
- **FastAPI** >=0.110 + **Uvicorn** >=0.29 (API REST)
- **SQLite** (stdlib) — base única `agua_clara.db`, sin ORM
- **Pytest** >=8, **httpx** >=0.27 (pruebas API/UI)

## Requisitos previos

- Python 3.10 o superior
- pip
- Entorno virtual (recomendado)
- Sistema Windows, Linux o macOS (comandos indicados para Windows en la demo; válidos también en Unix)

## Instalación

```bash
# Crear y activar entorno virtual
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
# source .venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Configuración

Archivo: [`config.py`](config.py)

Parámetros configurables (deterministas, visibles):
- `DB_PATH`: ruta SQLite. Por defecto `agua_clara.db` en raíz; se puede sobrescribir con variable de entorno `AGUA_CLARA_DB`.
- Pesos/factores prioridad: `PESO_HORAS=0.40`, `PESO_POBLACION=0.30`, `PESO_VULNERABILIDAD=0.30`, `HORAS_TOPE=96`, `PERSONAS_TOPE=300`, `VULNERABILIDAD_VALORES` (`baja/media/alta/crítica`).
- `LITROS_POR_PERSONA=15`, `CATEGORIAS=[(70,"CRÍTICA"),(50,"ALTA"),(30,"MEDIA"),(0,"BAJA")]`.
- `UMBRAL_DUPLICADO=0.55` (sugerencias; nunca fusiona).
- `INTERPRETE="reglas"` (interfaz `Interprete` disponible para extensión con IA).

**No requiere claves, tokens ni credenciales**. No hay archivos `.env` con secretos en el repo; si se crea uno, debe mantenerse fuera de control de versiones (ver `.gitignore`).

## Cómo iniciar la aplicación

**Interfaz Streamlit (principal):**
```bash
streamlit run app.py
```
Abre: [http://localhost:8501](http://localhost:8501)

**API REST (opcional, para dispositivos futuros):**
```bash
uvicorn api.main:app --port 8000
```
Documentación interactiva: [http://localhost:8000/docs](http://localhost:8000/docs)

La base `agua_clara.db` se crea automáticamente al primer uso. Para reiniciar con demo, usar el botón "Cargar / reiniciar datos de ejemplo" en la barra lateral de Streamlit.

## Cómo probar la demo

Con datos ficticios cargados ([`data/datos_ficticios.py`](data/datos_ficticios.py)): 16 reportes, 14 sectores, 6 cisternas. Demanda estimada ~16 900 L vs ~11 500 L disponibles → **habrá sectores pendientes**.

Recorrido recomendado (≈5 min):
1. **Cargar demo**: barra lateral → *Cargar / reiniciar datos de ejemplo* (reportes quedan `por_revisar`).
2. **Ingresar reporte** (tab 1): puede escribir uno nuevo o usar existentes. Al procesar, se guarda texto original.
3. **Revisar datos** (tab 2): confirmar cada reporte activo (sector obligatorio). Reporte #16 no trae sector → elegir del catálogo. Solo reportes `confirmados` cuentan para prioridad/plan.
4. **Ubicación y duplicados** (tab 3): revisar candidatos (ej. #1–#3 La Chorrera pueden sugerirse como duplicados). Decidir Sí/No.
5. **Prioridad** (tab 4): verificar puntajes, desglose, razones (quejas repetidas **no** suben puntaje).
6. **Plan y aprobación** (tab 5): *Generar propuesta*. Editar litros/cisterna_id (0=quitar) → *Guardar modificaciones* (motivo). Luego *Aprobar* o *Rechazar* (rechazar exige motivo). Ver borradores (no enviados).
7. **Auditoría** (tab 6): verificar cadena íntegra.

## Estructura del proyecto

```
app.py                    # Punto de entrada Streamlit
config.py                 # Configuración determinista
requirements.txt          # Dependencias
agua_clara.db             # SQLite local (se crea/usa en runtime)

api/
  main.py                 # FastAPI: /api/v1/estado, /api/v1/planes, /api/v1/dispositivos/confirmaciones, /api/v1/auditoria...

data/
  database.py             # Acceso SQLite (crud minimal)
  datos_ficticios.py      # Datos demo ficticios

interface/
  streamlit_app.py        # UI (solo presentación; lógica en workflow)

models/
  schemas.py              # Pydantic: contratos estables (SCHEMA_VERSION 1.0). Incluye estados, prioridad, plan, auditoría, contratos dispositivos

services/
  ingest.py               # Módulo 1: ingestión por reglas + Interprete
  geoloc.py               # Módulo 2: sector + sugerencia duplicados (no fusiona)
  prioritization.py       # Módulo 3: prioridad determinista (máximo por sector)
  planner.py              # Módulo 4: asignación por capacidad/disponibilidad
  communication.py        # Módulo 5: borradores (sin envío)
  audit.py                # Módulo 6: auditoría append-only con hashes
  workflow.py             # Orquestador (única puerta UI/API)
  textutil.py             # Normalización y palabras clave

tests/
  conftest.py             # Fixture BD temporal para tests
  test_flujo.py           # Tests de lógica (ingesta, duplicados, prioridad, plan, auditoría, API)
  test_ui.py              # Recorrido UI con Streamlit testing

INFO DEL PROYECTO/        # Documentación PDF del proyecto (referencia)
```

## Datos, privacidad y auditoría

- **100% local**: sin internet, sin llamadas a APIs externas, sin claves/tokens.
- **Datos ficticios en demo**: ver [`data/datos_ficticios.py`](data/datos_ficticios.py).
- **Texto original conservado**: [`Reporte.mensaje_original`](models/schemas.py) nunca se modifica.
- **No se fusionan duplicados**: solo se registra decisión humana ([`decisiones_duplicado`](data/database.py), [`workflow.resolver_duplicado`](services/workflow.py)).
- **Auditoría inmutable**: cada entrada guarda hash previo + hash calculado con cuerpo serializado ([`services/audit.py`](services/audit.py)). `verificar_integridad()` comprueba encadenamiento.
- **Privacidad**: responsable se pide por operación (no hay autenticación aún); datos personales mínimos. Ver `.gitignore` para exclusión de DB/archivos locales.

## API para dispositivos futuros (`/api/v1`)

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/salud` | Estado básico + `schema_version` |
| GET | `/estado` | `plan_aprobado`, `plan_pendiente_de_revision`, `reportes_activos`, `cisternas` ([`EstadoActual`](models/schemas.py)) |
| GET | `/cisternas` | Catálogo de cisternas |
| GET | `/reportes` | Lista de reportes |
| GET | `/planes` | Lista de planes |
| GET | `/planes/{id}` | Detalle de plan |
| POST | `/dispositivos/confirmaciones` | Publica confirmación (`dispositivo_id`, `plan_id`, `tipo`, `cisterna_id?`, `detalle`). **Solo audita**; no modifica plan. Requiere plan `aprobado`. |
| GET | `/auditoria` | Verifica integridad + lista de entradas (filtrable por `entidad`, `entidad_id`) |

**Notas API:** Sin autenticación aún (destinado a red local de pruebas). Contratos definidos en [`models/schemas.py`](models/schemas.py) (`ConfirmacionDispositivo`, `EstadoActual`, `SCHEMA_VERSION="1.0"`).

## Limitaciones conocidas y trabajo pendiente

- **Hardware**: no hay Raspberry Pi 4 ni ESP32-S3 ejecutando código en esta etapa. Solo contratos para futura integración (Raspberry Pi como servidor local con SQLite; ESP32-S3 cliente HTTP).
- **Autenticación**: faltan login de responsables y token/identificación por dispositivo antes de exponer API fuera de pruebas.
- **Extracción**: reglas regex limitadas; interfaz `Interprete` lista para IA futura. Algunos casos ambiguos requieren corrección humana (comportamiento intencional).
- **Plan**: edición actual permite cambiar/reasignar/quitar (litros=0), pero no agregar nuevas asignaciones desde UI de forma libre en todos los casos — mejorar tabla de edición.
- **Geografía**: hay coordenadas en demo pero no se usan para distancia/rutas/costos; deliberadamente fuera de alcance (no se prometen horas/llegadas).
- **Datos reales**: catálogo sectores/cisternas es ficticio; requiere validación con expertos para uso real.

## Colaboración y contribuciones

1. Crear entorno virtual e instalar dependencias.
2. Ejecutar tests: `pytest -q` (usa BD temporal).
3. Probar UI: `streamlit run app.py`.
4. Seguir principios: determinista, supervisión humana, sin inventar datos, conservar texto original, auditar cambios.
5. Mantener contratos estables en `models/schemas.py` (incrementar `SCHEMA_VERSION` si cambian campos).
6. No incluir datos sensibles, claves o `agua_clara.db` real en commits.

## Equipo

**TEAM VIFY AI** — Frida Leis, Yohany Kavacila y Victor Montes

**Nota**: Este README refleja únicamente lo que está implementado y confirmado en el código. Las partes no implementadas se marcan explícitamente como pendientes.