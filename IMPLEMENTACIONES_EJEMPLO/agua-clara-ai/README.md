# Agua Clara AI — MVP de demostración

**Team VIFY AI:** Frida Leis · Yohany Kavacila · Victor Montes

Agua Clara AI convierte reportes ciudadanos dispersos (WhatsApp, texto, voz, fotos) en un plan de reparto de cisternas **justo, explicable, trazable y supervisado por humanos**. El modelo interpreta las entradas variables; el código determinista calcula puntajes, restricciones y verifica decisiones.

## 1. Problema que resuelve

En Arraiján y La Chorrera, los reportes de cortes de agua llegan dispersos y duplicados. Los sectores con menos presencia en redes (menor propensión a reportar) quedan invisibles y la atención suele favorecer a quien más reclama. El reto (Reto 1: Agua) pide pasar de un caos de reportes a una coordinación basada en datos, con **humano en el ciclo** y **trazabilidad**.

## 2. Principio de diseño

- **IA interpreta; reglas deciden.** El LLM extrae campos a JSON y redacta avisos sobre plantillas. Puntajes, rutas, asignaciones y verificación son **código puro y determinista**.
- **Silencio ≠ ausencia de problema.** El sistema corrige el **sesgo de visibilidad**: un sector con cero reportes mantiene su probabilidad previa de corte; cada reporte de un sector poco visible pesa más.
- **Ninguna acción automática.** Todo plan nuevo requiere **aprobación explícita** del coordinador; los avisos solo se generan tras la aprobación.
- **Datos como prueba, no certeza.** Cada campo incierto se marca; si faltan datos, el sistema pide aclaración en lugar de inventar.
- **Privacidad por defecto.** Teléfonos se pseudonimizan (hash SHA-256), solo se guarda lo mínimo.

## 3. Arquitectura multiagente

Cumple los 7 requisitos obligatorios con 6 agentes funcionales orquestados por un pipeline, más una **capa de canal y percepción** (WhatsApp, normalización de jerga/erratas, audio, resolución de ubicaciones vagas y consenso anti-campaña) y el módulo **Proyecto Poseidón** de percepción hidráulica pasiva (acústica + visión):

> **Nota de diseño.** El reto admite frameworks como OpenAI Agents, LangGraph, CrewAI o «u otro». Usamos un **orquestador propio** (Python puro, sin dependencias pesadas): cada agente es un módulo con contrato Pydantic, y la comunicación entre agentes es explícita y **trazable paso a paso**. Esto prioriza el determinismo y la auditabilidad sobre la creatividad, como pide el reto, y permite que la demo funcione **100% offline**.

| # | Agente | Rol | Herramientas que actúan | Determinístico |
|---|---|---|---|---|
| A0 | **Pasarela WhatsApp** | Convierte el webhook real de WhatsApp (Meta/Twilio) en mensajes estructurados: texto, imagen, audio, vídeo y ubicación GPS. Encola respuestas de aclaración. | Parseo del webhook, descarga de media, escritura en **outbox**. | Sí |
| A1 | **Ingesta (+ multimodal)** | Transforma texto, **imagen, audio, vídeo o documento** en Report estructurado. Detecta inyección de instrucciones, emergencia médica y ubicación fuera de alcance. | Validación Pydantic; escritura inicial en SQLite; extracción con LLM/Gemini (visión y transcripción) + fallback por regex. | Parcial (LLM opcional) |
| A1b | **Normalizador (jerga y erratas)** | Corrige erratas («bista alegre»→«vista alegre») y entiende jerga panameña («no hay ni gota», «a cada rato»), **aprendiendo de correcciones humanas**. | Memoria operativa `data/memory.jsonl` + corpus semilla. | Sí |
| A1c | **Audio (transcripción)** | Transcribe notas de voz de WhatsApp y extrae horas/personas; si no hay proveedor, **degrada sin romper** y marca campos faltantes. | LLM de audio (xAI/Gemini/OpenAI) o reglas. | Parcial |
| A2 | **Geolocalización + Deduplicación** | Asigna sector vía catálogo local + búsqueda difusa (difflib) + **gacetero de referencias locales**. Agrupa duplicados (no fusiona casos ambiguos). | Catálogo `data/sectors.json`, `data/landmarks.json`, comparación de texto, ventana temporal. | Sí |
| A2b | **Resolutor de ubicaciones vagas** | Si la ubicación es vaga («por ahí cerca», «donde mi mamá»), **no adivina**: genera una **pregunta de aclaración** y marca el reporte `pendiente_confirmacion`. Usa la ubicación GPS de WhatsApp al sector más cercano. | Geolocalización, cálculo de distancia, outbox de respuesta. | Sí |
| A9 | **Consenso anti-campaña** | Índice de consenso por sector: premia fuentes distintas y evidencia (fotos/audio), penaliza ráfagas casi idénticas (posible campaña coordinada). | Conteo ponderado, detección de similitud. | Sí |
| A3 | **Estimador de estado** | Posterior de corte por sector con **corrección de sesgo de visibilidad** (propensión a reportar) y ponderación por fuentes distintas. Propone **muestreo activo** para sectores silenciosos. | Cálculo bayesiano determinista (logit/sigmoid). | Sí |
| A4 | **Priorización** | Puntaje auditable 0.40*horas + 0.30*población + 0.30*vulnerabilidad + bono por servicios críticos. **Cantidad de quejas NO determina prioridad**. | Cálculos puros, razones enumeradas. | Sí |
| A5 | **Planificador** | Asigna cisternas respetando capacidad, turnos, mínimo Sphere (15 L/persona) e instituciones críticas. Incluye **línea base "por quejas"** para comparación. | **Solver determinista propio** (greedy con capacidad); nunca excede capacidad; registra pendientes. | Sí |
| A6 | **Verificador de entrega** | Cruza **GPS, litros del caudalímetro y confirmación comunitaria**. Estados: `confirmada / dudosa / rechazada`. GPS solo no basta. | Reglas deterministas + umbrales, paquete de evidencia (no acusa). | Sí |
| A7 | **Comunicación** | Redacta avisos por barrio sobre plantillas; verifica consistencia numérica. Solo genera tras aprobación. | Escritura en **outbox** (herramienta que actúa); Telegram opcional. | Sí |
| A8 | **Supervisión humana** | Único punto que puede aprobar/editar/rechazar. Revalida ediciones; exige motivo si viola restricciones. Todo queda atribuido. | Registro en auditoría con **cadena de hashes**. | Sí |

