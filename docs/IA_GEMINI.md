# IA y Gemini en HIDRO360

> **Estado honesto.** La integración con Gemini está **implementada y probada con un cliente simulado** (y la construcción de objetos del SDK real se valida contra el paquete instalado). **No se ha probado contra el servicio real** porque el desarrollo no tuvo clave. Sin clave el sistema funciona completo en modo local (reglas).

## Qué hace la IA y qué no
| Tarea | Quién | Dónde |
|---|---|---|
| Interpretar el reporte (sector, referencia, horas, personas, severidad, tipo, vulnerabilidad, servicio esencial, inciertos, evidencia) | Gemini **propone**; el código valida | `services/ingest.py` → `InterpreteGemini` |
| Resumen explicable de un puntaje ya calculado | Gemini redacta; el código rechaza cifras inventadas | `services/ia_tareas.py` |
| Borrador de comunicación | Gemini redacta; el código rechaza promesas de hora; el aviso «BORRADOR» lo añade el código | `services/ia_tareas.py` |
| **Recomendación de respuesta** (acción sugerida de 1-3 frases para un reporte analizado) | Gemini redacta con esquema estricto; el código la descarta si inventa sector/cisterna/cifras, incluye datos personales o promete hora | `services/ia_tareas.py` → `recomendar_respuesta` |
| Prioridad, plan, capacidad, estados, auditoría, aprobación | **Código determinista / personas** (nunca la IA) | `services/*` |
Gemini **no** aprueba reportes, no cierra incidentes, no asigna cisternas ni calcula prioridad.

## Cómo se configura
1. Cree una clave en https://aistudio.google.com/apikey (requiere cuenta de Google). **No la pegue en el código, el chat, el README ni los tests.**
2. Copie `.env.example` a `.env` (está en `.gitignore`) y escriba `GEMINI_API_KEY=...`. Opcional: `GEMINI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_MAX_REINTENTOS`.
3. `AI_PROVIDER`: `auto` (defecto: Gemini solo si hay clave) · `local` (nunca sale texto del equipo) · `gemini` (fuerza Gemini; si falla, modo local).
4. Verifique: `python -m scripts.verificar_gemini` (muestra proveedor, modelo y si hay clave —sin mostrarla—, lista los modelos disponibles y hace una llamada mínima; códigos de salida 0/1/2). `--sin-llamada` solo comprueba la configuración. En la app: **Configuración → Verificar conexión con Gemini**.
5. Cambiar de modelo: edite `GEMINI_MODEL` en `.env`; no hay que tocar código. **El modelo por defecto (`gemini-3.5-flash-lite`) se tomó de la página de modelos de Google consultada el 2026-10-16; los nombres cambian: confírmelo con el comando anterior.**

## Límites, gratuidad y condiciones
Según la documentación de Google consultada el 2026-10-16: existe un nivel gratuito ligado a un proyecto; los límites (solicitudes/min, tokens/min, solicitudes/día) dependen del modelo y del proyecto, **se ven en AI Studio**, pueden cambiar y no están garantizados; las cuotas diarias se reinician a medianoche (Pacífico). **No se promete que ningún modelo ni cuota sea gratuito de forma permanente.** Revise las condiciones de uso y de tratamiento de datos vigentes de Google antes de enviar datos reales: esta guía no las ha verificado.

## Fallback local
Se activa si falta clave/paquete, hay timeout/red caída, 429 (cuota), 401/403, 5xx persistente, respuesta vacía/bloqueada, JSON inválido, campo extra o rango inválido. El resultado queda como `metodo = "reglas(fallback)"`, con una nota visible en la revisión y un evento `fallback` en las trazas. **Nunca** se presenta como generado por Gemini.
- Reintento prudente: máximo `AI_MAX_REINTENTOS` (1), solo para errores transitorios (5xx, timeout, red).
- Corte de circuito: tras 429 se suspenden las llamadas 60 s; tras 401/403, 15 min; tras 3 fallos seguidos, 60 s (estado visible en Configuración; botón «Reiniciar estado»).

## Validación y seguridad
- **Entrada no confiable**: el texto del ciudadano es dato. Las frases que parecen instrucciones («olvida las reglas…») se excluyen de la extracción y se avisa; el prompt separa instrucciones del sistema y datos (`<reporte>…</reporte>`); el modelo no tiene herramientas.
- **Privacidad**: antes de enviar se redactan teléfonos y correos (`[tel]`, `[correo]`). Se envía solo el texto del reporte (sin id, sin otros reportes); las tareas de resumen/borrador envían solo sector, puntaje, factores o litros. No se envía nada si `AI_PROVIDER=local`.
- **Salida**: esquema estricto `SalidaIA` (`extra="forbid"`, rangos) + revalidación en código: el sector lo decide el catálogo; cifras y severidad exigen una evidencia que aparezca **literalmente** en el texto enviado (y fuera de las frases sospechosas); enums y formatos; lo no respaldado se descarta y se marca incierto.
- **Confianza**: la que declara el modelo es una autoevaluación subjetiva; **no es una probabilidad calibrada** y la interfaz lo indica.
- **Secretos**: la clave solo sale de variables de entorno/`.env`; no se registra en trazas, errores ni estado (pruebas: `tests/test_gemini.py`).
- **Trazas**: cada llamada deja `ia/gemini.<tarea>` con modelo, estado y duración, sin contenido.

