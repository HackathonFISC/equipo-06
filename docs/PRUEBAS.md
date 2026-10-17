# Pruebas y evaluación

## Qué se ejecuta
| Comando | Qué cubre | Tipo |
|---|---|---|
| `pytest -q` | todas las pruebas (cifra vigente: ejecútelo) | automatizadas, sin red, con bases temporales |
| `python -m evaluation.run_cases` | casos por grupo de la guía + adicionales (ver el informe generado) | automatizadas, base temporal, modo local |
| `python -m evaluation.run_impacto` | experimento sintético línea base vs HIDRO360 | simulación con semillas fijas |
| `python -m scripts.verificar_gemini` | conexión real con Gemini | **manual**, requiere clave |

| Archivo | Cubre |
|---|---|
| `tests/test_flujo.py` | ingesta, duplicados, prioridad, capacidad, borradores, edición/aprobación/rechazo, API |
| `tests/test_backend.py` | máquina de estados, responsable, idempotencia, atomicidad con auditoría, trazas, planificador (flujo vs voraz), visibilidad, autenticación de la API |
| `tests/test_ingesta.py` | ejemplos del enunciado, sector difuso/ambiguo, inyecciones, Gemini simulado y fallbacks |
| `tests/test_gemini.py` | proveedor: selección de proveedor, reintento 503, 429/403 con corte, respuesta vacía, clave no filtrada, redacción de PII, tareas de IA, compatibilidad con el SDK real (objetos) |
| `tests/test_equidad.py` | Gini (valores conocidos, ceros vs faltantes), Spearman, reproducibilidad del experimento |
| `tests/test_flet.py` | las 12 páginas construyen; acciones reales (recibir, doble clic, confirmar, duplicados, plan, edición, aprobar/rechazar, borrador) invocando los manejadores |

## Qué NO está probado (no lo afirme)
- **Gemini real**: no hay clave en el desarrollo; solo cliente simulado.
- **Interfaz en escritorio de otros SO y la Raspberry**; **hardware** (ESP32-S3 sin compilar ni probar en placa).
- Las pruebas de Flet no abren ventana: la revisión visual se hizo en navegador (modo `--web`) y a mano.
- Los **15 casos oficiales** de la guía no existen como lista: los casos del runner los redactó el equipo; se escribieron conociendo el sistema (no son ciegos).
- El experimento de impacto es **sintético**: no demuestra impacto real.

## Entorno limpio
Para comprobar `requirements.txt`: `python -m venv .venv2 && .venv2\Scripts\activate && pip install -r requirements.txt && pytest -q`.

## Regla
Si no se ejecutó, no se afirma. Un caso falla si no se cumple el criterio, aunque no haya excepción.