### Proyecto Poseidón — percepción hidráulica pasiva (`poseidon_core/`)

Módulo autocontenido e importable que **escucha y mira** la infraestructura para anticipar cortes:

- **Audio (`poseidon_core/audio.py`)** — analiza una nota de voz del grifo. Trocea en ventanas de 1 s y calcula el **Centroide Espectral** y la energía en banda alta: rumor grave (< 600 Hz) = agua circulando; **siseo agudo (> 1500 Hz) = aire comprimido en la red** (corte o maniobra); silencio = sin presión. Devuelve el **segundo exacto** del patrón, la confianza y el estado inferido. Incluye un **generador de muestras sintéticas** para demostrar y evaluar sin grabaciones reales.
- **Visión (`poseidon_core/vision.py`)** — clasifica fotos de tuberías, uniones de PVC o medidores en `seco / aire / flujo_normal`. Usa `openai` (gpt-4o, `response_format=json_object`) si está configurado; si no, el cliente multimodal del proyecto (xAI/Gemini); si no hay proveedor, **degrada a `desconocido`** y deja la imagen para revisión humana (nunca inventa).
- **Enjambre (`poseidon_core/agents.py`)** — `AgenteOrquestadorPanamaOeste` acumula lecturas por sector en una ventana temporal. Cuando un sector (p. ej. Burunga, Vacamonte, La Chorrera) acumula **3+ lecturas consecutivas de “aire”**, activa de forma autónoma un **sub-agente de notificaciones** que **encola** alertas predictivas («el agua llegará a su sector en ~X minutos») por WhatsApp y SMS. Las alertas **nunca se envían solas**: quedan en el outbox, pendientes de aprobación, y cada activación se **audita** con hash encadenado.
- **Persistencia (`poseidon_core/store.py`)** — usa **Supabase** si defines `SUPABASE_URL`/`SUPABASE_KEY` y el paquete `supabase`; si no, cae a la **SQLite** del proyecto (tabla `hydro_reading`). Cualquier fallo de Supabase vuelve a SQLite: la lectura nunca se pierde.


### Herramientas que ejecutan acciones reales
1. **SQLite**: inserción/actualización de reportes, planes, decisiones, entregas, outbox (persistencia real).
2. **Auditoría con hash encadenado**: cada evento guarda `prev_hash + body` → detecta alteraciones.
3. **Trazas JSONL**: un registro por paso (`run_id`, agente, herramientas, decisión, latencia).
4. **Outbox**: aviso queda registrado (y puede enviarse por Telegram si hay credenciales).
5. **Planificador**: ejecuta un solver determinista para asignar recursos.

## 4. Estructura del proyecto

