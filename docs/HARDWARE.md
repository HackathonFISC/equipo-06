# Hardware: pantalla ESP32-S3 y Raspberry Pi 4 (HIDRO360)

> **Estado honesto.** La pantalla es la **terminal operativa de un carro cisterna** (una por vehículo, con su propio token). El firmware está **escrito y se compila** con el `arduino-cli` del Arduino IDE instalado en el equipo de desarrollo (resultado en la sección 6), pero **NO está probado en la placa ni en la Raspberry**: no había hardware. Lo verificado sin placa: el protocolo HTTP completo contra la API real con `scripts/simular_terminal.py` (sección 6.5). Eso **no sustituye** la prueba física (WiFi, táctil, pantalla, NVS, tiempos). Nada se declara funcional en la placa sin esa prueba.

## 1. Modelo de placa (qué evidencia lo identifica)
- **Placa**: «2.8inch ESP32-S3 Display», documentada en https://www.lcdwiki.com/2.8inch_ESP32-S3_Display (consultada en esta revisión). SKU **ES3C28P** (con táctil capacitivo); existe también **ES3N28P** (sin táctil). El proyecto usa el táctil, por lo que se asume ES3C28P; la etiqueta física de la placa no se ha comprobado.
- **Módulo**: ESP32-S3 con «+16M external SPI Flash» y «8M internal OPI PSRAM» (N16R8), según la wiki. Pantalla ILI9341V 240×320; táctil FT6336G (I2C).
- Los ejemplos del fabricante están en `Demo/` (30 sketches, sin versionar; no se modifican).

## 2. Tabla de pines
Estados: **verificado** = coincide en la wiki y en código del fabricante; **wiki** = solo documentación; **no verificado** = sin evidencia en el repo ni en la wiki.

| Función | Pines (GPIO) | Estado | Fuente |
|---|---|---|---|
| TFT ILI9341V (SPI) | CS 10, DC 46, SCLK 12, MOSI 11, MISO 13, BL 45; RST compartido con el reset del ESP32 (`-1`) | verificado | wiki; `Demo/Example_01_Simple_test/Simple_test/spi_dev.h`; `User_Setup.h` de TFT_eSPI en `Documentos/Arduino/libraries` (`TFT_CS 10, TFT_DC 46, TFT_SCLK 12, TFT_MOSI 11, TFT_MISO 13, TFT_BL 45, TFT_RST -1`) |
| Táctil FT6336G (I2C) | SDA 16, SCL 15, INT 17, RST 18 | verificado | wiki; `Demo/Example_08_LVGL_Demos/LVGL_Demos/touch.h` (igual en Ejemplos 14 y 15) |
| LED RGB (1 pixel, un solo hilo) | IO42 | verificado | wiki; `LED_PIN 42` en Ejemplos 06, 09, 12 y 15 |
| microSD (SDIO 4 bits) | CLK 38, CMD 40, D0 39, D1 41, D2 48, D3 47 | verificado | wiki; `Demo/Example_05_show_SD_jpg_picture/Show_SD_Jpg/Show_SD_Jpg.ino`; `Demo/Example_16_music/music/ESP_Panel_Board_Custom.h` |
| Audio I2S (códec ES8311) | MCLK 4, BCLK 5, WS 7, DOUT 8, DIN 6; IO1 habilita el amplificador (nivel bajo = habilitado) | I2S verificado; IO1 solo wiki | wiki; `Demo/Example_17_echo/echo/echo.ino` (GPIO 4, 5, 7, 8, 6); `ESP_Panel_Board_Custom.h`. El códec comparte el bus I2C 15/16 (`I2C_SCL 15`, `I2C_SDA 16` en ese archivo) |
| Botón BOOT / descarga | IO0 (el botón EN reinicia) | verificado | wiki; `BUTTON_PIN 0` en `Demo/Example_09_key/Key_test/Key_test.ino` |
| UART0 (conector 4P, requiere adaptador USB-serie externo) | IO43 e IO44 | wiki; **discrepancia** RX/TX | La wiki (releída en esta revisión) escribe «RXD0 (IO43), TXD0 (IO44)»; en el chip ESP32-S3 U0TXD es GPIO43 y U0RXD GPIO44 (dato general del chip, no está en el repo). Hasta mirar la serigrafía de la placa, no cablee RX/TX por la wiki. El firmware no usa este UART |
| **GPS / GNSS** | — | **la placa NO lo documenta** | La wiki del fabricante no menciona GPS/GNSS (relectura de la página) y `Demo/` no contiene ni una referencia a GPS/NMEA/GNSS (búsqueda en los 30 ejemplos). **No hay GPS integrado verificado.** Consecuencia de diseño: la terminal **no reporta posición**; el destino y sus coordenadas vienen de la misión (`lat/lng` de la parada) y la ubicación mostrada en el mapa del panel es la de la última parada alcanzada, no una posición en vivo. Un GPS externo (UART por el conector 4P o por los GPIO de expansión) sería una ampliación **no diseñada ni probada** |
| Batería (ADC) | IO9 | wiki | wiki; `Demo/Example_13_Get_Battery_Voltage/GetBatteryVoltage/GetBatteryVoltage.ino` usa `ADC_UNIT_1`, `ADC_CHANNEL_8` (que ADC1 canal 8 sea GPIO9 es dato del chip, no del repo) |
| **Conector «Expand pin»** (1.25 mm, 4 pines) | GPIO **2, 3, 14, 21**, «normal IO» | wiki (única fuente) | wiki. **No da el orden pin a pin del conector (cuál es VCC, GND o señal)**: no verificado |
| Conectores UART (4P), I2C (4P, comparte IO16/IO15 con el táctil), batería (2P), altavoz (2P) | los indicados | wiki (solo existencia) | wiki. Orden de pines y polaridad: **no verificado** |
| Strapping, USB, flash/PSRAM | strapping 0, 3, 45, 46; USB 19/20; flash/PSRAM octal en 26-37 con módulos R8 | **no verificado en el repo** | datos generales del chip (datasheet de Espressif), no consultado en esta revisión: confirmar antes de usarlos |

