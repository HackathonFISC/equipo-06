# Base de datos (SQLite)

Archivo: `agua_clara.db` en la raíz (variable `AGUA_CLARA_DB`); está en `.gitignore` y **nunca** se borra salvo con «Cargar datos de ejemplo» (la UI pide confirmación). Código: `data/database.py` (módulo `sqlite3` de la librería estándar, sin ORM).

## Esquema (se crea con `CREATE TABLE IF NOT EXISTS`)
Todas las tablas guardan un documento JSON validado por Pydantic en la columna `datos`:
| Tabla | Clave | Contenido (modelo) |
|---|---|---|
| `sectores` | `nombre` (TEXT) | `Sector` (población, vulnerabilidad, coordenadas, alias, referencias, antecedentes, fuente) |
| `cisternas` | `id` (TEXT) | `Cisterna` (capacidad, disponible, estado, sede, sectores elegibles) |
| `reportes` | `id` (autoinc.) | `Reporte` (texto original + campos extraídos/confirmados, estado, evidencia, intérprete, clave de idempotencia) |
| `planes` | `id` (autoinc.) | `PropuestaPlan` (asignaciones, pendientes, prioridades, borradores, estado, versión, método) |
| `decisiones_duplicado` | `id` | decisión humana sobre un posible duplicado |
| `auditoria` | `id` | `EntradaAuditoria` con `hash_previo` y `hash` encadenados |
| `usuarios` | `id` (TEXT) | cuentas (scrypt); **no** se borra al recargar la demo |
| `fotos` | `id` (hex aleatorio) | `Foto` (reporte, tipo MIME por firma, bytes, sha256). El archivo está en `config.MEDIA_DIR/<id>.<ext>` (fuera de Git); **no** se borra al recargar la demo (pueden quedar huérfanas si se borran sus reportes) |
| `dispositivos` | `id` = `cisterna_id` | `Dispositivo` + `token_hash` (SHA-256 del token de 256 bits; nunca el token); **no** se borra al recargar la demo |
| `misiones` | `id` (autoinc.) | `Mision` con paradas y su estado (`ficticio` si la cisterna lo es) |
| `eventos_mision` | `id` (autoinc.) | `RegistroEvento` (uid único por evento aplicado → idempotencia; los rechazados se guardan con el motivo en `nota`) |
| `recomendaciones` | `id` (autoinc.) | `Recomendacion` de IA (agente de orquestación) |

`cargar_datos_demo` vacía solo `TABLAS` (sectores, cisternas, reportes, planes, decisiones, auditoría, misiones, eventos, recomendaciones). Los datos operativos (usuarios, dispositivos, fotos) sobreviven; los datos sintéticos llevan `ficticio=true`.

## Transacciones
`db.transaccion()` abre `BEGIN IMMEDIATE` (serializa escritores), es reentrante y revierte todo si hay excepción. Cada función mutante de `workflow.py` (`@operacion`) escribe el cambio **y** su entrada de auditoría en la misma transacción. Las trazas JSONL son un archivo aparte y no forman parte de la transacción.

## Migraciones
- Campos nuevos: añádalos al modelo Pydantic **con valor por defecto**; los documentos antiguos se leen sin migrar (así se añadieron `evidencia`, `interprete`, `clave_idempotencia`, etc.).
- Cambio incompatible (renombrar/eliminar campos, cambiar tipos): (1) copie `agua_clara.db` (`python -c "import sqlite3; s=sqlite3.connect('agua_clara.db'); d=sqlite3.connect('copia.db'); s.backup(d)"`), (2) escriba un script reversible en `scripts/migraciones/` (carpeta a crear cuando haga falta) que lea cada documento, lo transforme y lo guarde dentro de `db.transaccion()`, (3) añada una prueba que lea datos del formato antiguo, (4) suba `SCHEMA_VERSION` y documente.
- La auditoría es append-only: no se reescribe en una migración (la cadena de hashes lo detectaría).

## Integridad
`audit.verificar_integridad()` recorre la cadena. Las pruebas comprueban atomicidad (`test_auditoria_y_cambio_de_negocio_son_atomicos`) y estados inválidos.

## Datos ficticios vs reales
`Sector.ficticio`, `Cisterna.ficticio` y `Reporte.ficticio` marcan los datos de demo (`data/datos_ficticios.py`); la UI muestra «DATOS FICTICIOS». Ningún dato de demo es real.
