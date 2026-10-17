# Guion del video de demostración (máx. 3 minutos)

> **Este es solo un guion. El video NO se ha grabado.** Preparación: `python app.py` (o `python app.py --web`), pulsar «Cargar datos de ejemplo», pantalla limpia, Responsable = su nombre. Ensayar con cronómetro; si algo falla, plan B: capturas del recorrido.

| Tiempo | Pantalla | Qué decir / hacer |
|---|---|---|
| 0:00–0:20 | Panel general | «Cuando falta agua, la respuesta no debería depender de quién reporta más.» Mostrar 19 reportes y la etiqueta **DATOS FICTICIOS**. |
| 0:20–0:50 | Bandeja de reportes | Escribir «En Vista Alegre no tenemos agua desde ayer» → *Recibir*. Mostrar que se guardó (SQLite) y que el texto original no cambia. |
| 0:50–1:15 | Revisión y validación | Ver lo que entendió (sector por referencia, 24 h marcadas como **estimación**, personas **faltantes**). Completar personas = 120 y *Confirmar*. |
| 1:15–1:40 | Ubicación y duplicados | Elegir un reporte de La Chorrera: aparece como **posible duplicado** con motivos; decidir «Sí». Insistir: *nunca se fusiona solo*. |
| 1:40–2:05 | Priorización | Confirmar varios reportes antes del video. Mostrar el desglose (40/30/30) y que 5 quejas no suben el puntaje; señalar «sectores sin información» (sin reportes ≠ sin necesidad). |
| 2:05–2:30 | Planificación y aprobación | *Generar propuesta*: barras de capacidad, sectores **pendientes con motivo**. Editar una asignación (pide motivo) y **Aprobar**. |
| 2:30–2:45 | Evaluación e impacto | Pestaña «Línea base vs HIDRO360»: persona-horas y Gini; decir que son **datos sintéticos**. |
| 2:45–3:00 | Auditoría / Trazas | Mostrar responsable, fecha, motivo y antes/después; la cadena de hashes íntegra; la traza que indica reglas o fallback. Cierre: «La IA ayuda a leer; las reglas calculan; la persona decide.» |

Mensajes a NO decir: que hay IA decidiendo, que el ESP32/Raspberry están probados, que los resultados del experimento son impacto real, que hay autenticación de usuarios.
