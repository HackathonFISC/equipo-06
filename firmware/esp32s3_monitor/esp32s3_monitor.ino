/*
 * HIDRO360 (TEAM VIFY AI) - Tablero ESP32-S3 (Hosyond 2.8" ILI9341 240x320 + tactil FT6336G)
 * Placa: lcdwiki "2.8inch_ESP32-S3_Display", SKU ES3C28P (con tactil), modulo ESP32-S3 N16R8.
 * Tabla de pines verificada y pines libres: docs/HARDWARE.md. Este sketch SOLO usa los pines del
 * TFT/tactil (via TFT_eSPI y FT6336) y IO45 (luz de fondo); no usa IO42, SD, audio ni UART0.
 *
 * ESTADO: escrito a partir de los ejemplos del fabricante (Demo/) y la documentacion
 * https://www.lcdwiki.com/2.8inch_ESP32-S3_Display. NO COMPILADO NI PROBADO EN HARDWARE.
 *
 * Reglas de seguridad de diseno:
 *  - Solo habla con la API FastAPI (nunca con SQLite), con el token de DISPOSITIVO (cabecera X-API-Token).
 *  - Solo LEE /api/v1/estado y PUBLICA confirmaciones de recepcion. NO aprueba ni modifica planes.
 *  - Maneja WiFi caido, timeouts, HTTP != 200 y JSON invalido mostrando el error en pantalla.
 *
 * Librerias (carpeta libraries/ del fabricante, ver docs/HARDWARE.md): TFT_eSPI (User_Setup.h ya
 * configurado para esta placa), FT6336-arduino, ArduinoJson 7.x. Placa: ESP32S3 Dev Module,
 * PSRAM OPI, Flash 16MB.
 */
#include <TFT_eSPI.h>
#include <FT6336.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include "config_dispositivo.h"

// Pines del touch (documentacion del fabricante)
#define TP_SDA 16
#define TP_SCL 15
#define TP_INT 17
#define TP_RST 18

TFT_eSPI lcd = TFT_eSPI();
FT6336 ts = FT6336(TP_SDA, TP_SCL, TP_INT, TP_RST, 240, 320);

struct Estado {
  bool valido = false;
  int reportesActivos = 0, porRevisar = 0, sinInfo = 0;
  int planAprobadoId = 0, planPendienteId = 0, litrosAsignados = 0;
  int nTop = 0;
  char topSector[5][24];
  float topPuntaje[5];
  int nAsig = 0;
  char asigSector[8][24], asigCist[8][12];
  int asigLitros[8];
} est;

String errorMsg = "";    // fallo al LEER el estado -> pantalla "SIN DATOS"
String avisoMsg = "";    // fallo al CONFIRMAR -> solo un aviso en la pagina del plan (los datos siguen siendo validos)
unsigned long ultimoPoll = 0, ultimoOk = 0;
int pagina = 0;          // 0 resumen, 1 prioridades, 2 plan aprobado
int planConfirmado = 0;  // id del plan cuya recepcion ya se confirmo

void dibujarBarra() {
  lcd.fillRect(0, 0, 240, 22, TFT_NAVY);
  lcd.setTextColor(TFT_WHITE, TFT_NAVY);
  lcd.drawString("HIDRO360", 6, 3, 2);
  bool ok = WiFi.status() == WL_CONNECTED && errorMsg.length() == 0;
  lcd.fillCircle(224, 11, 6, ok ? TFT_GREEN : TFT_RED);
}

void dibujarPie() {
  lcd.fillRect(0, 290, 240, 30, TFT_NAVY);
  lcd.setTextColor(TFT_WHITE, TFT_NAVY);
  lcd.drawString("<", 14, 297, 4);
  lcd.drawString(">", 214, 297, 4);
  if (pagina == 2 && est.planAprobadoId && planConfirmado != est.planAprobadoId)
    lcd.drawString("Confirmar recepcion", 52, 299, 2);
  else
    lcd.drawString("pag " + String(pagina + 1) + "/3", 100, 299, 2);
}

