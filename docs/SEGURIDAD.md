# Seguridad de HIDRO360

## Modelo de acceso (roles)
| Quién | Cómo accede | Qué puede |
|---|---|---|
| **Ciudadano** (sin cuenta) | Portal público de la interfaz o `POST /api/v1/publico/reportes` | Registrar un reporte, consultar su estado con un **código de seguimiento** (`HID-XXXXXXXX`), ver avisos. Nunca ve textos de otras personas ni datos internos |
| **Usuario** (rol `usuario`) | Cuenta creada con `scripts.crear_admin --rol usuario` | Sin permisos administrativos (no accede a la consola ni a endpoints admin) |
| **Administrador** (rol `administrador`) | Login (usuario + contraseña) → sesión; en la API, sesión `Bearer` o token de servicio `AGUA_CLARA_API_TOKEN` | Toda la gestión: revisar, confirmar/rechazar, duplicados, prioridades, planes, aprobar/rechazar, auditoría, trazas, diagnóstico |
| **Dispositivo** (ESP32) | `X-API-Token` = `AGUA_CLARA_DEVICE_TOKEN` | Solo `GET /estado`, `POST /dispositivos/confirmaciones`. No lee reportes ni aprueba |

## Dónde se comprueba la autorización (no basta con ocultar botones)
1. **Lógica de negocio** (`services/workflow.py`): las funciones administrativas llevan `@requiere_admin` (`services/auth.py`) y fallan con `ErrorAutenticacion` (sin actor) o `ErrorAutorizacion` (rol sin permiso) **antes** de abrir transacción. La interfaz y la API establecen el actor con `auth.como(actor)`.
2. **API** (`api/main.py`): dependencias `admin`, `autenticado`, `dispositivo_u_operador`; 401 sin credenciales válidas, 403 sin permiso, 429 por límite de tasa.
3. **Interfaz**: la consola no se construye sin sesión de administrador, y cada operación se ejecuta con el actor de la sesión. Es una comodidad: la barrera real son los puntos 1 y 2.
Pruebas (`tests/test_auth.py`): cada función administrativa y **cada ruta** de la API que no es pública se prueba sin credenciales (401), con rol `usuario` (403) y con token de dispositivo (401).

## Cuentas y contraseñas
- **No existen cuentas ni contraseñas predeterminadas.** El primer administrador se crea a mano: `python -m scripts.crear_admin` (la contraseña se pide sin mostrarla y no se acepta por argumento).
- Contraseñas con **scrypt** y sal aleatoria por cuenta (no se guardan en texto plano; hay prueba que inspecciona SQLite). Política mínima: 10 caracteres con mayúsculas, minúsculas y un número.
- Mensaje de error idéntico para usuario inexistente y contraseña incorrecta; **bloqueo temporal** tras 5 fallos seguidos por usuario (5 min).
- Sesiones: token aleatorio de 256 bits, solo su SHA-256 vive en memoria, expiran a las 8 h y se invalidan al cerrar sesión.
- El responsable en la auditoría es el **usuario autenticado** (con el token de servicio se registra `servicio:<nombre declarado>`; el ciudadano figura como `ciudadano`).

## Portal público
Código de seguimiento aleatorio (`secrets`); código inválido e inexistente dan el mismo error; límite de 10 reportes/min y 20 consultas/min por IP; la consulta devuelve solo código, estado público comprensible, sector (si está confirmado) y fecha: ni texto original, ni motivos de rechazo, ni responsables, ni ids internos. Los avisos públicos no incluyen litros, cisternas ni horas.

## Secretos
`GEMINI_API_KEY` y los tokens salen solo de variables de entorno o `.env` (en `.gitignore`; solo se versionan `.env.example`). No hay claves en código, tests, README ni frontend. Las trazas y la auditoría no guardan claves ni el texto completo del ciudadano. Si una clave se filtra: revóquela y cree otra.

## Entrada no confiable e IA
Texto del ciudadano = dato: frases tipo instrucción se excluyen; el modelo no tiene herramientas; teléfonos y correos se ocultan antes de enviar a Gemini; la salida se valida con Pydantic y con código; la IA no aprueba, rechaza, asigna ni prioriza. Ver `docs/IA_GEMINI.md`.

## Integridad
Auditoría y trazas con cadena de hashes: detectan la alteración o el borrado de una entrada intermedia, no la edición del archivo ni el truncado final. La auditoría está en SQLite en la misma transacción que el cambio.

## Limitaciones conocidas (honestas)
- **Sesiones, contadores de fallos y límites de tasa viven en memoria**: se pierden al reiniciar y no se comparten entre procesos.
- El bloqueo por usuario permite bloquear a propósito a un administrador; el límite por IP usa `request.client` (tras un proxy sería la IP del proxy).
- **Sin HTTPS propio**: contraseñas, tokens y sesiones viajan en claro en la red local. Úsese solo en una red de confianza o detrás de un proxy TLS.
- Sin recuperación de contraseña, sin MFA, sin gestión de cuentas desde la interfaz (solo por línea de comandos).
- Si dos ciudadanos envían exactamente el mismo texto en 30 s, la idempotencia devuelve el mismo reporte y el mismo código.
- No se ha realizado una auditoría de seguridad externa ni pruebas de penetración: no afirme que el acceso es «a prueba de ataques»; afirme lo que las pruebas demuestran.
- Datos personales: la demo usa datos ficticios; con datos reales defina retención y revise las condiciones de Google si usa Gemini.

## Red
No abra puertos a internet. La API y la interfaz escuchan en `127.0.0.1` salvo que se indique otra cosa. Raspberry: red local aislada y firewall (ver `docs/HARDWARE.md`).
