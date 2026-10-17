# IA y Gemini en HIDRO360

> **Estado honesto.** La integración con Gemini está **implementada y probada con un cliente simulado** (y la construcción de objetos del SDK real se valida contra el paquete instalado). **No se ha probado contra el servicio real** porque el desarrollo no tuvo clave. Sin clave el sistema funciona completo en modo local (reglas).

## Qué hace la IA y qué no
| Tarea | Quién | Dónde |
|---|---|---|
| Interpretar el reporte (sector, referencia, horas, personas, severidad, tipo, vulnerabilidad, servicio esencial, inciertos, evidencia) | Gemini **propone**; el código valida | `services/ingest.py` → `InterpreteGemini` |
| Resumen explicable de un puntaje ya calculado | Gemini redacta; el código rechaza cifras inventadas | `services/ia_tareas.py` |
| Borrador de comunicación | Gemini redacta; el código rechaza promesas de hora; el aviso «BORRADOR» lo añade el código | `services/ia_tareas.py` |
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

## Limitaciones
Modelo y cuotas pueden cambiar; la extracción por reglas es regex; el modo Gemini aún no se evaluó con los 22 casos del runner (el runner usa el modo local); no se usa salida estructurada nativa del SDK (`response_schema`) porque no pudo verificarse sin clave: se pide JSON (`response_mime_type`) y se valida con Pydantic.