void dibujar() {
  lcd.fillScreen(TFT_WHITE);
  dibujarBarra();
  lcd.setTextColor(TFT_BLACK, TFT_WHITE);
  if (errorMsg.length()) {
    lcd.setTextColor(TFT_RED, TFT_WHITE);
    lcd.drawString("SIN DATOS", 10, 40, 4);
    lcd.drawString(errorMsg.substring(0, 34), 10, 78, 2);
    if (est.valido) {
      lcd.setTextColor(TFT_DARKGREY, TFT_WHITE);
      lcd.drawString("ultimo dato hace " + String((millis() - ultimoOk) / 1000) + " s", 10, 100, 2);
    }
  } else if (!est.valido) {
    lcd.drawString("Conectando...", 10, 40, 4);
  } else if (pagina == 0) {
    lcd.drawString("Resumen operativo", 10, 32, 2);
    lcd.drawString("Reportes activos: " + String(est.reportesActivos), 10, 60, 2);
    lcd.drawString("Por revisar: " + String(est.porRevisar), 10, 84, 2);
    lcd.drawString("Sectores sin info: " + String(est.sinInfo), 10, 108, 2);
    lcd.drawString("Plan aprobado: " + (est.planAprobadoId ? "#" + String(est.planAprobadoId) : String("ninguno")), 10, 140, 2);
    lcd.drawString("Plan por revisar: " + (est.planPendienteId ? "#" + String(est.planPendienteId) : String("ninguno")), 10, 164, 2);
    lcd.setTextColor(TFT_DARKGREY, TFT_WHITE);
    lcd.drawString("Solo lectura. Aprueba una persona", 10, 230, 1);
    lcd.drawString("en el panel web.", 10, 242, 1);
  } else if (pagina == 1) {
    lcd.drawString("Prioridades (top)", 10, 32, 2);
    for (int i = 0; i < est.nTop; i++) {
      lcd.drawString(String(i + 1) + ". " + String(est.topSector[i]), 10, 60 + i * 40, 2);
      lcd.drawString(String(est.topPuntaje[i], 1) + " pts", 150, 60 + i * 40, 2);
    }
    if (!est.nTop) lcd.drawString("Sin prioridades aun", 10, 60, 2);
  } else {
    lcd.drawString("Plan aprobado", 10, 32, 2);
    if (!est.planAprobadoId) {
      lcd.drawString("No hay plan aprobado", 10, 60, 2);
    } else {
      lcd.drawString("#" + String(est.planAprobadoId) + "  " + String(est.litrosAsignados) + " L asignados", 10, 54, 2);
      for (int i = 0; i < est.nAsig; i++) {
        lcd.drawString(String(est.asigSector[i]) + " <- " + String(est.asigCist[i]), 10, 80 + i * 24, 2);
        lcd.drawString(String(est.asigLitros[i]) + " L", 190, 80 + i * 24, 1);
      }
      if (planConfirmado == est.planAprobadoId) {
        lcd.setTextColor(TFT_DARKGREEN, TFT_WHITE);
        lcd.drawString("Recepcion confirmada", 10, 268, 2);
      } else if (avisoMsg.length()) {
        lcd.setTextColor(TFT_RED, TFT_WHITE);
        lcd.drawString(avisoMsg.substring(0, 34), 10, 268, 2);
      }
    }
  }
  dibujarPie();
}