```text
agua-clara-ai/
  app.py                # FastAPI + UI demo (una sola página)
  schemas.py            # Modelos Pydantic (contratos)
  config.py             # Variables de entorno + utilidades
  agents/               # Agentes con límites claros
    intake.py, geolocation.py, estimator.py, prioritization.py,
    planner.py, verification.py, communication.py, supervisor.py,
    guardrails.py, multimodal.py, orchestrator.py,
    whatsapp_gateway.py, typo_normalizer.py, audio_agent.py,
    location_resolver.py, consensus.py
  poseidon_core/        # Proyecto Poseidón (percepción hidráulica pasiva)
    audio.py, vision.py, agents.py, store.py, route.py
  services/             # Persistencia, trazas, métricas, catálogo, LLM, memoria
    storage.py, traces.py, metrics.py, catalog.py, llm.py, memory.py
  evals/                # 35 casos de evaluación + runner (con métricas)
    cases.py, harness.py, run_evals.py
  data/
    sectors.json        # Catálogo demo (Arraiján/La Chorrera)
    landmarks.json      # Gacetero de referencias locales
    seed_corpus.json    # Corpus semilla de aprendizaje (erratas, alias, jerga)
    memory.jsonl        # Memoria operativa (crece con correcciones humanas)
  uploads/              # Adjuntos multimodales de la demo (temporales)
  traces/traces.jsonl   # Trazas por paso (JSONL)
  .env.example
  requirements.txt
  README.md
  .gitignore
```

## 5. Interfaz de demostración (SPA web)

Todo se sirve desde FastAPI en `http://127.0.0.1:8000`. Interfaz de una sola página con barra lateral agrupada:

| Vista | Contenido |
|---|---|
| **Panel** | KPIs (reportes, personas, sectores, integridad de auditoría) + gráficos (reportes por sector, tipos/estados). Botón **Cargar datos demo**. |
| **Reporte ciudadano** | Ingreso **multimodal**: texto + adjunto de **foto, audio, vídeo o documento** (arrastrar y soltar, máx. 10 MB). Muestra qué extrajo la cadena de agentes. |
| **Mapa y grafos** | **Mapa interactivo (Leaflet/OpenStreetMap)** de los sectores con **filtros** por distrito, capa (reportes / necesidad / visibilidad) y búsqueda. Grafos de barras+línea comparando reportes vs. horas sin agua (expone el sesgo de visibilidad). |
| **Bandeja** | Todos los reportes con filtros por estado y tipo. |
| **Canal WhatsApp** | Simulador del **webhook real**: envía texto, imagen, audio, vídeo o ubicación GPS y ve la cadena A0→A1b→A1→A2b→A9 y las respuestas encoladas. |
| **Poseidón · acústica** | Sube una **nota de voz del grifo** o una foto de tubería/medidor. Muestra el **espectro por ventana** (banda alta vs. centroide), el estado hidráulico, y la decisión del **enjambre** con alertas predictivas. Botón de escenario de 3 lecturas. |
| **Aprendizaje** | Estado de la **memoria operativa** (correcciones, alias, jerga), botón **Entrenar** con el corpus semilla e índice de **consenso** por sector. |
| **Planificación** | Genera el plan (método social) y compara contra la línea base «por quejas» (Gini, deprivación, cobertura). |
| **Aprobación HITL** | Aprueba o rechaza con motivo (A8). |
| **Verificación 3 señales** | Simula entregas (correcta, GPS de moto, fantasma, litros imposibles) → veredicto con evidencia. |
| **Agentes IA** | **Grafo de comunicación** interactivo (14 agentes + orquestador); al hacer clic se ve el rol y las herramientas de cada agente, y se puede **animar el flujo** de un reporte real sobre las trazas. |
| **Trazas y auditoría** | Trazas por paso + verificación de la cadena de hashes. |
| **Evaluaciones** | Ejecuta los **35 casos** y muestra **métricas agregadas** (Gini, sectores críticos, cobertura, falsos positivos evitados, sectores silenciosos, memoria aprendida). |

### Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/reports` | Reporte por texto (JSON). |
| POST | `/api/reports/upload` | Reporte **multipart** con archivo (imagen/audio/vídeo/documento) + texto. |
| GET/POST | `/webhook/whatsapp` | **Webhook real** de WhatsApp (verificación GET + recepción POST de Meta/Twilio). |
| POST | `/api/whatsapp/simulate` | Simula un mensaje entrante de WhatsApp (texto/media/GPS). |
| GET | `/api/memory` · POST `/api/train` | Estado de la memoria operativa y entrenamiento con el corpus semilla. |
| GET | `/api/consensus` · `/api/agents` | Índice de consenso por sector y grafo de agentes. |
| GET | `/api/dashboard` | Agregados para panel y mapa. |
| POST | `/api/demo/seed` | Carga la secuencia de demostración (incluye guardrails). |
| POST | `/api/plan` · `/api/plan/decision` | Genera el plan y registra la decisión HITL. |
| GET | `/api/compare` | Método social vs. línea base «por quejas». |
| POST | `/api/delivery/simulate` | Verificación con 3 señales. |
| GET | `/api/traces` · `/api/audit` · `/api/outbox` · `/api/evals` | Trazabilidad, auditoría, avisos y evals. |
| POST | `/poseidon/analizar` · `/poseidon/simular` · `/poseidon/webhook` | Percepción acústica/visual + enjambre (Poseidón). |
| GET | `/poseidon/lecturas` · `/poseidon/sector` | Histórico hidroacústico y estado agregado por barriada. |

