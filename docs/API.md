# API HTTP (FastAPI) — `/api/v1`

Código: `api/main.py` (capa fina sobre `services/workflow.py`). Documentación interactiva: `http://localhost:8000/docs` con `uvicorn api.main:app --port 8000`. Esquemas: `models/schemas.py` (`SCHEMA_VERSION = 1.3`). Modelo de roles: `docs/SEGURIDAD.md`.

## Autenticación
| Credencial | Cabecera | Para |
|---|---|---|
| Sesión de usuario | `Authorization: Bearer <token>` (de `POST /auth/login`) | administración (rol `administrador`) |
| Token de servicio | `X-API-Token` = `AGUA_CLARA_API_TOKEN` | administración desde otros sistemas (solo existe si está configurado) |
| Token de dispositivo (compartido, antiguo) | `X-API-Token` = `AGUA_CLARA_DEVICE_TOKEN` | solo `GET /estado` y `POST /dispositivos/confirmaciones` (compatibilidad) |
| Token de terminal por vehículo | `X-Device-Token` (se obtiene al registrar el dispositivo; solo se guarda su SHA-256) | solo `/dispositivo/mision`, `/dispositivo/eventos`, `/dispositivo/latido`. La cisterna se **deriva del token**, nunca del cuerpo |
Sin tokens configurados: `/estado` y `/dispositivos/confirmaciones` solo aceptan localhost; ningún acceso administrativo es implícito (hay que iniciar sesión).

## Errores
401 sin credenciales/sesión inválida · 403 sin permiso · 404 «no existe» · 409 transición no permitida · 422 validación/regla de negocio · 429 límite de tasa. Cuerpo `{"detail": "mensaje"}`; los errores internos devuelven «Error interno.» sin traza.

## Endpoints
**Sin credenciales**
| Ruta | Descripción |
|---|---|
| `GET /salud` | `{ok, schema_version, version, proveedor_ia}` |
| `POST /auth/login` | `{usuario, clave}` → `{token, rol, expira_horas}`; límite por IP + bloqueo por usuario |
| `POST /publico/reportes` | `{texto, lat?, lng?, fotos?: [{nombre, base64}]}` → `{codigo_seguimiento, mensaje}` (10/min por IP). `lat`/`lng` juntas y dentro de Panamá Oeste (lat 8.3–9.3, lng −80.3 a −79.2; `config.COORD_LIMITES` si existe) o 422. Máx. 3 fotos de 3 MB; el tipo (JPEG/PNG/WebP) se decide por la **firma binaria**, no por extensión ni `Content-Type`; el nombre del cliente se ignora. Cuerpo máx. 16 MB (413) |
| `GET /publico/reportes/{codigo}` | `{codigo, estado_publico, sector?, fecha_creacion, tiene_ubicacion, n_fotos}` (nunca coordenadas ni fotos) (20/min por IP; código inválido o inexistente = mismo 404) |
| `GET /publico/avisos` | avisos comprensibles (sin litros, cisternas ni horas) |

**Sesión o token de servicio (cualquier rol)**: `POST /auth/logout`, `GET /auth/yo`.
**Dispositivo o servicio**: `GET /estado` (plan aprobado/pendiente, top de prioridades, cisternas, contadores; sin borradores ni textos de ciudadanos) · `POST /dispositivos/confirmaciones` `{dispositivo_id, plan_id, tipo, cisterna_id?, detalle?}` → 202, solo se audita y solo sobre planes aprobados.

**Terminal del vehículo** (`X-Device-Token`; 240 peticiones/min por IP y bloqueo suave con 429 tras 10 tokens inválidos en 5 min)
| Ruta | Descripción |
|---|---|
| `GET /dispositivo/mision` | `{cisterna_id, servidor_hora (ISO UTC), mision: Mision + siguiente_tarea \| null}` — solo la misión activa (asignada/en_curso) de ESE vehículo. `siguiente_tarea = {parada_orden, accion: ir_a\|entregar, sector, litros, lat, lng, instruccion}` |
| `POST /dispositivo/eventos` | `{eventos: [EventoMision, ...]}` (máx. 50, 422 si más) → `{resultados: [{uid, resultado: aplicado\|duplicado\|rechazado, motivo}]}`. **Idempotente por `uid`**: reenviar no duplica ni descuenta litros otra vez. Cada evento se valida por separado (uno defectuoso no bloquea el lote); todo el lote va en una transacción. Entregar descuenta `litros_disponibles` (nunca bajo 0) y se audita como `dispositivo:<cisterna_id>`. Los rechazados quedan registrados con el motivo en `nota` («RECHAZADO: …») |
| `POST /dispositivo/latido` | `{firmware?, wifi_rssi? (−150..0), pendientes?, uptime_s?}` → guarda `ultima_conexion` y `ultimo_estado` |

Máquina de estados: misión `asignada → en_curso` (primer evento) `→ completada` (todas las paradas entregada/incidencia); `asignada\|en_curso → cancelada` (admin, con motivo). Parada `pendiente → llegada\|entregada\|incidencia`, `llegada → entregada\|incidencia`; entrega ≤ litros planificados y > 0.

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
| `GET /reportes/{id}/fotos/{foto_id}` | bytes de la foto (solo admin) con `Content-Type` real, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline`, `Cache-Control: private, no-store`. La foto debe pertenecer a ese reporte (404 si no) |
| `POST/GET /dispositivos` | registrar `{cisterna_id, nombre?}` → `{dispositivo, token}` (**el token en claro se devuelve una sola vez**; 409 si ya existe) · listar (sin hash) |
| `POST /dispositivos/{cisterna_id}/rotar-token` · `/desactivar` | token nuevo (invalida el anterior y reactiva) · desactivar |
| `POST/GET /misiones` · `GET /misiones/{id}` | crear `{cisterna_id, paradas[{orden, sector, litros, lat?, lng?, reporte_ids?, instruccion?}], plan_id?, recomendacion_id?, motivo?}` (cisterna disponible, litros > 0 y ≤ `litros_disponibles`, sectores del catálogo, coordenadas de la parada = las del sector si faltan, una misión activa por cisterna → 409) · listar (`?estado=`) · detalle |
| `POST /planes/{id}/misiones` | `{cisterna_id}` convierte las asignaciones de un plan **aprobado** para esa cisterna en paradas |
| `POST /misiones/{id}/cancelar` | `{motivo}` obligatorio |
| `GET /eventos` | eventos de terminales (`?mision_id=&cisterna_id=`) |
| `GET /mapa` | `{reportes[{id,lat,lng,estado,sector,severidad}] (solo con coordenadas), cisternas[{id,lat,lng,fuente_ubicacion: ultima_parada\|base_sector\|null,...}], paradas (misiones activas)}`; no se inventan coordenadas |
| `GET /auditoria` (`/audit`) · `GET /trazas` | bitácora + integridad · eventos JSONL |
El campo `responsable` es opcional: **prevalece el usuario autenticado**.

## Reglas del contrato
Estados de reporte: `por_revisar → confirmado | rechazado | duplicado`; `confirmado → rechazado | duplicado | en_plan`. Estados de plan: `propuesto → aprobado | rechazado`. Otra transición ⇒ 409. Capacidad y elegibilidad se revalidan al editar y aprobar. Cambiar un modelo ⇒ subir `SCHEMA_VERSION`, actualizar este documento y el firmware si afecta a `/estado`.
