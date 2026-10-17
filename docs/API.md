# API HTTP (FastAPI) — `/api/v1`

Código: `api/main.py` (capa fina sobre `services/workflow.py`). Documentación interactiva: `http://localhost:8000/docs` con `uvicorn api.main:app --port 8000`. Esquemas: `models/schemas.py` (`SCHEMA_VERSION = 1.2`). Modelo de roles: `docs/SEGURIDAD.md`.

## Autenticación
| Credencial | Cabecera | Para |
|---|---|---|
| Sesión de usuario | `Authorization: Bearer <token>` (de `POST /auth/login`) | administración (rol `administrador`) |
| Token de servicio | `X-API-Token` = `AGUA_CLARA_API_TOKEN` | administración desde otros sistemas (solo existe si está configurado) |
| Token de dispositivo | `X-API-Token` = `AGUA_CLARA_DEVICE_TOKEN` | solo `GET /estado` y `POST /dispositivos/confirmaciones` |
Sin tokens configurados: `/estado` y `/dispositivos/confirmaciones` solo aceptan localhost; ningún acceso administrativo es implícito (hay que iniciar sesión).

## Errores
401 sin credenciales/sesión inválida · 403 sin permiso · 404 «no existe» · 409 transición no permitida · 422 validación/regla de negocio · 429 límite de tasa. Cuerpo `{"detail": "mensaje"}`; los errores internos devuelven «Error interno.» sin traza.

## Endpoints
**Sin credenciales**
| Ruta | Descripción |
|---|---|
| `GET /salud` | `{ok, schema_version, version, proveedor_ia}` |
| `POST /auth/login` | `{usuario, clave}` → `{token, rol, expira_horas}`; límite por IP + bloqueo por usuario |
| `POST /publico/reportes` | `{texto}` → `{codigo_seguimiento, mensaje}` (10/min por IP) |
| `GET /publico/reportes/{codigo}` | `{codigo, estado_publico, sector?, fecha_creacion}` (20/min por IP; código inválido o inexistente = mismo 404) |
| `GET /publico/avisos` | avisos comprensibles (sin litros, cisternas ni horas) |

**Sesión o token de servicio (cualquier rol)**: `POST /auth/logout`, `GET /auth/yo`.
**Dispositivo o servicio**: `GET /estado` (plan aprobado/pendiente, top de prioridades, cisternas, contadores; sin borradores ni textos de ciudadanos) · `POST /dispositivos/confirmaciones` `{dispositivo_id, plan_id, tipo, cisterna_id?, detalle?}` → 202, solo se audita y solo sobre planes aprobados.

**Administrador** (sesión admin o token de servicio)
| Ruta (alias de la guía) | Descripción |
|---|---|
| `GET/POST /reportes` (`/reports`) | listar · crear `{texto, responsable?, canal?, clave_idempotencia?}` |
| `GET /reportes/{id}` | detalle |
| `POST /reportes/{id}/confirmar` (`/confirm`) | corrige y confirma `{sector, horas_sin_agua?, personas_afectadas?, severidad?, calle?, servicio_esencial?, vulnerabilidades?, tipo_incidencia?, referencia_ubicacion?}` |
| `POST /reportes/{id}/rechazar` (`/reject`) | `{motivo}` |
| `GET /reportes/{id}/duplicados` · `POST /reportes/{id}/duplicado` | sugerencias · decisión `{otro_id, es_duplicado, motivo?}` |
| `GET /prioridades` · `/sectores/visibilidad` · `/cisternas` | cálculo determinista / visibilidad / catálogo |
| `GET/POST /planes` (`/plan`) · `GET /planes/{id}` | listar · generar `{metodo: flujo\|greedy}` |
| `PUT /planes/{id}/asignaciones` | editar `{motivo, asignaciones[]}` (valida capacidad/elegibilidad) |
| `POST /planes/{id}/decision` (`/plan/{id}/decision`) | `{accion: aprobar\|rechazar, motivo}` |
| `GET /auditoria` (`/audit`) · `GET /trazas` | bitácora + integridad · eventos JSONL |
El campo `responsable` es opcional: **prevalece el usuario autenticado**.

## Reglas del contrato
Estados de reporte: `por_revisar → confirmado | rechazado | duplicado`; `confirmado → rechazado | duplicado | en_plan`. Estados de plan: `propuesto → aprobado | rechazado`. Otra transición ⇒ 409. Capacidad y elegibilidad se revalidan al editar y aprobar. Cambiar un modelo ⇒ subir `SCHEMA_VERSION`, actualizar este documento y el firmware si afecta a `/estado`.