**Pines realmente libres**: la única evidencia es la wiki: **GPIO2, GPIO3, GPIO14 y GPIO21** salen al conector de expansión. Ningún otro GPIO se puede dar por libre: o están asignados arriba o no hay evidencia (**no verificado**). GPIO3 es pin de strapping según el datasheet general del chip (no verificado aquí). Los comentarios de pines dentro de los `.ino` de `Demo/` (p. ej. `DC=2`, `LED=21`, `BAT_VOLT_ADC 34`) están copiados de otras placas y **no son fiables**; mandan la wiki y las constantes de código.

## 3. Comprobación del sketch contra la tabla
`firmware/esp32s3_monitor/esp32s3_monitor.ino` usa: TFT por TFT_eSPI (pines de `User_Setup.h`, coinciden con la wiki y con `Demo/Example_01`), táctil FT6336 en 16/15/17/18 (coinciden con `Demo/Example_08/LVGL_Demos/touch.h`) y la luz de fondo IO45 (la enciende TFT_eSPI con `TFT_BL`; se eliminó el `pinMode(45)` redundante). **No usa** IO42, SD, audio, UART0 ni pines de expansión. **No se encontraron conflictos de pines.** Observaciones:
- IO45 es pin de strapping del chip: no conecte nada externo a él.
- `firmware/pruebas/led_rgb/led_rgb.ino` usa IO42 con `NEO_RGB`; los ejemplos del fabricante usan `NEO_GRB`/`NEO_GRBW`: si rojo y verde salen cambiados es el orden de color (no probado).
- El bus I2C 15/16 lo comparten táctil, códec y conector I2C: no añada otros dispositivos sin comprobar direcciones. El conector IIC solo queda libre en la variante sin táctil (ES3N28P), según la wiki.
- La rotación del táctil (`ROTATION_NORMAL`) y la de la pantalla (`setRotation(0)`) siguen la combinación usada en `Demo/Example_08`; **no se ha comprobado en la placa** que los toques caigan sobre los botones dibujados.

