# Auditoría técnica inicial — Agua Clara AI (2026-10-16)

> **Nota de cambio de nombre:** documento histórico. El producto se llamaba «Agua Clara AI»; el nombre oficial ahora es **HIDRO360** (TEAM VIFY AI, ver `docs/DECISIONES.md` D-02). El contenido de abajo conserva el nombre y el estado de la fecha en que se escribió (p. ej. rutas `pages/` y Streamlit ya no vigentes).

## Fuentes revisadas
- `INFO DEL PROYECTO/Agua_Clara_AI_Propuesta.pdf` (8 pp.) y `Agua_Clara_AI_Guia_de_Programacion.pdf` (10 pp.).
- Código del repo (commit `b157006`), `README.md`, carpeta `Demo/` (ejemplos del fabricante de la pantalla) y `PANTALLA_DE_MONITOREO/` (sketch + librerías).

## Hallazgos sobre la rúbrica y los 15 casos
- **No existe una rúbrica con ponderaciones** en los documentos. Lo más cercano: la *lista de aceptación del MVP* (Guía p. 8), los *indicadores de demo* (Propuesta p. 6) y la *definición de terminado* (Guía p. 10).
- **Los 15 casos NO están enumerados**: solo hay su agrupación y el resultado esperado por grupo (Guía p. 8):
  1–4 extracción con faltantes/ambigüedad · 5–7 repetido / parecido-pero-distinto / ubicación ambigua · 8–11 prioridad (horas, población, vulnerabilidad, servicio esencial) · 12–13 capacidad suficiente/insuficiente · 14–15 comunicación y control humano.
- Consecuencia: las **entradas concretas de los 15 casos las redactó el equipo de ingeniería** siguiendo esos grupos; los resultados esperados se derivan de las reglas escritas en la guía (fórmula 40/30/30, capacidad nunca excedida, no fusionar, no enviar sin aprobación). **Pendiente de contrastar** con los casos oficiales si existen en otro documento.
- Indicadores cuantitativos de la Propuesta: % de campos clave bien extraídos, duplicados correctos vs falsos agrupamientos, cumplimiento de capacidad, justificación+registro en el 100 % de decisiones. El runner los calculará.
- La guía define endpoints mínimos (`POST /reports`, `GET /reports`, `POST /reports/{id}/confirm`, `POST /plan`, `POST /plan/{id}/decision`, `GET /audit`) y objetos `Report/Sector/Tanker/Assignment` con campos como `channel`, `confidence`, `evidence`, `eta_minutes`, `stop_order`. El repo actual solo expone lectura + confirmaciones de dispositivo.

## Estado real al inicio
| Área | Estado |
|---|---|
| Ingesta por reglas, texto original, faltantes/inciertos | ✅ hecho (regex; sin evidencia/fragmentos, sin tipo de incidencia, sin LLM) |
| Catálogo + sector | ⚠️ solo coincidencia exacta/alias; sin errores ortográficos ni ambigüedad |
| Duplicados | ✅ sugeridos, sin fusión; ⚠️ sin tiempo ni tipo de incidencia |
| Prioridad determinista | ✅ (no incluye servicio esencial) |
| Planificador | ✅ greedy; ⚠️ sin tope por vehículo ni elegibilidad |
| Aprobación humana | ✅ en `workflow`; ⚠️ la API no la expone y no hay máquina de estados en backend para reportes |
| Auditoría | ✅ cadena de hashes; ⚠️ no es transaccional con el cambio de negocio |
| Trazas JSONL | ❌ |
| Runner de 15 casos | ❌ |
| Sectores invisibles / línea base / Gini | ❌ |
| UI | ✅ funcional, básica (6 pestañas) |
| Idempotencia en envío | ❌ |
| Autenticación | ❌ (el responsable es texto libre) |
| Hardware | ⚠️ `PANTALLA_DE_MONITOREO.ino` solo parpadea el LED RGB (pin 42); sin cliente HTTP |

## Pruebas iniciales
`pytest -q` → **10 passed** (flujo, API, UI con AppTest). Dependencias instaladas en `.venv` (Python 3.14); sin `ortools` instalado.

## Operación sin internet
La demo básica no requiere red ni claves. Streamlit/FastAPI/SQLite son locales.

## Hardware
- `Demo/` contiene los ejemplos oficiales del fabricante (Simple_test, display_graphics, RGB_LED, etc.).
- `PANTALLA_DE_MONITOREO/libraries/` (354 MB) son librerías **ya descomprimidas** (TFT_eSPI, lvgl, ESP32_Display_Panel, ArduinoJson…). Cada una tiene `library.properties` en su raíz (estructura válida). Una carpeta `libraries` **dentro del sketch no es leída** por Arduino IDE: las librerías deben estar en `<Sketchbook>/libraries/`. Esto se detalla en Fase 8.
- Esa carpeta no debe versionarse (354 MB).

## Estado tras la evolución (0.3.0)
- `pytest -q`: 50 passed. `python -m evaluation.run_cases`: 22 PASS / 0 REVIEW / 0 FAIL (casos redactados por el equipo; no es la evaluación oficial).
- Implementado: trazas JSONL, ingesta con LLM opcional + fallback + anti-inyeccion, sector difuso/ambiguo, maquina de estados y transacciones en backend, API de escritura con tokens, planificador por flujo, visibilidad de sectores, Gini y experimento sintetico, UI de 12 secciones, docs.
- Sin verificar: firmware ESP32-S3 (no compilado), scripts Raspberry Pi (no probados), modo LLM contra un proveedor real, autenticacion de usuarios.
