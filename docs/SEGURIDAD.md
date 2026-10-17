# Seguridad de HIDRO360

## Modelo de acceso (roles)
| Quién | Cómo accede | Qué puede |
|---|---|---|
| **Ciudadano** (sin cuenta) | Portal público de la interfaz o `POST /api/v1/publico/reportes` | Registrar un reporte, consultar su estado con un **código de seguimiento** (`HID-XXXXXXXX`), ver avisos. Nunca ve textos de otras personas ni datos internos |
| **Usuario** (rol `usuario`) | Cuenta creada con `scripts.crear_admin --rol usuario` | Sin permisos administrativos (no accede a la consola ni a endpoints admin) |
| **Administrador** (rol `administrador`) | Login (usuario + contraseña) → sesión; en la API, sesión `Bearer` o token de servicio `HIDRO360_API_TOKEN` | Toda la gestión: revisar, confirmar/rechazar, duplicados, prioridades, planes, aprobar/rechazar, auditoría, trazas, diagnóstico |
| **Terminal de cisterna** (ESP32-S3) | Token propio **por vehículo** en la cabecera `X-Device-Token`, contra `/api/v1/dispositivo/*` (se crea con `python -m scripts.registrar_dispositivo CIS-01`) | Solo lo que expone `/dispositivo/*` para su misión; no administra ni aprueba. Contrato exacto: `docs/API.md` |
| **Dispositivo heredado** (pantalla de monitoreo) | `X-API-Token` = `HIDRO360_DEVICE_TOKEN` (alias obsoleto `AGUA_CLARA_DEVICE_TOKEN`) | Solo `GET /estado`, `POST /dispositivos/confirmaciones`. No lee reportes ni aprueba |

Los tokens de servicio y de dispositivo se llaman ahora `HIDRO360_API_TOKEN` / `HIDRO360_DEVICE_TOKEN`; los nombres `AGUA_CLARA_*` siguen funcionando (**obsoletos**) y, si ambos existen, gana `HIDRO360_*`.

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

## Terminales por vehículo y fotografías
- **Un token por cisterna**: si una terminal se pierde o se compromete, se revoca solo esa y no las demás (a diferencia de un token compartido). Genere el token con `scripts.registrar_dispositivo` (aleatorio; no lo escriba a mano ni lo reutilice) y guárdelo solo en `config_dispositivo.h` de esa placa (ignorado por Git). Qué se guarda del token en la base y cómo se revoca: ver `docs/BASE_DE_DATOS.md` y `docs/API.md`.
- **Fotos**: se guardan en `HIDRO360_MEDIA_DIR` (en la Raspberry, `/var/lib/hidro360/media`, fuera del código y de Git; `media/` está en `.gitignore`). Límites del servidor: 3 fotos por reporte y 3 MB por foto (`config.py`). Una foto puede mostrar rostros, matrículas o interiores de viviendas: es dato personal; defina quién la ve y cuánto se conserva. Las copias de seguridad también las contienen.
- Las fotos y los tokens no deben aparecer en trazas ni en la auditoría (revise si añade registros nuevos).

## Secretos
`GEMINI_API_KEY` y los tokens salen solo de variables de entorno o `.env` (en `.gitignore`; solo se versiona `.env.example`). En la Raspberry viven en `/etc/hidro360/hidro360.env` (permisos `600`, generado por `install.sh` con tokens aleatorios `openssl rand -hex 32`, sin claves por defecto). No hay claves en código, tests, README ni frontend. Las trazas y la auditoría no guardan claves ni el texto completo del ciudadano. Si una clave se filtra: revóquela y cree otra.

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

## Red y despliegue en Raspberry
- **No abra puertos a internet ni haga port-forwarding.** En local (Windows) la API y la interfaz escuchan en `127.0.0.1`. En la Raspberry los servicios escuchan en `0.0.0.0` (puertos 8000 y 8501) **para atender a la red local**: restrinja con `ufw` a su subred (comandos en `docs/INSTALACION.md` §9.4; el instalador no cambia el firewall).
- **HTTP sin TLS en la LAN**: contraseñas, sesiones, tokens y fotos viajan **en claro**. Cualquiera en la misma red (Wi-Fi compartida incluida) puede capturarlos o suplantar una terminal. Riesgo aceptable solo en una red local aislada y de confianza; para algo más, ponga un proxy con TLS delante (no incluido ni probado).
- Los servicios corren como usuario `hidro360` sin privilegios, con `NoNewPrivileges`, `ProtectSystem=strict` y escritura únicamente en `/var/lib/hidro360` (unidades en `deploy/raspberry/`; **no probadas con systemd real**). Solo la instalación corre como root.
- Logs en journald (`journalctl -u hidro360-api -f`).

## Qué NO cubre esta seguridad
Sin TLS, sin MFA, sin recuperación de contraseñas, sin cifrado de la base ni de las fotos en disco ni de las copias, sin revisión externa ni pruebas de penetración, sin protección contra quien tenga acceso físico a la Raspberry o a la tarjeta SD, sin límites de tasa persistentes (en memoria), y sin certeza de que el despliegue en Raspberry funcione: está sin probar. Un token de terminal robado permite actuar como esa cisterna hasta revocarlo.