## 4. Limitaciones físicas reales
- **Seguridad de red:** HTTP sin cifrar. El `X-Device-Token` viaja **en claro por la LAN**; cualquiera en la misma red WiFi puede capturarlo y suplantar al vehículo (leer su misión y enviar eventos de entrega). Mitigación: red local aislada con WPA2/WPA3, un token por vehículo, rotarlo (`rotar-token`) si el vehículo se pierde o se sospecha filtración, y desactivar el dispositivo. HTTPS en el ESP32 exige certificado/CA en el firmware y en la Raspberry: **no implementado**.
- **El token está en el firmware** (`config_dispositivo.h` compilado): quien tenga la placa y un cable puede extraerlo (no se activó Flash Encryption ni Secure Boot).
- **Sin GPS:** la terminal no conoce ni reporta su posición (sección 2). No hay hora real: se muestra la hora del servidor de la última sincronización; los eventos viajan con `fecha_dispositivo = null` y el servidor pone la hora.
- **Peticiones bloqueantes:** durante una petición HTTP (hasta `HTTP_TIMEOUT_MS`, 5 s por defecto para conectar y otros 5 s para leer en el peor caso) la pantalla no atiende toques. Con WiFi caído no se hacen peticiones, así que la interfaz responde.
- **Cola:** hasta 24 eventos en NVS. Si se llena (24 acciones sin conexión) el firmware avisa «Cola llena» y no acepta más; los guardados no se pierden.
- **Confirmación:** una entrega registrada en pantalla solo cuenta en el servidor cuando este responde `aplicado` o `duplicado`; mientras tanto la pantalla marca «Por enviar: N». Si el servidor la **rechaza**, el aviso con el motivo se muestra 12 s y el siguiente sondeo devuelve la pantalla al estado del servidor.
- **Litros entregados:** ENTREGADO registra los litros planificados de la parada (no hay entrada numérica). Una entrega parcial debe registrarse como incidencia. INCIDENCIA envía una nota fija («incidencia reportada desde la terminal»).
- **Misión completada:** el servidor solo devuelve misiones activas; al completarse devuelve `mision: null` (comprobado con el simulador, no está escrito en el contrato). La terminal muestra «MISION COMPLETADA» solo si localmente todas las paradas estaban cerradas y la cola vacía; en otro caso (p. ej. misión cancelada) muestra «SIN MISION ASIGNADA».
- WiFi 2.4 GHz; pantalla 240×320 solo ASCII (sin tildes ni ñ en las fuentes integradas); textos largos se recortan; máximo 10 paradas por misión mostrada (con aviso si hay más).
- Sin batería ni sensores previstos. Alimentación del vehículo (5 V por USB-C), robustez mecánica y térmica en cabina: no evaluadas.

## 5. Qué requiere prueba física (nada de esto está probado)
Carga a la placa; orientación y calibración del táctil; legibilidad al sol; reconexión WiFi; comportamiento con la API apagada («SERVIDOR SIN RESPUESTA» y recuperación); persistencia de la cola tras cortar la luz con eventos pendientes; token rechazado (rotar el token a mitad de misión); consumo; arranque tras corte de luz; salida por Serial (¿USB nativo o puente?); SKU real de la placa y pinout del conector de expansión.

