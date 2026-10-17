# Diseño de la interfaz: del prototipo HTML a Flet

> Nota: `PROTOTIPO/` desapareció del árbol de trabajo durante una reorganización y se restauró desde el respaldo (SHA-256 idéntico). La interfaz se organiza ahora en `interface/flet_app/portal/` (público) y `interface/flet_app/admin/` (administración).

## Qué es el prototipo (`PROTOTIPO/hidro360_prototipo.html`, 78 KB)
Una sola página **ciudadana/comunitaria** («Hidro360 | Prototipo conceptual para La Chorrera»): barra superior blanca (logo + enlaces Inicio · Alertas · Cisternas · Cómo funciona + botón «Reportar falta de agua»), *hero* degradado azul marino con titular y dos acciones, cuatro tarjetas de cifras (alertas activas, sectores afectados, cisternas en ruta, reportes atendidos), mapa ilustrativo con pines (El Coco, Guadalupe, Barrio Colón, Puerto Caimito), lista de alertas con estado (prioridad alta / en seguimiento), tarjeta «Asistencia inteligente», estado de cisternas, «¿Cómo funciona?» en 3 pasos, y un modal de reporte (sector, tipo de problema, tiempo sin agua, personas, información adicional).
- **Paleta** (variables CSS): navy `#09265d`, azul `#087cf0`, cian `#15c9e8`, texto `#17243b`, apagado `#6d7b91`, línea `#e5edf5`, fondo `#f5f9fd`, rojo `#e85d67`, ámbar `#f2a93b`, verde `#169b79`. Tipografía Inter/sistema. Tarjetas blancas con radio 18 px y sombra suave.
- **Datos**: todo es ficticio y está rotulado («DEMO», «EJEMPLO», «datos ficticios, no reportes oficiales»). **Interacciones simuladas**: el modal solo añade una alerta a la vista mientras la página está abierta; no hay backend.
- **Valor**: el diseño visual. No se convirtió el HTML a Python; se conserva intacto en `PROTOTIPO/` como referencia.

## Qué se trasladó a Flet
| Prototipo | Flet |
|---|---|
| Paleta, radios, sombras | `interface/flet_app/theme.py`, `components.py` |
| Logo en la barra superior | Barra lateral y bienvenida (`assets/logo.jpeg`) |
| *Hero* degradado | Panel general (`interface/flet_app/admin/`, página del panel) |
| Tarjetas de cifras | `components.kpi` |
| Alertas con pastilla de estado | Prioridades con `pill_estado` |
| Mapa con pines | Mapa **esquemático** de sectores coloreado por prioridad (Panel general) |
| Estado de cisternas | Planificación (uso de cisternas por barras) |
| Modal «Reportar» | Bandeja de reportes (formulario) |
| «¿Cómo funciona?» | Recorrido operativo del Panel |
| Aviso «datos ficticios» | `C.ficticio()` visible en el Panel |
Lo que **no** se trasladó: la vista pública de ciudadanos (el sistema actual es una herramienta del coordinador), el mapa cartográfico, la sección «cisternas en ruta» (no hay datos de ruta reales: no se inventan).

## Pantallas implementadas (todas con función real)
Panel general · Bandeja de reportes (filtros, detalle con fotos y mini-mapa) · Mapa · Recomendaciones IA · Revisión y validación · Ubicación y duplicados · Prioridades · Plan y aprobación · Comunicación · Misiones y flota · Métricas · Auditoría · Configuración · (Diagnóstico y desarrollo: Trazas, Evaluación e impacto, Verificar Gemini, Datos de ejemplo). La antigua página «Estado de dispositivos» se fusionó en «Misiones y flota».

## Logo
JPEG con fondo blanco, sin transparencia, sin texto (gota azul con marcador de ubicación y ondas). Se usa **sin modificar**, solo sobre superficies blancas. Si se necesita sobre fondos oscuros, hace falta una versión con transparencia del diseñador.