bool consultarEstado() {
  if (WiFi.status() != WL_CONNECTED) { errorMsg = "WiFi desconectado"; return false; }
  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(String(API_BASE_URL) + "/api/v1/estado")) { errorMsg = "URL invalida"; return false; }
  http.addHeader("X-API-Token", API_TOKEN);
  int code = http.GET();
  if (code <= 0) { errorMsg = "Sin respuesta: " + http.errorToString(code); http.end(); return false; }
  if (code != 200) { errorMsg = "HTTP " + String(code); http.end(); return false; }
  String cuerpo = http.getString();
  http.end();
  if (cuerpo.length() == 0 || cuerpo.length() > 120000) { errorMsg = "Respuesta vacia/enorme"; return false; }

  JsonDocument filtro;
  filtro["reportes_activos"] = true;
  filtro["reportes_por_revisar"] = true;
  filtro["sectores_sin_informacion"] = true;
  filtro["prioridades_top"][0]["sector"] = true;
  filtro["prioridades_top"][0]["puntaje"] = true;
  filtro["plan_pendiente_de_revision"]["id"] = true;
  filtro["plan_aprobado"]["id"] = true;
  filtro["plan_aprobado"]["resumen"]["litros_asignados"] = true;
  filtro["plan_aprobado"]["asignaciones"][0]["sector"] = true;
  filtro["plan_aprobado"]["asignaciones"][0]["cisterna_id"] = true;
  filtro["plan_aprobado"]["asignaciones"][0]["litros"] = true;
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, cuerpo, DeserializationOption::Filter(filtro));
  if (err) { errorMsg = String("JSON invalido: ") + err.c_str(); return false; }
  if (!doc["reportes_activos"].is<int>()) { errorMsg = "Formato inesperado"; return false; }

  est.reportesActivos = doc["reportes_activos"] | 0;
  est.porRevisar = doc["reportes_por_revisar"] | 0;
  est.sinInfo = doc["sectores_sin_informacion"] | 0;
  est.planPendienteId = doc["plan_pendiente_de_revision"]["id"] | 0;
  est.planAprobadoId = doc["plan_aprobado"]["id"] | 0;
  est.litrosAsignados = doc["plan_aprobado"]["resumen"]["litros_asignados"] | 0;
  est.nTop = 0;
  for (JsonObject p : doc["prioridades_top"].as<JsonArray>()) {
    if (est.nTop >= 5) break;
    strlcpy(est.topSector[est.nTop], p["sector"] | "?", sizeof(est.topSector[0]));
    est.topPuntaje[est.nTop++] = p["puntaje"] | 0.0f;
  }
  est.nAsig = 0;
  for (JsonObject a : doc["plan_aprobado"]["asignaciones"].as<JsonArray>()) {
    if (est.nAsig >= 8) break;
    strlcpy(est.asigSector[est.nAsig], a["sector"] | "?", sizeof(est.asigSector[0]));
    strlcpy(est.asigCist[est.nAsig], a["cisterna_id"] | "?", sizeof(est.asigCist[0]));
    est.asigLitros[est.nAsig++] = a["litros"] | 0;
  }
  est.valido = true;
  errorMsg = "";
  ultimoOk = millis();
  return true;
}

// Publica "plan_recibido": el servidor solo lo AUDITA; no cambia el plan.
void confirmarRecepcion() {
  if (WiFi.status() != WL_CONNECTED) { avisoMsg = "WiFi desconectado"; return; }
  if (!est.planAprobadoId) return;
  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  if (!http.begin(String(API_BASE_URL) + "/api/v1/dispositivos/confirmaciones")) { avisoMsg = "URL invalida"; return; }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-API-Token", API_TOKEN);
  JsonDocument body;
  body["dispositivo_id"] = DEVICE_ID;
  body["plan_id"] = est.planAprobadoId;
  body["tipo"] = "plan_recibido";
  String s;
  serializeJson(body, s);
  int code = http.POST(s);
  http.end();
  if (code == 202) { planConfirmado = est.planAprobadoId; avisoMsg = ""; }
  else avisoMsg = code > 0 ? "Rechazada HTTP " + String(code) : "Sin respuesta";
}

void setup() {
  Serial.begin(115200);
  lcd.begin();
  lcd.setRotation(0);
  lcd.fillScreen(TFT_WHITE);
  // IO45 = luz de fondo (TFT_BL en el User_Setup.h de TFT_eSPI ya la enciende; esto es redundante e inofensivo).
  // IO45 es pin de strapping del ESP32-S3 (docs/HARDWARE.md): no conectar nada externo a el.
  pinMode(45, OUTPUT);
  digitalWrite(45, HIGH);
  ts.begin();
  ts.setRotation(ROTATION_NORMAL);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  dibujar();
}

void loop() {
  static unsigned long tToque = 0, tReconexion = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - tReconexion > 10000) {
    tReconexion = millis();
    WiFi.reconnect();
  }
  if (millis() - ultimoPoll > POLL_MS || ultimoPoll == 0) {
    ultimoPoll = millis();
    consultarEstado();
    dibujar();
  }
  ts.read();
  if (ts.isTouched && millis() - tToque > 400) {
    tToque = millis();
    int x = ts.points[0].x, y = ts.points[0].y;
    if (y > 285) {
      if (x < 60) pagina = (pagina + 2) % 3;
      else if (x > 180) pagina = (pagina + 1) % 3;
      else if (pagina == 2) confirmarRecepcion();
      dibujar();
    }
  }
  delay(20);
}
