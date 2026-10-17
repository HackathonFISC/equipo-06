# Hardware: pantalla ESP32-S3 y Raspberry Pi 4 (HIDRO360)

> **Estado honesto.** El firmware del ESP32-S3 y los scripts de la Raspberry Pi están **escritos pero NO compilados ni probados en hardware**: en este entorno no hay `arduino-cli`, placa ni Raspberry. Lo verificado por software: el contrato de la API que usan (`tests/test_backend.py`). Nada de lo siguiente se declara funcional sin prueba física.

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
| UART0 | IO43 e IO44 (RXD0/TXD0 según la wiki) | wiki; asignación RX/TX no concluyente | wiki. En el chip ESP32-S3 U0TXD es GPIO43 y U0RXD GPIO44 (dato general del chip, no está en el repo): confirmar con la serigrafía antes de cablear |
| Batería (ADC) | IO9 | wiki | wiki; `Demo/Example_13_Get_Battery_Voltage/GetBatteryVoltage/GetBatteryVoltage.ino` usa `ADC_UNIT_1`, `ADC_CHANNEL_8` (que ADC1 canal 8 sea GPIO9 es dato del chip, no del repo) |
| **Conector «Expand pin»** (1.25 mm, 4 pines) | GPIO **2, 3, 14, 21**, «normal IO» | wiki (única fuente) | wiki. **No da el orden pin a pin del conector (cuál es VCC, GND o señal)**: no verificado |
| Conectores UART (4P), I2C (4P, comparte IO16/IO15 con el táctil), batería (2P), altavoz (2P) | los indicados | wiki (solo existencia) | wiki. Orden de pines y polaridad: **no verificado** |
| Strapping, USB, flash/PSRAM | strapping 0, 3, 45, 46; USB 19/20; flash/PSRAM octal en 26-37 con módulos R8 | **no verificado en el repo** | datos generales del chip (datasheet de Espressif), no consultado en esta revisión: confirmar antes de usarlos |

**Pines realmente libres**: la única evidencia es la wiki: **GPIO2, GPIO3, GPIO14 y GPIO21** salen al conector de expansión. Ningún otro GPIO se puede dar por libre: o están asignados arriba o no hay evidencia (**no verificado**). GPIO3 es pin de strapping según el datasheet general del chip (no verificado aquí). Los comentarios de pines dentro de los `.ino` de `Demo/` (p. ej. `DC=2`, `LED=21`, `BAT_VOLT_ADC 34`) están copiados de otras placas y **no son fiables**; mandan la wiki y las constantes de código.

## 3. Comprobación del sketch contra la tabla
`firmware/esp32s3_monitor/esp32s3_monitor.ino` usa: TFT por TFT_eSPI (pines de `User_Setup.h`, coinciden), táctil 16/15/17/18 (coinciden) e **IO45** (luz de fondo, coincide). **No usa** IO42, SD, audio, UART0 ni pines de expansión. **No se encontraron conflictos de pines.** Observaciones:
- `pinMode(45)/digitalWrite(45, HIGH)` es redundante: TFT_eSPI ya enciende `TFT_BL` (45). Se mantiene sin cambiar el comportamiento. IO45 es pin de strapping del chip: no conecte nada externo a él.
- `firmware/pruebas/led_rgb/led_rgb.ino` usa IO42 con `NEO_RGB`; los ejemplos del fabricante usan `NEO_GRB`/`NEO_GRBW`: si rojo y verde salen cambiados es el orden de color (no probado).
- El bus I2C 15/16 lo comparten táctil, códec y conector I2C: no añada otros dispositivos sin comprobar direcciones.

## 4. Limitaciones físicas
HTTP sin cifrar con token en cabecera (solo red local de confianza); WiFi 2.4 GHz; la pantalla es de **solo lectura** más un botón de confirmación; sin batería ni sensores previstos (la propuesta descarta sensores/GPIO adicionales); pantalla 240×320, los textos largos se recortan (no probado).

## 5. Qué requiere prueba física (nada de esto está probado)
Compilación (versiones de core y librerías), carga a la placa, orientación y calibración del táctil, legibilidad, reconexión WiFi, comportamiento con la API apagada («SIN DATOS» y recuperación), consumo, arranque tras corte de luz, SKU real de la placa y pinout del conector de expansión.

## 6. Firmware (`firmware/esp32s3_monitor/`)
1. Copie `config_dispositivo.h.example` a `config_dispositivo.h` (no se versiona) y ponga WiFi, URL de la API y el **token de DISPOSITIVO** (`AGUA_CLARA_DEVICE_TOKEN` en el servidor; el prefijo `AGUA_CLARA_` se conserva por compatibilidad). `DEVICE_ID` de ejemplo: `hidro360-pantalla-01`.
2. Arduino IDE: placa *ESP32S3 Dev Module*, PSRAM *OPI*, flash 16 MB; librerías en `Documentos/Arduino/libraries` (TFT_eSPI 2.5.43, ArduinoJson 7.4.3, FT6336-arduino, según el paquete del fabricante; la wiki no fija versiones de core ni de librerías).
3. Pantallas táctiles: resumen operativo, top de prioridades, plan aprobado y botón «Confirmar recepción» (`POST /api/v1/dispositivos/confirmaciones`, que solo se audita).
4. Solo habla con FastAPI por HTTP (nunca SQLite), cabecera `X-API-Token`. **No aprueba ni modifica nada.** Maneja WiFi caído, timeout, HTTP ≠ 200 y JSON inválido mostrando «SIN DATOS» (revisado leyendo el código, no ejecutado).
5. Revisión de código, defectos corregidos: (a) un fallo al *confirmar* ponía la pantalla en «SIN DATOS» aunque los datos eran válidos; ahora es un aviso aparte en la página del plan; (b) faltaba el timeout de conexión (`setConnectTimeout`); (c) la confirmación no comprobaba `http.begin` ni el WiFi. **No se pudo compilar** (no hay `arduino-cli`), así que estos cambios no están verificados por compilador.

## 7. Rutas de integración
- **ESP32-S3 → HTTP → FastAPI** (`GET /api/v1/estado`, `POST /api/v1/dispositivos/confirmaciones`) con el token de dispositivo. La API corre en la Raspberry Pi o en un PC de la misma red. Autorización y roles: `docs/SEGURIDAD.md`, `docs/API.md`.
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