## Responsivo y accesibilidad
Barra lateral completa ≥ 980 px y compacta (solo iconos con *tooltip*) por debajo; rejillas con `ResponsiveRow`. Contraste: texto `#17243b` sobre blanco/`#f5f9fd`; pastillas con pares fondo/texto de contraste alto. Pendiente: revisión con lector de pantalla (Flet depende de la semántica de Flutter).


## Mapas, fotos, IA supervisada y flota (interfaz v2)
**Navegación del administrador:** Operación (Panel, Bandeja, Mapa, Recomendaciones IA, Revisión, Ubicación y duplicados, Prioridades, Plan, Comunicación) · Flota (Misiones y flota) · Seguimiento · Sistema · Diagnóstico y desarrollo (plegado).

**Portal ciudadano** (`portal/reportar.py`, `portal/consultar.py`): el formulario añade un mapa para marcar el lugar (clic = marcador, guarda lat/lng reales; «No sé ubicarlo en el mapa» descarta el punto y usa solo sector/referencia), hasta 3 fotos con `FilePicker` (comprobación amistosa de tipo y tamaño en el cliente; la validación real, por firma binaria, es del backend y sus errores se muestran en español), y tras enviar muestra el código con botón «Copiar código». La consulta por código muestra estado, si hay ubicación y cuántas fotos; nunca coordenadas ni fotos. Nada técnico (IA, trazas, hashes) aparece en el portal.

**Mapa** (`mapa.py`): `flet-map` (OpenStreetMap). Selector del portal, mini-mapa del detalle y mapa general de la consola alimentado por `workflow.datos_mapa()`: solo se dibuja lo que trae coordenadas válidas; nada se inventa. Los vehículos aparecen en su sector base o en su última parada (el tooltip lo dice); no hay posición en vivo. Sin rueda del ratón en los mapas de formulario (no mover la página); rotación desactivada. **Limitación:** las teselas se descargan de internet. Sin conexión el fondo se ve gris, el formulario sigue funcionando y la pantalla lo avisa. Si `flet-map` no estuviera instalado se muestra un aviso en lugar del mapa. Verificado con el modo `--web` (flet-web 1.0.4 trae flutter_map); en la ventana de escritorio depende de que el cliente descargado incluya la extensión (no verificado).

**Bandeja** (`admin/bandeja.py`): filtros por estado, sector y texto/código; el detalle (arriba de la lista) muestra texto original, datos, coordenadas, mini-mapa, miniaturas de fotos (`obtener_foto`, ampliables) y acciones: revisar/confirmar, rechazar con motivo, ver duplicados y «Analizar reporte».

**Recomendaciones IA** (`admin/recomendaciones.py`): procedencia visible por etapa (Gemini · reglas locales · reglas de respaldo/fallback, esta última nunca presentada como IA), prioridad, duplicados sugeridos (solo sugeridos), cisterna y paradas. Aprobar (con confirmación), Modificar (cisterna y litros por parada; motivo obligatorio) y Rechazar (motivo obligatorio) llaman a `decidir_recomendacion`; tras aprobar se abre la misión creada. La IA propone, una persona decide.

**Misiones y flota** (`admin/misiones.py`): flota con estado de la terminal (activa, última conexión, misión en curso), registrar terminal / rotar token / desactivar, crear misión manual o desde un plan aprobado, avance por parada, eventos recibidos (llegada, entrega, incidencia) con botón Actualizar y refresco automático cada 15 s (solo recarga listas, no formularios), y cancelar con motivo. El token se muestra **una sola vez** en un diálogo y nunca se vuelve a mostrar.

**Detalle técnico:** las lecturas de los manejadores de eventos usan `ctx.con_actor()` porque Flet los ejecuta fuera de la construcción de la página (sin el actor ambiente). `interface/flet_app/backend.py` localiza las funciones del servidor por nombre y descarta con claridad los argumentos que una versión aún no admite.

**No verificado visualmente:** selección real de fotos con el diálogo del sistema (se probó la lógica con dobles de prueba y la subida con `with_data=True`), la ventana de escritorio con mapas, pantallas estrechas (móvil) y el flujo de rotar/desactivar terminal en navegador (solo en pruebas automáticas).
