# Bitácora de IA

**Equipo:** Team VIFY AI (Frida Leis · Yohany Kavacila · Victor Montes)  
**Requisito del reto:** Documentar qué partes se hicieron con IA, con qué herramienta y qué se modificó a mano.

## Propósito
Esta bitácora cumple el entregable obligatorio "Bitácora de IA" del reto.

## Uso de IA

| Parte del sistema | Herramienta IA | Nivel | Descripción de lo generado/modificado |
|---|---|---|---|
| Arquitectura y diseño (plan de implementación) | OpenCode (Big Pickle) | Asistido | Se solicitó revisar el reto, las dos propuestas (Agua Clara AI y AquaTrust-PTY), la guía y el MVP. Se recibió análisis, puntos críticos, incumplimientos de rúbrica y plan priorizado (P1–P3). **Modificado a mano**: se decidió mezclar lo útil de AquaTrust (sesgo de visibilidad, registro encadenado, trazas, evals) con el alcance pragmático de Agua Clara. |
| Esquemas Pydantic (`schemas.py`) | OpenCode | Asistido | Se generó estructura base de modelos (Report, Sector, Tanker, Assignment, Plan, DeliveryEvidence). **Modificado a mano**: se agregaron campos guardrails (`injection_flag`, `out_of_scope`, `medical_emergency`) y límites (severity 1–5, horas 0–720, poblaciones). |
| Configuración, almacenamiento y auditoría (`config.py`, `services/storage.py`) | OpenCode | Asistido | Se generaron helpers .env, pseudonimización, conexión SQLite y **cadena de hashes encadenada** (seq, prev_hash, hash). **Modificado a mano**: corrección en almacenamiento del payload (se almacena payload JSON puro) y verificación (`audit_verify_chain`) para computar body correctamente. |
| Agentes A1–A8 (`agents/*.py`) | OpenCode | Asistido | Se generaron intake (LLM+fallback), geolocation (difflib), estimator (corrección sesgo de visibilidad, logit/sigmoid), prioritization (0.4/0.3/0.3 + bono crítico), planner (greedy determinista, base "por quejas"), verification (3 señales), communication (plantillas + verificador numérico), supervisor (revalidación). **Modificado a mano**: conteo de fuentes distintas (dedup por fuente), estimador usa evidencia corregida por propensión, planner usa uuid (evita colisión de IDs), métricas post-plan. |
| Guardrails (`agents/guardrails.py`) | OpenCode | Asistido | Se generaron detección de campañas coordinadas (fuentes distintas + similitud), detección de emergencia médica, rate-limit. **Modificado a mano**: filtro de campañas usa todas las fuentes, requiere >=4 fuentes distintas y alto ratio. |
| Orquestador (`agents/orchestrator.py`) | OpenCode | Asistido | Se generó pipeline con trazas y auditoría. **Modificado a mano**: cálculo de Gini/deprivación **post-plan** (basado en horas_after tras cobertura) para que el método social vs quejas se diferencien; verificación de cadena auditiva tras cada acción relevante. |
| UI demo (`app.py`) | OpenCode | Asistido | Se generó SPA con pestañas (Reporte, Bandeja, Plan, Aprobación, Verificación, Evals/Trazas), comparación métodos, simulador de entrega, botón de evals. **Modificado a mano**: ajuste de clases CSS/legibilidad, muestra inyección/oos/duplicado, muestreo activo, trazas y auditoría encadenada. |
| Evals (`evals/cases.py`, `harness.py`, `run_evals.py`) | OpenCode | Asistido | Se generaron 20 casos con descripciones, ejecución contra DB temporal. **Modificado a mano**: corrección de lógica EV09–EV12 (prioridades por métodos, capacidad insuficiente), uso correcto del catálogo, validación de edición (EV17), modo offline (EV18), determinismo permutación (EV20). Resultado final **20/20 aprobados**. |
| Documentación (`README.md`) | OpenCode | Asistido | Se redactó README completo con principios, arquitectura, agente por agente, herramientas que actúan, ejecución, guion demo, cumplimiento rúbrica. **Revisado a mano**: eliminar referencias a hardware (no usado), aclarar modo offline, correcciones de rutas Windows. |
| Tests rápidos de integración | OpenCode | Asistido | Se ejecutaron pruebas rápidas desde CLI para validar ciclo reporte→plan→decisión→entrega→trazas→auditoría. **Analizado a mano**: se detectaron dos bugs (plan.id colisión, payload de auditoría incorrecto) y se corrigieron. |
| Git, tag de congelamiento, bitácora | Manual | Manual | Se prepara `BITACORA_IA.md` (este archivo), `.gitignore`, `final-24h` tag (commit atómicos). Se registra uso de IA con transparencia, conforme al reto. |

## Verificación de cumplimiento
- [x] ≥15 casos de evaluación: 20 casos, **100% aprobados**.
- [x] Trazabilidad: `services/traces.py` registra run_id, agente, herramientas, decisión.
- [x] Auditoría encadenada: verificación de integridad (detecta rotura).
- [x] Humano en ciclo: aprobación obligatoria con motivo; edición revalidada.
- [x] Guardrails: inyección, fuera de alcance, emergencia médica, campañas, valores absurdos.
- [x] Herramientas que actúan: SQLite, auditoría hash, outbox, solver determinista.
- [x] Componentes determinísticos: scoring, geoloc fuzzy, dedup, planner, verificación.

## Declaración
La IA asistió en la codificación y documentación. Toda lógica crítica (auditoría, sesgo de visibilidad, métricas post-plan, revalidación de ediciones) fue **revisada, testeada y corregida a mano** hasta obtener **20/20** en evals y flujo demo verificado de punta a punta.

**Fecha:** 16 de octubre de 2026  
**Equipo:** Team VIFY AI