## 6. Instalación y ejecución

### Requisitos
- Python 3.9+
- Núcleo: FastAPI, Uvicorn, Pydantic (ver `requirements.txt`)
- **Opcionales** (la app degrada sin ellos): `numpy` (análisis espectral de Poseidón), `librosa`/`soundfile` (decodificar ogg/mp3), `openai` (visión gpt-4o), `supabase` (persistencia en la nube), `ortools` (solver VRP exacto), `requests`.

### Instalación
```bash
cd "C:\Users\Frida Sofia\OneDrive\Documentos\Proyecto predeterminado\agua-clara-ai"
pip install -r requirements.txt
# opcional, para todas las capacidades de Poseidón:
pip install numpy librosa soundfile openai supabase
```

### Configurar variables (opcional)
```bash
copy .env.example .env  # Windows cmd
# editar .env si tienes API de LLM (xAI/Gemini/OpenAI), WhatsApp o Supabase
```

**Nota:** Si no hay ningún proveedor LLM o falla la red, el sistema usa **extracción por reglas + plantillas fijas**, y Poseidón mantiene su **DSP determinista** (numpy) y su generador de muestras. La demo funciona **100% offline**.

Variables relevantes (todas opcionales): `XAI_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` / `AGUA_LLM_*` (cadena de LLM por prioridad), `WHATSAPP_VERIFY_TOKEN`/`WHATSAPP_ACCESS_TOKEN`/`WHATSAPP_PHONE_ID` (webhook real), `SUPABASE_URL`/`SUPABASE_KEY` (lecturas de Poseidón).

### Ejecutar la demo
```bash
uvicorn app:app --reload
# Abrir http://127.0.0.1:8000
```

### Ejecutar los evals (35 casos)
```bash
python -m evals.run_evals
```

Resultado esperado: `35/35 aprobados (100%)`. La suite es **hermética** (base de datos y memoria temporales) e **idempotente**.

## 7. Guion de demo (4 minutos)

| Tiempo | Mostrar | Lo que demostrar |
|---|---|---|
| 0:00–0:30 | Problema + Mapa | «Cargar datos demo»; **mapa interactivo** con filtros por distrito/capa: sectores con muchos reportes vs. silenciosos (grafos barras vs. horas sin agua). |
| 0:30–1:00 | Ingesta (A1) | Procesar reporte coloquial; mostrar campos inciertos, detección de inyección/emergencia médica, modo reglas vs LLM. |
| 1:00–1:30 | Geo+Dedup (A2) y A3 | Ambigüedad de ubicación → pide confirmación; 20 reportes idénticos cuentan como 1 fuente; **corrección de visibilidad** y muestreo activo. |
| 1:30–2:00 | Priorización+Plan (A4+A5) | Por qué un sector va primero (razones enumeradas). Comparar **método social vs línea base "por quejas"** (Gini/deprivación). |
| 2:00–2:30 | Aprobación (A8) + Comunicación (A7) | **Humano aprueba** (no automático); avisos generados solo tras aprobación; auditoría con cadena de hashes. |
| 2:30–3:00 | Verificación (A6) + Evals + Trazas | Entrega con GPS de moto/fantasma → **rechazada** con paquete de evidencia. Ejecutar 35 casos (100%) y ver **métricas** (Gini social vs. base, críticos, cobertura, falsos positivos evitados). Mostrar trazas y cadena íntegra. |
| 3:00–3:30 | **Canal WhatsApp + Aprendizaje** | Enviar un mensaje vago → el sistema **pregunta** en vez de adivinar. Enseñar una corrección y ver cómo la próxima vez ya resuelve. Índice de **consenso** (real vs. campaña). |
| 3:30–4:00 | **Poseidón (acústica)** | Subir la **nota de voz del grifo**: el espectro identifica **aire en la tubería** (siseo >1500 Hz) vs. agua. Ejecutar el **escenario de 3 lecturas** → el enjambre **encola alertas predictivas** («el agua llega en ~X min»), pendientes de aprobación humana. |

## 8. Validación rápida

```bash
cd "C:\Users\Frida Sofia\OneDrive\Documentos\Proyecto predeterminado\agua-clara-ai"
python -m evals.run_evals  # 35/35 OK
```

**Agua Clara AI — cuando falta agua, la respuesta no debe depender de quién hace más ruido. Debe depender de quién más lo necesita, con evidencia verificable y supervisión humana.**