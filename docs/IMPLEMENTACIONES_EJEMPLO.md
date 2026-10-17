# `IMPLEMENTACIONES_EJEMPLO/` — análisis y decisión

> **Decisión: conservar y documentar; NO integrar al producto en esta entrega.**
> Fecha del análisis: **2026-10-17**. Alcance: solo lectura. Comparación módulo a módulo contra la base real de HIDRO360 (`services/`, `api/`, `interface/`, `models/`, `evaluation/`, `tests/`).

## Qué es

`IMPLEMENTACIONES_EJEMPLO/agua-clara-ai` es un **laboratorio de IA** generado a partir de la idea original (el nombre histórico «Agua Clara AI»). Son **43 archivos, ~6.522 líneas**: una demo FastAPI + SPA embebida con un pipeline de 16 «agentes», el paquete `poseidon_core/` (percepción acústica/visión), `services/` propios y una suite `evals/`.

**Está totalmente aislado del producto:** ningún import, prueba, script ni documento del producto lo referencia. Las únicas coincidencias de «agua_clara» fuera de la carpeta son el nombre del archivo de base de datos (`agua_clara.db`) y una etiqueta interna en `evaluation/impacto.py`; son de **nomenclatura histórica**, no de código.

## Por qué NO se integra (criterios de la rúbrica y de `AGENTS.md` §12)

| Criterio | Verificación |
|---|---|
| ¿Resuelve una necesidad de la rúbrica **no cubierta**? | Casi todo lo que aporta **ya está cubierto** en HIDRO360 (prioridad, plan, avisos, auditoría, ingesta, geoloc, orquestación), y con **mayor calidad** (transacciones, `@requiere_admin`, cadena de hashes). |
| ¿Duplica? | **Sí**: dos priorizadores, dos planificadores, dos sistemas de avisos, dos auditorías, dos trazas, dos extractores, dos geolocalizadores. |
| ¿Tiene pruebas? | **No tiene `tests/`**; su única verificación es su propia suite `evals/` autoevaluada. HIDRO360 tiene **23 archivos** de pruebas. |
| ¿Es explicable en una demo de 5–7 min y sin nuevos riesgos? | Varias piezas **chocan con principios propios**: `poseidon_core/agents.py` promete ETA («llegará en X minutos»), contra `AGENTS.md` §5.7 («sin promesas de hora de llegada»); `memory.jsonl` y `poseidon/store` escriben **fuera de transacción/auditoría**, contra §5.5. |
| ¿Aporta dependencias nuevas? | `audio_agent`/`multimodal`/`whatsapp_gateway`/`poseidon_core.audio` requieren claves y librerías opcionales (Whisper, Meta, `numpy`/`librosa`). |

## Comparación por módulo (qué hace y si ya está cubierto)

### `agents/` (16 módulos)

| Módulo | Función | ¿Cubierto en HIDRO360? | Decisión |
|---|---|---|---|
| `intake.py` | Parseo del texto ciudadano, inyección, `pii` | **Sí**: `services/ingest.py` | Documentar |
| `geolocation.py` | Sector + duplicados | **Sí**: `services/geoloc.py` + `workflow` | Documentar |
| `prioritization.py` | Fórmula 40/30/30 | **Sí**: `services/prioritization.py` (reglas distintas) | Documentar (mantener el del producto) |
| `planner.py` | Asignación de cisternas | **Sí**: `services/planner.py` | Documentar |
| `verification.py` | Verificación de entrega | **Sí**: eventos de cisterna + `services/fotos.py` | Documentar |
| `communication.py` | Avisos en outbox (no envía) | **Sí**: `services/communication.py` | Documentar |
| `supervisor.py` | Aprobar/editar/rechazar con motivo | **Sí**: `workflow.decidir_plan()` + auditoría | Documentar |
| `guardrails.py` | Anti-inyección, ráfagas, fuera de zona | **Sí**: `ingest` + `services/limites.py` | Documentar |
| `orchestrator.py` | Orquestación con traza y fallback | **Sí y más estricto**: `services/orquestador.py` + `workflow_ia.py` | Documentar (la *narrativa* del panel inspira la demo) |
| `estimator.py` | **Sesgo de visibilidad (`p_cut`)** | **No**: el producto solo clasifica «sin reportes ≠ sin necesidad» | **Candidato nº 1 (post-reto)** |
| `typo_normalizer.py` | Corrección de jerga/erratas | Parcial: `services/textutil.py` | Documentar |
| `location_resolver.py` | Landmarks coloquiales («detrás del hospital») | Parcial: `geoloc` solo reconoce nombres de sector | **Candidato (post-reto)**, costo bajo |
| `multimodal.py` | Extracción de contenido de imágenes | **No**: el producto solo valida/almacena fotos | **Candidato (post-reto, requiere clave)** |
| `audio_agent.py` | Nota de voz → transcripción | **No** | **Candidato (post-reto, requiere clave)** |
| `whatsapp_gateway.py` | Webhook de WhatsApp | **No** (el producto expone REST) | **Candidato (post-reto, requiere claves Meta)** |
| `consensus.py` | Índice de consenso / antispam de campañas | **No** (solo dedup Jaccard) | **Candidato (post-reto)** |