## Orquestador: del reporte a la misión (con aprobación humana)
```
Reporte -> validación -> duplicados -> clasificación -> prioridad -> recomendación -> asignación -> [APROBACIÓN HUMANA] -> misión
```
Código: `services/orquestador.py` (lógica pura, sin base de datos), `services/workflow_ia.py` (persistencia, permisos, auditoría) y `api/rutas_ia.py` (router FastAPI; el líder lo monta con `app.include_router(rutas_ia.crear_router(admin), prefix="/api/v1")`).

| Etapa | Quién | Reutiliza |
|---|---|---|
| validación | código | estado del reporte, sector del catálogo (si el reporte está rechazado/duplicado/en plan el flujo **se detiene** y el resto queda `omitida`) |
| duplicados | código (solo **sugiere**; nada se fusiona) | `geoloc.sugerir_duplicados` |
| clasificación | **Gemini** propone / reglas | `ingest.interpretar` (informativa: no modifica el reporte) |
| prioridad | código | `prioritization` (el reporte se evalúa «como si» estuviera confirmado, sin cambiarlo) |
| recomendación | **Gemini** redacta / texto local | `ia_tareas.recomendar_respuesta` |
| asignación | código | `planner` (capacidad, `litros_disponibles`, elegibilidad; excluye cisternas con misión activa). Si no hay cisterna posible: `cisterna_sugerida=None` con el motivo en el detalle de la etapa |

- **Procedencia por etapa** (`EtapaIA.proveedor`): `gemini` solo si Gemini respondió y la salida pasó la validación; `reglas` si el modo local es la configuración; `reglas(fallback)` si se intentó Gemini y falló (429, 401/403, 5xx, timeout, sin red/clave, JSON inválido, campo extra, sector/cisterna/cifras inventados, datos personales, promesa de hora). **Global** (`Recomendacion.proveedor`): `gemini` solo si **todas** las etapas con IA (clasificación y recomendación) respondieron Gemini; `reglas(fallback)` si alguna lo intentó y falló; si no, `reglas`. El fallback nunca se rotula como Gemini y deja traza `fallback` (`orquestador/etapa.<nombre>` y `ia/...`).
- **Aislamiento de errores**: cada etapa corre aparte; si una falla queda `error`/`fallback` y las demás continúan con datos deterministas.
- **Humano en el bucle**: `analizar_reporte` solo guarda una `Recomendacion` «propuesta» (re-analizar crea otra, no sobrescribe). `decidir_recomendacion(id, "aprobar"|"modificar"|"rechazar", ...)` es la **única** vía a una misión (`workflow.crear_mision`), exige rol administrador, rechazar y modificar exigen motivo, la propuesta se revalida contra el estado actual de las cisternas y una recomendación decidida no se puede decidir de nuevo. Todo queda en la auditoría (misma transacción).
- **API** (administrador): `POST /api/v1/reportes/{id}/analisis` · `GET /api/v1/recomendaciones?estado=&reporte_id=` · `GET /api/v1/recomendaciones/{id}` · `POST /api/v1/recomendaciones/{id}/decision` con `{"accion","motivo","cisterna_id","paradas"}`.

### Cómo probarlo
1. Modo local (sin clave): `.venv\Scripts\python -m pytest tests/test_orquestador.py -q`. Las pruebas con Gemini usan un **cliente simulado (mock)**: demuestran la validación, la procedencia y el fallback, **no** el servicio real.
2. Servicio real: configure `GEMINI_API_KEY` (ver arriba), ejecute `python -m scripts.verificar_gemini` y después `pytest tests/test_orquestador.py -k gemini_real -q` (se **omite** sin clave). Con clave, además, analice un reporte desde la API y compruebe que `etapas[clasificacion].proveedor` y `etapas[recomendacion].proveedor` sean `gemini`.
3. **No probado sin clave**: respuestas reales de Gemini al esquema de recomendación (el prompt y la validación están implementados, pero no verificados contra el modelo; es posible que el modelo produzca textos que la validación estricta descarte con frecuencia), latencia/cuotas reales y calidad de la clasificación.

## Limitaciones
Modelo y cuotas pueden cambiar; la extracción por reglas es regex; el modo Gemini aún no se evaluó con los 22 casos del runner (el runner usa el modo local); no se usa salida estructurada nativa del SDK (`response_schema`) porque no pudo verificarse sin clave: se pide JSON (`response_mime_type`) y se valida con Pydantic.
