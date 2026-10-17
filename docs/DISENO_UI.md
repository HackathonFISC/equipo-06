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
Panel general · Bandeja de reportes · Revisión y validación · Ubicación y duplicados · Priorización · Planificación y aprobación · Comunicación · Trazas · Evaluación e impacto · Auditoría · Estado de dispositivos · Configuración.

## Logo
JPEG con fondo blanco, sin transparencia, sin texto (gota azul con marcador de ubicación y ondas). Se usa **sin modificar**, solo sobre superficies blancas. Si se necesita sobre fondos oscuros, hace falta una versión con transparencia del diseñador.

## Responsivo y accesibilidad
Barra lateral completa ≥ 980 px y compacta (solo iconos con *tooltip*) por debajo; rejillas con `ResponsiveRow`. Contraste: texto `#17243b` sobre blanco/`#f5f9fd`; pastillas con pares fondo/texto de contraste alto. Pendiente: revisión con lector de pantalla (Flet depende de la semántica de Flutter).
