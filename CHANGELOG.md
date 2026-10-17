# Changelog

## 0.6.0 — 2026-10-17 (MVP integrado: fotos, mapa, IA orquestada, flota)
### Añadido
- Reportes con **coordenadas reales** (mapa) y hasta 3 **fotos** validadas por firma binaria, guardadas en `HIDRO360_MEDIA_DIR` (fuera de Git); solo el administrador las ve.
- **Flota**: un token por vehículo (`X-Device-Token`, solo se guarda el hash), misiones con paradas, eventos de terminal idempotentes por `uid`, `/api/v1/mapa`.
- **Orquestación IA** (`services/orquestador.py`, `workflow_ia.py`): validación → duplicados → clasificación → prioridad → recomendación → asignación; procedencia por etapa (`gemini`/`reglas`/`reglas(fallback)`); la misión solo nace con aprobación humana.
- Interfaz: mapa en el formulario y en administración, fotos, «Recomendaciones IA», «Misiones y flota».
- Firmware de terminal de cisterna (misión, botones táctiles, cola de eventos en NVS, reintentos); compila con `arduino-cli`; `scripts/simular_terminal.py`.
- Raspberry: `requirements-servidor.txt`, `install.sh` idempotente, usuario sin privilegios, datos en `/var/lib/hidro360`, timer de copias, `hidro360-cli.sh`.
- Prueba extremo a extremo con servidor uvicorn real y reinicio (`tests/test_e2e.py`).
### Cambiado
- Variables `HIDRO360_*` (alias `AGUA_CLARA_*` obsoletos). SCHEMA_VERSION 1.3.
### Conocido
- Gemini real y Raspberry/systemd sin probar; firmware sin probar en placa.

## 0.5.0 — 2026-10-17 (reorganización y roles)
### Cambiado
- **Nombre oficial HIDRO360** (equipo TEAM VIFY AI) en interfaz, configuración, documentación, deploy y firmware. Las variables de entorno conservan el prefijo `AGUA_CLARA_` por compatibilidad.
- **Interfaz separada en dos experiencias**: portal público (reportar, consultar con código de seguimiento, avisos) y consola de administración tras login (`interface/flet_app/portal/` y `admin/`). Las herramientas técnicas (trazas, evaluación, verificación de Gemini, carga de datos ficticios) viven en «Diagnóstico y desarrollo», solo para administradores.
- Servicios systemd de la Raspberry renombrados a `hidro360-*`.
### Añadido
- **Autenticación y roles** (`services/auth.py`): scrypt con sal, sesiones con hash, bloqueo por intentos, sin cuentas por defecto (`python -m scripts.crear_admin`). Autorización en el backend (`@requiere_admin`) y en cada endpoint de la API; portal público con límites de tasa; `tests/test_auth.py`.
- Tabla de pines del ESP32-S3 con fuentes y correcciones del firmware (aviso de confirmación separado, timeouts).
### Conocido
- Sesiones y límites de tasa en memoria; sin HTTPS ni MFA; firmware sin compilar ni probar en placa; Gemini sin probar con el servicio real.

> Nombre oficial: **HIDRO360** (TEAM VIFY AI); antes «Agua Clara AI». Las entradas históricas conservan el contexto de su fecha.

## Sin versión (en curso)
### Cambiado
- La evaluación funcional fuerza el intérprete local determinista: ya no depende de una clave Gemini configurada en el entorno de quien la ejecuta ni envía sus casos a la red.
- Identidad unificada a HIDRO360: documentación, skills (`.claude/skills/hidro360-*`), servicios systemd (`hidro360-api.service`, `hidro360-ui.service`; rutas `/opt/hidro360`, `/etc/hidro360`, `/var/lib/hidro360`, usuario `hidro360`). Las variables de entorno conservan el prefijo `AGUA_CLARA_` por compatibilidad.
- Firmware ESP32-S3: texto en pantalla HIDRO360; los fallos al confirmar recepción ya no muestran «SIN DATOS» (aviso aparte); `setConnectTimeout`; comprobación de `http.begin`. Sigue sin compilarse ni probarse en placa.
- `docs/HARDWARE.md`: tabla de pines con fuentes; pines libres marcados «no verificado» donde no hay evidencia.

## 0.4.0 — 2026-10-16
### Cambiado
- **Interfaz migrada de Streamlit a Flet 1.0.4** (12 páginas, identidad del prototipo y logo, componentes reutilizables, confirmaciones en acciones sensibles). Streamlit y sus dependencias se retiraron tras verificar la cobertura (`docs/INVENTARIO_ARCHIVOS.md`).
- **Gemini como proveedor de IA** (`google-genai`): `AI_PROVIDER=auto|local|gemini`, `GEMINI_API_KEY`, `GEMINI_MODEL`; fallback local declarado, corte por cuota, reintento prudente, redacción de teléfonos/correos, `scripts/verificar_gemini`. Se retiraron `INTERPRETE` y `LLM_*`.
- `config.py` lee `.env` (sin pisar el entorno). `app.py` arranca Flet (`--web` para navegador).
### Añadido
- Resumen explicable y borrador de comunicación asistidos por IA (validados; informativos).
- `AGENTS.md`, `CLAUDE.md`, 6 skills en `.claude/skills/`, y documentación: `IA_GEMINI`, `DECISIONES`, `DISENO_UI`, `API`, `BASE_DE_DATOS`, `SEGURIDAD`, `INSTALACION`, `PRUEBAS`, `INVENTARIO_ARCHIVOS`.
- `tests/test_flet.py` y `tests/test_gemini.py` (el total vigente lo da `pytest -q`).
### Retirado
- `PANTALLA_DE_MONITOREO/` (librerías idénticas por SHA-256 a las de Arduino; el sketch del LED se conservó en `firmware/pruebas/led_rgb/`).
### Conocido
- Gemini sin probar contra el servicio real; la app de escritorio descarga su cliente de Flet en la primera ejecución; `--web` necesita internet en el navegador; hardware sin probar.

## 0.3.0 — 2026-10-16
### Añadido
- Trazas JSONL con cadena de hashes (`services/tracing.py`) y página «Trazas».
- Ingesta con evidencia, tipo de incidencia, vulnerabilidades y servicio esencial; intérprete LLM opcional con esquema Pydantic estricto, revalidación en código, fallback a reglas y defensa contra prompt injection.
- Sector difuso/ambiguo con opciones para el operador; referencias coloquiales; duplicados con tiempo y tipo de incidencia.
- Máquina de estados en el backend, idempotencia de envío, transacciones SQLite (cambio + auditoría atómicos), API de escritura completa con tokens de operador y dispositivo.
- Planificador por flujo máximo lexicográfico con elegibilidad y capacidad.
- Visibilidad de sectores (sin reportes ≠ sin necesidad), Gini y experimento línea base vs HIDRO360 (datos sintéticos).
- Runner de 15 casos + 7 adicionales (`python -m evaluation.run_cases`).
- Interfaz rediseñada (12 secciones), firmware ESP32-S3 (sin compilar), scripts Raspberry Pi (sin probar), documentación.
### Cambiado
- Prioridad: vulnerabilidad elevada por servicio esencial/personas vulnerables confirmados; aviso de horas contradictorias. Reglas `reglas-2026.10.a`.
- Contrato de esquemas 1.1 (campos nuevos, retrocompatible por lectura).
### Conocido
- Responsable sin autenticación; HTTP sin cifrar; casos de evaluación redactados por el equipo (la guía no los enumera).

## 0.2.0
- MVP local: ingesta por reglas, duplicados sugeridos, prioridad, plan, aprobación, auditoría y API de lectura.