### `poseidon_core/` (percepción acústica/visión + enjambre)

| Módulo | Función | Decisión |
|---|---|---|
| `audio.py` | Clasifica sonido «aire/seco/normal» (FFT) | Documentar; integrar solo si el reto lo exige |
| `vision.py` | Clasifica imagen por color + visión opcional | Documentar |
| `store.py` | Almacén JSONL append-only | Documentar (el producto usa SQLite con transacciones) |
| `agents.py` | **Enjambre** que promete ETA | Documentar; **no** integrar (choca con «sin promesas de hora») |
| `route.py` | Router `/poseidon/*` | Documentar (solo junto con `audio.py`) |

### `services/` (del ejemplo)

| Módulo | Función | Decisión |
|---|---|---|
| `storage.py` | SQLite + cadena de hashes | Documentar (el producto tiene mejor cobertura) |
| `traces.py` | Trazas JSONL **sin** cadena de hashes | Documentar (el producto **sí** la tiene) |
| `metrics.py` | `deprivation` (Holguín-Veras), `gini`, cobertura **Sphere 15 L** | **Candidato**: refuerzo directo de equidad (~40 líneas) |
| `catalog.py` | Catálogo JSON | Documentar (salvo `landmarks`) |
| `llm.py` | Cadena multi-proveedor por `urllib` | Documentar (idea rescatable) |
| `memory.py` | Memoria operativa que «aprende» | Documentar; integrar solo si cada escritura se audita |

### `evals/` (del ejemplo)

`cases.py` (35 casos), `harness.py`, `run_evals.py`. **Documentar**: el producto ya tiene `evaluation/` (casos de la guía + adicionales) y `pytest` (23 archivos), con PASS/FAIL/**NEEDS_REVIEW** y experimento sintético. Se pueden **tomar ideas** de casos (audio, campañas, jerga).

### Raíz y `data/`

`app.py` (demo FastAPI+SPA), `config.py`, `schemas.py`, `README.md`, `requirements.txt`: **documentar** (tecnología distinta; el producto usa Flet). Se pueden **tomar ideas de narrativa** (panel «¿por qué este orden?», visor de agentes, gráfico barras-vs-necesidad).

`BITACORA_IA.md` (bitácora de uso de IA) y `data/landmarks.json` / `data/seed_corpus.json`: **ideas adoptables** (el formato de bitácora ya se adoptó en `docs/BITACORA_IA.md`).

## Capacidades del laboratorio que el producto NO tiene (banco post-reto)

1. **Sesgo de visibilidad (`p_cut`)** — `agents/estimator.py`.
2. **`deprivation` y cobertura Sphere (15 L)** — `services/metrics.py`.
3. **Landmarks coloquiales** — `agents/location_resolver.py` + `data/landmarks.json`.
4. **Consenso / antispam de campañas** — `agents/consensus.py`.
5. **Multimodal (imagen)** — `agents/multimodal.py`.
6. **Audio / notas de voz** — `agents/audio_agent.py`.
7. **Canal WhatsApp** — `agents/whatsapp_gateway.py`.

> Que una capacidad exista aquí **no la convierte en funcionalidad de HIDRO360** (regla del proyecto). Cualquier integración futura debe pasar sus pruebas y respetar los principios (IA propone, reglas calculan, humano aprueba, todo auditado).

## Discrepancias detectadas en el laboratorio (no se corrigen aquí; se documentan)

- Recuento de casos inconsistente: `BITACORA_IA.md` dice 20; `README.md`/`app.py`/`cases.py` dicen 35; `harness.py` dice 30.
- Cero pruebas unitarias (solo `evals/` autoevaluada).
- Trazas sin cadena de hashes.
- Conflictos de principio: ETA en `poseidon_core/agents.py`; escrituras fuera de transacción en `memory.jsonl` y `poseidon/store`.

## Conclusión

El laboratorio **no se ejecuta ni se importa** en la entrega. Su valor es (1) **narrativa** para la demo y (2) **banco de 7 capacidades** para un trabajo posterior al reto. Se conserva íntegro como evidencia del proceso (ver `docs/INVENTARIO_TECNICO.md`).
