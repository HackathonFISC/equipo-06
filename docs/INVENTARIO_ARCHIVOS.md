# Inventario de cambios de archivos (migración a Flet + Gemini, 2026-10-16)

> **Nota de cambio de nombre:** documento histórico. El producto se llamaba «Agua Clara AI»; el nombre oficial ahora es **HIDRO360** (TEAM VIFY AI, ver `docs/DECISIONES.md` D-02). El contenido de abajo conserva el nombre y el estado de la fecha en que se escribió (p. ej. rutas `pages/` y Streamlit ya no vigentes).

Respaldo previo a los cambios: zip del árbol (sin `.venv`, `.git`, `Demo/`, librerías) en el directorio temporal de la sesión; el trabajo anterior seguía **sin confirmar en Git**, por lo que ese respaldo era la única red de seguridad para los archivos nuevos.

## Eliminados (con evidencia de que su función está cubierta)
| Archivo / carpeta | Sustituido por | Evidencia |
|---|---|---|
| `interface/streamlit_app.py` | `interface/flet_app/` (12 páginas) | las 12 secciones existen en Flet y 13 pruebas de interacción pasan; `git grep` sin referencias |
| `interface/estilos.py` | `interface/flet_app/theme.py` + `components.py` | solo lo importaba la UI Streamlit |
| `.streamlit/config.toml` | `page.theme` en `main.py` | solo configuraba Streamlit |
| `tests/test_ui.py` (AppTest de Streamlit) | `tests/test_flet.py` | cubre las mismas acciones (bandeja, confirmar, plan, aprobar) invocando los manejadores |
| Dependencias `streamlit`, `pandas` (y `numpy`, `altair`, `pydeck` del venv) | — | `pytest -q`: 77 pasan sin ellas |
| `docs/BITACORA_IA.md` | `docs/IA_GEMINI.md` | contenido ampliado y actualizado |
| `PANTALLA_DE_MONITOREO/libraries/` (354 MB) | `Documentos/Arduino/libraries` | **5564 archivos idénticos por SHA-256**; sin referencias en el código |
| `PANTALLA_DE_MONITOREO/PANTALLA_DE_MONITOREO.ino` | `firmware/pruebas/led_rgb/led_rgb.ino` | copia idéntica (`cmp`); la carpeta quedó vacía |
| Variables `INTERPRETE`, `LLM_*` y el transporte HTTP «compatible OpenAI» | `AI_PROVIDER`, `GEMINI_*`, `services/ia_gemini.py` | Gemini es el proveedor; se evita duplicar configuración |

## Conservados sin cambios
`INFO DEL PROYECTO/` (PDF) · `LOGO/` (original del logo) · `PROTOTIPO/` (referencia visual) · `Demo/` (ejemplos del fabricante, 51 MB, sin versionar: decide el usuario) · `docs/AUDITORIA_TECNICA.md` (historial) · `docs/PLANIFICADOR.md`.

## Creados
`interface/flet_app/` (`main.py`, `contexto.py`, `components.py`, `theme.py`, `pages/` ×12, `__main__.py`) · `assets/logo.jpeg` · `services/ia_gemini.py`, `services/ia_tareas.py` · `scripts/verificar_gemini.py` · `tests/test_flet.py`, `tests/test_gemini.py` · `AGENTS.md`, `CLAUDE.md` · `.claude/skills/` (6 skills) · `firmware/pruebas/led_rgb/` · `docs/` : `IA_GEMINI`, `DECISIONES`, `DISENO_UI`, `API`, `BASE_DE_DATOS`, `SEGURIDAD`, `INSTALACION`, `PRUEBAS`, `INVENTARIO_ARCHIVOS`.

## Modificados
`app.py` (arranca Flet) · `config.py` (`AI_PROVIDER`, `GEMINI_*`, lector de `.env`) · `services/ingest.py` (proveedor Gemini, redacción de PII, fallback) · `services/workflow.py` (explicación/borrador asistidos) · `services/communication.py` (plantilla reutilizable) · `evaluation/casos.py` (caso A2 con la nueva costura) · `api/main.py` (`proveedor_ia` en `/salud`) · `tests/conftest.py`, `tests/test_ingesta.py` · `requirements.txt` · `.env.example`, `deploy/raspberry/*` (servicio de UI Flet) · `README.md`, `CHANGELOG.md`, `docs/ARQUITECTURA.md`, `docs/HARDWARE.md`, `docs/GUION_VIDEO.md`.