## 6. Firmware de la terminal (`firmware/esp32s3_monitor/`)
### 6.1 Qué hace
Pantalla principal: ID del vehículo y estado de conexión (cabecera verde = en línea, roja = problema), hora de la última sincronización («hace N s»), misión (#id y estado), zona de destino (sector), litros, instrucción de la parada, contadores (completadas / pendientes / incidencias), «Por enviar: N» (cola) y navegación `<` `>` entre paradas. Botones táctiles: **LLEGUE**, **INCIDENCIA** y **ENTREGADO**. ENTREGADO e INCIDENCIA piden **confirmación explícita** en una pantalla aparte (CONFIRMAR / CANCELAR; se cancela sola a los 15 s) para evitar toques accidentales. Pantallas de estado: sin WiFi, token rechazado (401/403), sin misión asignada, misión completada/cancelada, error de servidor (5xx/429) y servidor sin respuesta. Con WiFi caído o error de servidor y una misión en caché, la terminal **sigue operativa** mostrando la última misión conocida marcada «SIN SINCRONIZAR».

### 6.2 Decisiones de diseño
- **Persistencia: NVS (`Preferences`), no LittleFS.** Los datos son pequeños (cola ≤ 24 eventos ≈ 1,2 KB; misión ≤ 10 paradas < 4 KB), NVS escribe por clave (un corte de luz no deja una cadena a medias) y no hay que montar ni formatear un sistema de archivos. Límite: ~4000 bytes por cadena (de ahí el tope de 10 paradas) y desgaste del flash: se escribe la cola en cada acción del operador y la misión al cambiar (decenas de escrituras por turno). Si el formato de la cola cambia entre versiones del firmware, la cola guardada se descarta.
- **uid de evento** = `t<arranque>-<secuencia>-<aleatorio de 32 bits del hardware>`; el contador de arranques es persistente, por lo que es único aunque se reinicie o se pierda la NVS.
- **Entrega fiable:** el evento sale de la cola solo si el servidor responde `aplicado`, `duplicado` o `rechazado` para ese uid. Reintento con retroceso exponencial (2, 4, 8, 16, 32, 60 s; tope 60 s) ante red caída, 401/403, 429 o 5xx. Un 400/422 (lote ilegible) descarta el evento tras 5 intentos para no atascar la cola. Lotes de hasta 10 eventos (el servidor admite 50).
- **Estado local vs. servidor:** al actuar, la parada cambia al instante; al sondear, si hay eventos de esa parada aún sin confirmar se mantiene el estado local, y si no manda el servidor.
- **HTTP:** `WiFiClient` + `HTTPClient` locales a cada petición (se liberan con `end()`), `setConnectTimeout`/`setTimeout`, `begin()` comprobado, respuesta limitada a 24 KB, JSON con filtro de ArduinoJson, cabecera `X-Device-Token`.
- Sondeo cada `MISION_POLL_MS` (10 s) y latido cada `LATIDO_MS` (30 s), configurables.

### 6.3 Compilación (resultado real)
**Compila sin errores** (2026-10-17) con `arduino-cli` 1.5.1, core `esp32:esp32` 3.3.12, FQBN `esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,FlashMode=qio`, TFT_eSPI 2.5.43, ArduinoJson 7.4.3 y FT6336-arduino del fabricante: el binario ocupa 1 021 495 bytes (32 % de los 3 MB de aplicación) y 50 620 bytes de RAM estática (15 %). Única advertencia: `TOUCH_CS pin not defined` de TFT_eSPI (inofensiva: el táctil es I2C, no el de TFT_eSPI). **Compilar no prueba que funcione en la placa**: no se cargó a ninguna.

Comando exacto (Windows; `arduino-cli` viene en Arduino IDE 2.x; copie antes `config_dispositivo.h.example` a `config_dispositivo.h`):
```
"%LOCALAPPDATA%\Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe" core install esp32:esp32@3.3.12
arduino-cli compile --fqbn esp32:esp32:esp32s3:FlashSize=16M,PSRAM=opi,PartitionScheme=app3M_fat9M_16MB,FlashMode=qio firmware/esp32s3_monitor
```
Librerías (en `Documentos/Arduino/libraries`, del paquete del fabricante): TFT_eSPI 2.5.43 (con el `User_Setup.h` de la placa ya configurado: ILI9341 y pines de la sección 2), **FT6336-arduino** (sin versión: no tiene `library.properties`), **ArduinoJson 7.4.3** (el sketch requiere la API 7.x: `JsonDocument`). Core `esp32:esp32` 3.3.12. WiFi, HTTPClient y Preferences vienen con el core. **Atención:** el `User_Setup.h` está dentro de la carpeta de TFT_eSPI; si se reinstala la librería desde el gestor se pierde y la pantalla no funciona.
Opciones de placa: ESP32S3 Dev Module, Flash 16 MB, PSRAM **OPI** (módulo N16R8 según la wiki), esquema de particiones 16 MB (3 MB app). Si no sale texto por Serial, pruebe «USB CDC On Boot: Enabled» (no se verificó si el USB-C es nativo o puente).

### 6.4 Flasheo y prueba en la placa (pendiente de hacer)
1. Copie `config_dispositivo.h.example` a `config_dispositivo.h` (no se versiona) y complete `WIFI_SSID`, `WIFI_PASS`, `API_BASE_URL` (con `/api/v1`, IP de la Raspberry), `DEVICE_TOKEN` (el del vehículo) y `CISTERNA_ID` (solo se muestra).
2. En el servidor: registre la terminal (`python -m scripts.registrar_dispositivo CIS-001 --nombre "Camión 1"`; el token se muestra una vez) y asigne una misión desde el panel o con `POST /api/v1/misiones`.
3. Conecte el USB-C; si el puerto no aparece, mantenga **BOOT** (IO0) y pulse **RESET**; cargue desde Arduino IDE (opciones de 6.3) o con `arduino-cli upload -p COMx --fqbn ...`.
4. Prueba mínima: arranque → cabecera «EN LINEA» y misión; LLEGUE → «Por enviar» vuelve a 0 en segundos y el panel muestra la parada en «llegada»; ENTREGADO → pantalla de confirmación → CONFIRMAR; apague el router, registre una acción (debe mostrar «sin conexión» y «Por enviar: 1»), reinicie la placa (cola y misión deben seguir) y reconecte (la cola debe vaciarse sola); rote el token (debe aparecer «TOKEN RECHAZADO»).

### 6.5 Simulador del protocolo (sin placa)
`python -m scripts.simular_terminal --autoprueba` crea una base temporal, registra una terminal, asigna una misión de 2 paradas, arranca uvicorn en un puerto libre y ejecuta las mismas llamadas HTTP que el firmware (sondeo, cola con uid, reintento con retroceso, duplicado, rechazo, latido). También sirve contra una API real: `--base http://IP:8000/api/v1 --token <TOKEN> [--bucle]`. **No prueba** el firmware, la pantalla, el táctil ni la NVS: solo que el protocolo que el firmware implementa es aceptado por la API. Resultado de la última ejecución: `--autoprueba` contra la API real (uvicorn, base temporal): 14 comprobaciones, **todas OK**: token inválido → 401; `GET /dispositivo/mision` 200 con 2 paradas; uid únicos de 8-64 caracteres; con la API caída la cola se conserva y el retroceso es 2, 4, 8, 16 s; lote aplicado; el mismo lote reenviado → `duplicado`; evento de misión ajena y entrega repetida → `rechazado` (salen de la cola); latido 200; llegada+incidencia de la parada 2 aplicadas; tras cerrar todas las paradas el servidor devuelve `mision: null`.

### 6.6 Solución de problemas
| Síntoma | Causa probable |
|---|---|
| Pantalla en blanco | `User_Setup.h` de TFT_eSPI distinto al de la placa; luz de fondo IO45 |
| Toques desplazados o espejados | rotación del táctil distinta de la de la pantalla (`ts.setRotation(...)`) |
| «SIN WIFI» permanente | SSID/clave mal, red de 5 GHz (solo 2.4 GHz), router lejano |
| «SERVIDOR SIN RESPUESTA» | `API_BASE_URL` mal (¿falta `/api/v1`?), firewall de la Raspberry (puerto 8000), uvicorn en `127.0.0.1` en vez de `0.0.0.0` |
| «TOKEN RECHAZADO» (401/403) | token incorrecto, rotado o dispositivo desactivado; la cola se conserva y se envía al corregirlo |
| «ERROR SERVIDOR» / «LIMITE (429)» | 5xx o 429: reintenta solo |
| «Rechazado: …» | el servidor no aceptó el evento (transición no permitida, misión cancelada); el motivo viene del servidor |
| Errores de `JsonDocument` al compilar | ArduinoJson 6.x instalado: use 7.x |
| «library not valid» al instalar por ZIP | sección 8 |

## 7. Rutas de integración
- **ESP32-S3 (terminal de cisterna) → HTTP → FastAPI** (`GET /api/v1/dispositivo/mision`, `POST /api/v1/dispositivo/eventos`, `POST /api/v1/dispositivo/latido`) con el `X-Device-Token` del vehículo. La API corre en la Raspberry Pi o en un PC de la misma red. Autorización y roles: `docs/SEGURIDAD.md`, `docs/API.md`.
- **Raspberry Pi 4**: dos servicios systemd (`hidro360-api`, `hidro360-ui`), SQLite local, copias y comprobación de salud (sección 9).

## 8. Error de Arduino IDE «library not valid» — análisis
Error: `Library install failed: moving extracted archive to destination dir: library not valid`.
Lo que se examinó (no se dispone del ZIP original):
- El paquete del fabricante (`libraries/`) **no era una librería sino un conjunto de 21 librerías ya descomprimidas**. Un ZIP de ese conjunto no puede instalarse con «Añadir biblioteca .ZIP»: su raíz no tiene `library.properties` ni `src/`.
- Dentro hay dos carpetas **sin `library.properties`**: `FT6336-arduino` (solo `FT6336.h/.cpp` en la raíz) y `XT_DAC_Audio`. Son formato antiguo; el instalador por ZIP del IDE 2.x/`arduino-cli` puede rechazarlos como no válidos. Las otras 19 tienen estructura válida.
- Una carpeta `libraries` **dentro del sketch no es leída** por Arduino IDE: las librerías deben estar en `Documentos/Arduino/libraries/`.
- Comprobado: `C:\Users\Victor Montes\Documents\Arduino\libraries` ya contiene las 21 carpetas (copiadas a mano), que es el método que evita la validación del instalador.
**Causa más probable (no reproducida)**: intentar instalar por ZIP el conjunto completo o `FT6336-arduino`. **Solución**: copiar cada carpeta a `Documentos/Arduino/libraries/` (ya hecho) o, si se quiere instalar por ZIP, añadir a `FT6336-arduino` un `library.properties` mínimo (`name=FT6336`, `version=1.0.0`, `author=...`, `sentence=...`, `paragraph=...`, `category=Other`, `url=...`, `architectures=*`) y comprimir **esa carpeta sola**.
**Carpeta `PANTALLA_DE_MONITOREO` (resuelta, ver `docs/DECISIONES.md` D-05):** era el espacio de trabajo de Arduino. Su `libraries/` (354 MB) era idéntica por SHA-256 (5564 archivos) a `Documentos/Arduino/libraries` y se eliminó; su sketch de prueba del LED RGB se conservó en `firmware/pruebas/led_rgb/led_rgb.ino`. El firmware del tablero está en `firmware/esp32s3_monitor/`.

## 9. Raspberry Pi 4 (Raspberry Pi OS Lite)
Archivos en `deploy/raspberry/`: `install.sh`, `hidro360-api.service`, `hidro360-ui.service`, `backup.sh`, `healthcheck.sh`, `.env.example`. **Sin probar en una Pi.** (Antes `agua-clara-*.service`; renombrados a HIDRO360.)
```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
git clone <repo> /opt/hidro360 && cd /opt/hidro360
sudo bash deploy/raspberry/install.sh        # crea usuario, venv, dependencias, /etc/hidro360/hidro360.env y servicios
sudo nano /etc/hidro360/hidro360.env     # fije AGUA_CLARA_API_TOKEN y AGUA_CLARA_DEVICE_TOKEN
sudo systemctl enable --now hidro360-api hidro360-ui
bash deploy/raspberry/healthcheck.sh
```
- **Servicios**: API en `:8000` (uvicorn) y panel Flet en modo web en `:8501` (`python app.py --web --host 0.0.0.0 --sin-navegador`; el navegador cliente carga Flet desde internet, ver `docs/DECISIONES.md` D-04; la Pi no la necesita pero la primera ejecución de Flet descarga su cliente); reinicio controlado con `systemctl restart`; registros con `journalctl -u hidro360-api`.
- **Datos**: SQLite y trazas en `/var/lib/hidro360/`; copias con `backup.sh` (SQLite `.backup`, rotación 14 días; programar con cron).
- **Red**: use una red local aislada; con los tokens definidos, la API acepta peticiones de la red. **Sin tokens solo acepta localhost.** No exponga el panel fuera de la red local de confianza (p. ej. túnel SSH o firewall `ufw allow from 192.168.1.0/24`). Roles y autenticación: `docs/SEGURIDAD.md`.
- Pendiente: HTTPS, prueba de arranque tras corte de luz, instalación real en una Pi.
