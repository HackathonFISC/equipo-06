/*
 * HIDRO360 (TEAM VIFY AI) - TERMINAL OPERATIVA DE CARRO CISTERNA
 * Placa: Hosyond/lcdwiki "2.8inch ESP32-S3 Display" (ES3C28P, ILI9341V 240x320, tactil FT6336G, N16R8).
 * Pines: docs/HARDWARE.md. Este sketch solo usa TFT (TFT_eSPI, User_Setup.h del fabricante) y tactil 16/15/17/18.
 * La placa NO tiene GPS verificado: la terminal no reporta posicion; el destino viene de la mision.
 *
 * Protocolo (solo HTTP contra FastAPI, nunca SQLite; la identidad sale del token del vehiculo):
 *   GET  /dispositivo/mision   -> mision actual (se cachea en NVS para mostrarla sin conexion)
 *   POST /dispositivo/eventos  -> llegada | entrega | incidencia, idempotente por uid
 *   POST /dispositivo/latido   -> firmware, rssi, pendientes, uptime
 *
 * Cola de eventos: se guarda en NVS (Preferences) en cada cambio; sobrevive a reinicios y cortes de luz.
 * Un evento sale de la cola solo cuando el servidor responde aplicado | duplicado | rechazado.
 *
 * ESTADO: ver docs/HARDWARE.md (compilacion y pruebas en placa).
 * Librerias: TFT_eSPI 2.5.43, FT6336-arduino (fabricante), ArduinoJson 7.x, core esp32 3.x (WiFi, HTTPClient, Preferences).
 */
#include <TFT_eSPI.h>
#include <FT6336.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include "config_dispositivo.h"

#define FIRMWARE_VERSION "2.0.0"

// Tactil (documentacion del fabricante, comprobado contra Demo/Example_08)
#define TP_SDA 16
#define TP_SCL 15
#define TP_INT 17
#define TP_RST 18

#define MAX_PARADAS 10
#define MAX_COLA 24
#define LOTE_EVENTOS 10
#define BACKOFF_MIN_MS 2000UL
#define BACKOFF_MAX_MS 60000UL
#define MAX_JSON_BYTES 24000
#define CONFIRM_TIMEOUT_MS 15000UL

TFT_eSPI lcd = TFT_eSPI();
FT6336 ts = FT6336(TP_SDA, TP_SCL, TP_INT, TP_RST, 240, 320);
Preferences prefs;

// ---------------------------------------------------------------- modelo
enum EstadoParada : uint8_t { P_PENDIENTE = 0, P_LLEGADA, P_ENTREGADA, P_INCIDENCIA };
enum TipoEvento : uint8_t { E_LLEGADA = 0, E_ENTREGA, E_INCIDENCIA };
enum NetEstado : uint8_t { NET_INICIANDO = 0, NET_OK, NET_SIN_WIFI, NET_TOKEN, NET_LIMITE, NET_SERVIDOR, NET_SIN_RESPUESTA };

struct Parada {
  uint8_t orden = 0;
  char sector[28] = "";
  char instruccion[72] = "";
  int32_t litros = 0;
  int32_t litrosEntregados = 0;
  EstadoParada estado = P_PENDIENTE;
};

struct Mision {
  bool valida = false;      // hay mision en cache/servidor
  int32_t id = 0;
  char estado[14] = "";     // asignada | en_curso | completada | cancelada
  uint8_t n = 0;
  bool truncada = false;
  Parada p[MAX_PARADAS];
} mision;

struct Evento {
  char uid[28];
  uint8_t tipo;
  uint8_t orden;
  uint8_t intentos;         // solo cuenta rechazos HTTP 4xx de formato
  int32_t misionId;
  int32_t litros;
};
Evento cola[MAX_COLA];
uint8_t nCola = 0;

// ---------------------------------------------------------------- estado de ejecucion
NetEstado net = NET_INICIANDO;
int netHttp = 0;
bool sincronizadoDesdeArranque = false;  // true tras la 1a respuesta valida de GET /mision en esta sesion
char ultimaSyncHora[12] = "";            // HH:MM:SS (UTC) segun servidor_hora
unsigned long ultimaSyncMs = 0;
char avisoTxt[40] = "";                  // aviso transitorio (rechazos, doble toque, etc.)
unsigned long avisoHasta = 0;
uint32_t bootCnt = 0, seqEvento = 0;
unsigned long proxPoll = 0, proxLatido = 0, proxEnvio = 0, proxWifi = 0;
uint8_t backoffN = 0;
bool dirty = true, dirtyTodo = true;
uint8_t sel = 0;                         // indice de parada mostrada

enum Modo : uint8_t { M_NORMAL = 0, M_CONFIRMAR };
Modo modo = M_NORMAL;
TipoEvento confirmTipo = E_ENTREGA;
unsigned long confirmDesde = 0;

// ---------------------------------------------------------------- utilidades
void aviso(const char* t, unsigned long ms = 6000) {
  strlcpy(avisoTxt, t, sizeof(avisoTxt));
  avisoHasta = millis() + ms;
  dirty = true;
}

const char* tipoStr(uint8_t t) { return t == E_LLEGADA ? "llegada" : (t == E_ENTREGA ? "entrega" : "incidencia"); }

int contarEstado(EstadoParada e) {
  int c = 0;
  for (int i = 0; i < mision.n; i++) if (mision.p[i].estado == e) c++;
  return c;
}
bool paradaAbierta(const Parada& p) { return p.estado == P_PENDIENTE || p.estado == P_LLEGADA; }
int abiertas() { int c = 0; for (int i = 0; i < mision.n; i++) if (paradaAbierta(mision.p[i])) c++; return c; }
bool hayEventoEnCola(int32_t misionId, uint8_t orden) {
  for (int i = 0; i < nCola; i++) if (cola[i].misionId == misionId && cola[i].orden == orden) return true;
  return false;
}
void seleccionarPrimeraAbierta() {
  for (int i = 0; i < mision.n; i++) if (paradaAbierta(mision.p[i])) { sel = i; return; }
  sel = mision.n ? mision.n - 1 : 0;
}

// ---------------------------------------------------------------- persistencia (NVS)
// Se eligio NVS/Preferences (no LittleFS): los datos son pequenos (cola < 1 KB, mision < 3 KB), NVS es
// transaccional por clave (una escritura interrumpida no deja un blob a medias) y no hay que montar ni formatear
// un sistema de archivos. Limite: ~4000 bytes por cadena, por eso la mision se limita a MAX_PARADAS.
void guardarCola() {
  prefs.putUChar("ncola", nCola);
  prefs.putBytes("cola", cola, sizeof(cola));
}
void cargarCola() {
  nCola = 0;
  size_t tam = prefs.getBytesLength("cola");
  if (tam != sizeof(cola)) { if (tam) Serial.println("cola NVS con formato distinto: descartada"); return; }
  prefs.getBytes("cola", cola, sizeof(cola));
  nCola = min<uint8_t>(prefs.getUChar("ncola", 0), MAX_COLA);
}

void guardarMision() {
  if (!mision.valida) { prefs.remove("mision"); return; }
  JsonDocument d;
  d["id"] = mision.id;
  d["e"] = mision.estado;
  JsonArray ps = d["p"].to<JsonArray>();
  for (int i = 0; i < mision.n; i++) {
    JsonObject o = ps.add<JsonObject>();
    o["o"] = mision.p[i].orden;
    o["s"] = mision.p[i].sector;
    o["i"] = mision.p[i].instruccion;
    o["l"] = mision.p[i].litros;
    o["le"] = mision.p[i].litrosEntregados;
    o["st"] = (int)mision.p[i].estado;
  }
  String s;
  serializeJson(d, s);
  if (s.length() < 3900) prefs.putString("mision", s);
  else Serial.println("mision demasiado grande para NVS: no se guarda");
}
void cargarMision() {
  String s = prefs.getString("mision", "");
  if (s.length() == 0) return;
  JsonDocument d;
  if (deserializeJson(d, s)) return;
  mision.valida = true;
  mision.id = d["id"] | 0;
  strlcpy(mision.estado, d["e"] | "", sizeof(mision.estado));
  mision.n = 0;
  for (JsonObject o : d["p"].as<JsonArray>()) {
    if (mision.n >= MAX_PARADAS) break;
    Parada& p = mision.p[mision.n++];
    p.orden = o["o"] | 0;
    strlcpy(p.sector, o["s"] | "", sizeof(p.sector));
    strlcpy(p.instruccion, o["i"] | "", sizeof(p.instruccion));
    p.litros = o["l"] | 0;
    p.litrosEntregados = o["le"] | 0;
    p.estado = (EstadoParada)constrain((int)(o["st"] | 0), 0, 3);
  }
}

// ---------------------------------------------------------------- cola de eventos
void nuevoUid(char* out, size_t n) {
  // arranque persistente + secuencia + aleatorio de hardware => unico aun tras reinicios y perdida de NVS
  snprintf(out, n, "t%lx-%lx-%08lx", (unsigned long)bootCnt, (unsigned long)(++seqEvento), (unsigned long)esp_random());
}

bool encolar(TipoEvento t, const Parada& p) {
  if (nCola >= MAX_COLA) { aviso("Cola llena: espere conexion"); return false; }
  Evento& e = cola[nCola++];
  memset(&e, 0, sizeof(e));
  nuevoUid(e.uid, sizeof(e.uid));
  e.tipo = t;
  e.misionId = mision.id;
  e.orden = p.orden;
  e.litros = (t == E_ENTREGA) ? p.litros : 0;
  guardarCola();           // primero la cola (lo que se enviara), luego el estado local
  proxEnvio = 0;           // intentar enviar ya
  backoffN = 0;
  return true;
}

void quitarEvento(int i) {
  for (int k = i; k < nCola - 1; k++) cola[k] = cola[k + 1];
  nCola--;
}

// ---------------------------------------------------------------- HTTP
// Devuelve el codigo HTTP (>0) o un valor <= 0: -1 sin WiFi, -2 begin fallo, -3 respuesta enorme, otros = error de HTTPClient.
int llamar(bool post, const char* ruta, const String& cuerpo, String& resp) {
  resp = "";
  if (WiFi.status() != WL_CONNECTED) return -1;
  WiFiClient cli;
  HTTPClient http;
  http.setConnectTimeout(HTTP_TIMEOUT_MS);
  http.setTimeout(HTTP_TIMEOUT_MS);
  http.setReuse(false);
  String url = String(API_BASE_URL) + ruta;
  if (!http.begin(cli, url)) return -2;
  http.addHeader("X-Device-Token", DEVICE_TOKEN);
  int code;
  if (post) {
    http.addHeader("Content-Type", "application/json");
    code = http.POST((uint8_t*)cuerpo.c_str(), cuerpo.length());
  } else {
    code = http.GET();
  }
  if (code > 0) {
    int tam = http.getSize();
    if (tam > MAX_JSON_BYTES) { http.end(); return -3; }
    resp = http.getString();
    if (resp.length() > MAX_JSON_BYTES) resp = "";
  }
  http.end();     // libera conexion y buffers
  return code;
}

void clasificarRed(int code) {
  netHttp = code;
  if (code == 200 || code == 202) net = NET_OK;
  else if (code == 401 || code == 403) net = NET_TOKEN;
  else if (code == 429) net = NET_LIMITE;
  else if (code == -1) net = NET_SIN_WIFI;
  else if (code <= 0) net = NET_SIN_RESPUESTA;
  else net = NET_SERVIDOR;
  dirty = true;
}

// ---------------------------------------------------------------- sondeo de mision
void aplicarMision(JsonObjectConst m, const char* hora) {
  Mision nueva;
  nueva.valida = true;
  nueva.id = m["id"] | 0;
  strlcpy(nueva.estado, m["estado"] | "", sizeof(nueva.estado));
  for (JsonObjectConst o : m["paradas"].as<JsonArrayConst>()) {
    if (nueva.n >= MAX_PARADAS) { nueva.truncada = true; break; }
    Parada& p = nueva.p[nueva.n++];
    p.orden = o["orden"] | (nueva.n);
    strlcpy(p.sector, o["sector"] | "?", sizeof(p.sector));
    strlcpy(p.instruccion, o["instruccion"] | "", sizeof(p.instruccion));
    p.litros = o["litros"] | 0;
    p.litrosEntregados = o["litros_entregados"] | 0;
    const char* est = o["estado"] | "pendiente";
    p.estado = !strcmp(est, "llegada") ? P_LLEGADA : !strcmp(est, "entregada") ? P_ENTREGADA
             : !strcmp(est, "incidencia") ? P_INCIDENCIA : P_PENDIENTE;
    // Si hay eventos nuestros sin confirmar para esta parada, el estado local manda (el servidor aun no los vio).
    if (mision.valida && mision.id == nueva.id && hayEventoEnCola(nueva.id, p.orden)) {
      for (int i = 0; i < mision.n; i++) if (mision.p[i].orden == p.orden) { p.estado = mision.p[i].estado; p.litrosEntregados = mision.p[i].litrosEntregados; }
    }
  }
  bool cambioMision = !mision.valida || mision.id != nueva.id;
  mision = nueva;
  if (cambioMision) seleccionarPrimeraAbierta();
  if (sel >= mision.n) sel = mision.n ? mision.n - 1 : 0;
  guardarMision();
  (void)hora;
}

void sondearMision() {
  String resp;
  int code = llamar(false, "/dispositivo/mision", "", resp);
  clasificarRed(code);
  if (code != 200) return;

  JsonDocument filtro;
  filtro["servidor_hora"] = true;
  filtro["mision"]["id"] = true;
  filtro["mision"]["estado"] = true;
  filtro["mision"]["paradas"][0]["orden"] = true;
  filtro["mision"]["paradas"][0]["sector"] = true;
  filtro["mision"]["paradas"][0]["litros"] = true;
  filtro["mision"]["paradas"][0]["instruccion"] = true;
  filtro["mision"]["paradas"][0]["estado"] = true;
  filtro["mision"]["paradas"][0]["litros_entregados"] = true;
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, resp, DeserializationOption::Filter(filtro));
  if (err) { net = NET_SERVIDOR; netHttp = 200; Serial.printf("JSON invalido: %s\n", err.c_str()); return; }

  const char* hora = doc["servidor_hora"] | "";
  if (strlen(hora) >= 19) { memcpy(ultimaSyncHora, hora + 11, 8); ultimaSyncHora[8] = 0; }
  ultimaSyncMs = millis();
  sincronizadoDesdeArranque = true;

  JsonObjectConst m = doc["mision"].as<JsonObjectConst>();
  if (doc["mision"].isNull() || m.isNull()) {
    // El servidor solo devuelve misiones ACTIVAS: al completarse devuelve null. Si localmente ya estaban todas las
    // paradas cerradas y no queda nada por enviar, se muestra "MISION COMPLETADA"; si no (cancelada/reasignada) se limpia.
    if (mision.valida && mision.n > 0 && abiertas() == 0 && nCola == 0) {
      if (strcmp(mision.estado, "completada")) { strlcpy(mision.estado, "completada", sizeof(mision.estado)); guardarMision(); }
    } else if (mision.valida) { mision = Mision(); guardarMision(); }
  } else {
    aplicarMision(m, hora);
  }
  dirty = dirtyTodo = true;
}

// ---------------------------------------------------------------- envio de eventos con retroceso exponencial
void programarReintento() {
  unsigned long espera = BACKOFF_MIN_MS << min<uint8_t>(backoffN, 5);
  if (espera > BACKOFF_MAX_MS) espera = BACKOFF_MAX_MS;
  if (backoffN < 10) backoffN++;
  proxEnvio = millis() + espera;
}

void enviarCola() {
  if (nCola == 0 || millis() < proxEnvio) return;
  int n = min<int>(nCola, LOTE_EVENTOS);
  JsonDocument body;
  JsonArray arr = body["eventos"].to<JsonArray>();
  for (int i = 0; i < n; i++) {
    JsonObject o = arr.add<JsonObject>();
    o["uid"] = cola[i].uid;
    o["tipo"] = tipoStr(cola[i].tipo);
    o["mision_id"] = cola[i].misionId;
    o["parada_orden"] = cola[i].orden;
    if (cola[i].tipo == E_ENTREGA) o["litros_entregados"] = cola[i].litros;
    o["nota"] = cola[i].tipo == E_INCIDENCIA ? "incidencia reportada desde la terminal" : "";
    o["fecha_dispositivo"] = nullptr;   // sin reloj sincronizado: el servidor pone la hora
  }
  String s, resp;
  serializeJson(body, s);
  int code = llamar(true, "/dispositivo/eventos", s, resp);
  clasificarRed(code);

  if (code == 200) {
    JsonDocument filtro;
    filtro["resultados"][0]["uid"] = true;
    filtro["resultados"][0]["resultado"] = true;
    filtro["resultados"][0]["motivo"] = true;
    JsonDocument doc;
    if (deserializeJson(doc, resp, DeserializationOption::Filter(filtro))) { programarReintento(); return; }
    bool alguno = false;
    for (JsonObject r : doc["resultados"].as<JsonArray>()) {
      const char* uid = r["uid"] | "";
      const char* res = r["resultado"] | "";
      bool final = !strcmp(res, "aplicado") || !strcmp(res, "duplicado") || !strcmp(res, "rechazado");
      if (!final) continue;                 // resultado desconocido: se conserva y se reintenta
      for (int i = 0; i < nCola; i++) {
        if (strcmp(cola[i].uid, uid)) continue;
        if (!strcmp(res, "rechazado")) {
          char t[40];
          snprintf(t, sizeof(t), "Rechazado: %s", (const char*)(r["motivo"] | "sin motivo"));
          aviso(t, 12000);
        }
        quitarEvento(i);
        alguno = true;
        break;
      }
    }
    if (alguno) { guardarCola(); guardarMision(); backoffN = 0; proxEnvio = 0; proxPoll = 0; }  // sondear ya para reflejar el servidor
    else programarReintento();
    dirty = true;
  } else if (code == 400 || code == 422) {
    // el servidor no entiende el lote: no reintentar para siempre
    for (int i = 0; i < n; i++) if (cola[i].intentos < 255) cola[i].intentos++;
    for (int i = nCola - 1; i >= 0; i--) if (cola[i].intentos >= 5) { aviso("Evento descartado (HTTP 4xx)", 12000); quitarEvento(i); }
    guardarCola();
    programarReintento();
  } else {
    programarReintento();   // red caida, 401/403 (token), 429, 5xx: se conserva todo
  }
}

void enviarLatido() {
  JsonDocument body;
  body["firmware"] = FIRMWARE_VERSION;
  body["wifi_rssi"] = WiFi.status() == WL_CONNECTED ? WiFi.RSSI() : 0;
  body["pendientes"] = nCola;
  body["uptime_s"] = (uint32_t)(millis() / 1000);
  String s, resp;
  serializeJson(body, s);
  int code = llamar(true, "/dispositivo/latido", s, resp);
  clasificarRed(code);
}

// ---------------------------------------------------------------- acciones del operador
void registrar(TipoEvento t) {
  if (!mision.valida || mision.n == 0) return;
  if (strcmp(mision.estado, "asignada") && strcmp(mision.estado, "en_curso")) { aviso("Mision no activa"); return; }
  Parada& p = mision.p[sel];
  if (t == E_LLEGADA && p.estado != P_PENDIENTE) { aviso("Llegada ya registrada"); return; }
  if (t != E_LLEGADA && !paradaAbierta(p)) { aviso("Parada ya cerrada"); return; }
  if (!encolar(t, p)) return;
  p.estado = t == E_LLEGADA ? P_LLEGADA : (t == E_ENTREGA ? P_ENTREGADA : P_INCIDENCIA);
  if (t == E_ENTREGA) p.litrosEntregados = p.litros;
  guardarMision();
  if (t != E_LLEGADA) seleccionarPrimeraAbierta();
  aviso(t == E_LLEGADA ? "Llegada registrada" : (t == E_ENTREGA ? "Entrega registrada" : "Incidencia registrada"), 4000);
  dirty = dirtyTodo = true;
}

// ---------------------------------------------------------------- dibujo
#define COL_FONDO TFT_WHITE
#define COL_TXT TFT_BLACK
void txt(const String& s, int x, int y, int fuente, uint16_t fg, uint16_t bg = COL_FONDO, int dato = TL_DATUM) {
  lcd.setTextDatum(dato);
  lcd.setTextColor(fg, bg);
  lcd.drawString(s, x, y, fuente);
  lcd.setTextDatum(TL_DATUM);
}
void boton(int x, int y, int w, int h, const char* t, uint16_t col, uint16_t fg = TFT_WHITE, int fuente = 2) {
  lcd.fillRoundRect(x, y, w, h, 6, col);
  txt(t, x + w / 2, y + h / 2, fuente, fg, col, MC_DATUM);
}
String recortar(const char* s, int max) {
  String r(s);
  if ((int)r.length() > max) r = r.substring(0, max - 1) + ".";
  return r;
}
// Parte el texto por palabras en hasta 'lineas' lineas de 'ancho' caracteres.
void dibujarParrafo(const char* s, int x, int y, int ancho, int lineas, int alto) {
  String resto(s);
  for (int l = 0; l < lineas && resto.length(); l++) {
    String linea;
    if ((int)resto.length() <= ancho) { linea = resto; resto = ""; }
    else {
      int corte = resto.lastIndexOf(' ', ancho);
      if (corte <= 0) corte = ancho;
      linea = resto.substring(0, corte);
      resto = resto.substring(corte);
      resto.trim();
      if (l == lineas - 1 && resto.length()) linea = linea.substring(0, max(0, (int)linea.length() - 1)) + "...";
    }
    txt(linea, x, y + l * alto, 2, COL_TXT);
  }
}

const char* etiquetaRed() {
  switch (net) {
    case NET_OK: return "EN LINEA";
    case NET_SIN_WIFI: return "SIN WIFI";
    case NET_TOKEN: return "TOKEN RECHAZADO";
    case NET_LIMITE: return "LIMITE (429)";
    case NET_SERVIDOR: return "ERROR SERVIDOR";
    case NET_SIN_RESPUESTA: return "SIN RESPUESTA";
    default: return "CONECTANDO";
  }
}

void dibujarCabecera() {
  uint16_t col = net == NET_OK ? TFT_DARKGREEN : (net == NET_INICIANDO ? TFT_NAVY : TFT_MAROON);
  lcd.fillRect(0, 0, 240, 22, col);
  txt(CISTERNA_ID, 6, 3, 2, TFT_WHITE, col);
  txt(etiquetaRed(), 234, 3, 2, TFT_WHITE, col, TR_DATUM);
}

void dibujarSync() {
  lcd.fillRect(0, 24, 240, 18, COL_FONDO);
  char b[48];
  if (sincronizadoDesdeArranque) {
    snprintf(b, sizeof(b), "Sync %sZ hace %lus", ultimaSyncHora, (millis() - ultimaSyncMs) / 1000UL);
    txt(b, 6, 25, 2, net == NET_OK ? TFT_DARKGREY : TFT_RED);
  } else {
    txt(mision.valida ? "SIN SINCRONIZAR (datos guardados)" : "Sin sincronizar", 6, 25, 2, TFT_RED);
  }
}

void pantallaCompleta(const char* l1, const char* l2, const char* l3, uint16_t col) {
  lcd.fillRect(0, 44, 240, 276, COL_FONDO);
  txt(l1, 120, 110, 4, col, COL_FONDO, MC_DATUM);
  txt(l2, 120, 150, 2, COL_TXT, COL_FONDO, MC_DATUM);
  txt(l3, 120, 175, 2, TFT_DARKGREY, COL_FONDO, MC_DATUM);
}

void dibujarConfirmacion() {
  lcd.fillScreen(COL_FONDO);
  const Parada& p = mision.p[sel];
  bool ent = confirmTipo == E_ENTREGA;
  txt(ent ? "CONFIRMAR ENTREGA" : "CONFIRMAR INCIDENCIA", 120, 30, 4, ent ? TFT_DARKGREEN : TFT_RED, COL_FONDO, MC_DATUM);
  txt(String("Parada ") + p.orden + ": " + recortar(p.sector, 26), 120, 80, 2, COL_TXT, COL_FONDO, MC_DATUM);
  if (ent) txt(String(p.litros) + " litros", 120, 115, 4, COL_TXT, COL_FONDO, MC_DATUM);
  txt("Se enviara al servidor.", 120, 155, 2, TFT_DARKGREY, COL_FONDO, MC_DATUM);
  boton(10, 190, 220, 54, "CONFIRMAR", ent ? TFT_DARKGREEN : TFT_RED, TFT_WHITE, 4);
  boton(10, 254, 220, 54, "CANCELAR", TFT_DARKGREY, TFT_WHITE, 4);
}

void dibujarPrincipal() {
  const Parada& p = mision.p[sel];
  // mision y parada
  lcd.fillRect(0, 42, 240, 168, COL_FONDO);
  txt(String("Mision #") + mision.id + "  " + mision.estado, 6, 43, 2, TFT_NAVY);
  String sec = recortar(p.sector, 26);
  txt(sec, 6, 64, sec.length() > 15 ? 2 : 4, COL_TXT);
  txt(String(p.litros) + " L", 6, 92, 4, TFT_BLUE);
  const char* st = p.estado == P_PENDIENTE ? "PENDIENTE" : p.estado == P_LLEGADA ? "LLEGADA REGISTRADA"
                 : p.estado == P_ENTREGADA ? "ENTREGADA" : "INCIDENCIA";
  uint16_t cst = p.estado == P_ENTREGADA ? TFT_DARKGREEN : (p.estado == P_INCIDENCIA ? TFT_RED : TFT_ORANGE);
  txt(st, 234, 98, 2, cst, COL_FONDO, TR_DATUM);
  dibujarParrafo(p.instruccion[0] ? p.instruccion : "(sin instruccion)", 6, 122, 33, 3, 16);
  // contadores
  int hechas = contarEstado(P_ENTREGADA), inc = contarEstado(P_INCIDENCIA);
  txt(String("Completadas ") + hechas + "  Pend. " + abiertas() + "  Inc. " + inc, 6, 174, 2, COL_TXT);
  // aviso / cola
  lcd.fillRect(0, 192, 240, 18, COL_FONDO);
  if (avisoTxt[0] && millis() < avisoHasta) txt(avisoTxt, 6, 192, 2, TFT_RED);
  else if (nCola) txt(String("Por enviar: ") + nCola + (net == NET_OK ? "" : " (sin conexion)"), 6, 192, 2, TFT_ORANGE);
  else if (net == NET_TOKEN) txt("Token rechazado (HTTP " + String(netHttp) + ")", 6, 192, 2, TFT_RED);
  else if (net == NET_SERVIDOR || net == NET_LIMITE) txt("Servidor: HTTP " + String(netHttp), 6, 192, 2, TFT_RED);
  else if (mision.truncada) txt("Mision con mas paradas de las mostradas", 6, 192, 1, TFT_RED);
  else if (abiertas() == 0) txt("Todas registradas. Espere cierre.", 6, 192, 2, TFT_DARKGREEN);
}

void dibujarControles() {
  // navegacion
  lcd.fillRect(0, 212, 240, 36, COL_FONDO);
  boton(2, 214, 60, 32, "<", TFT_DARKGREY, TFT_WHITE, 4);
  boton(178, 214, 60, 32, ">", TFT_DARKGREY, TFT_WHITE, 4);
  txt(String("Parada ") + (sel + 1) + "/" + mision.n, 120, 230, 2, COL_TXT, COL_FONDO, MC_DATUM);
  // acciones
  const Parada& p = mision.p[sel];
  bool activa = !strcmp(mision.estado, "asignada") || !strcmp(mision.estado, "en_curso");
  bool puedeLleg = activa && p.estado == P_PENDIENTE;
  bool puedeOtro = activa && paradaAbierta(p);
  boton(2, 250, 117, 32, "LLEGUE", puedeLleg ? TFT_BLUE : TFT_LIGHTGREY);
  boton(121, 250, 117, 32, "INCIDENCIA", puedeOtro ? TFT_RED : TFT_LIGHTGREY);
  boton(2, 285, 236, 33, "ENTREGADO", puedeOtro ? TFT_DARKGREEN : TFT_LIGHTGREY, TFT_WHITE, 4);
}

void dibujar() {
  if (modo == M_CONFIRMAR) { if (dirtyTodo) dibujarConfirmacion(); dirty = dirtyTodo = false; return; }
  if (dirtyTodo) lcd.fillScreen(COL_FONDO);
  dibujarCabecera();
  dibujarSync();
  // pantallas completas: sin mision usable, o token rechazado (no se puede operar; la cola se conserva)
  if (!mision.valida || net == NET_TOKEN) {
    if (net == NET_TOKEN) pantallaCompleta("TOKEN RECHAZADO", (String("HTTP ") + netHttp + ": terminal no autorizada").c_str(), "Avise al administrador", TFT_RED);
    else if (net == NET_SIN_WIFI) pantallaCompleta("SIN WIFI", "Buscando red...", "Reconexion automatica", TFT_RED);
    else if (net == NET_SERVIDOR || net == NET_LIMITE) pantallaCompleta("ERROR DE SERVIDOR", (String("HTTP ") + netHttp).c_str(), "Reintentando...", TFT_RED);
    else if (net == NET_SIN_RESPUESTA) pantallaCompleta("SERVIDOR SIN RESPUESTA", "Verifique API_BASE_URL y red", "Reintentando...", TFT_RED);
    else if (net == NET_OK) pantallaCompleta("SIN MISION ASIGNADA", "Espere una asignacion", "Se consulta cada pocos segundos", TFT_NAVY);
    else pantallaCompleta("CONECTANDO...", "", "", TFT_NAVY);
    dirty = dirtyTodo = false;
    return;
  }
  if (!strcmp(mision.estado, "completada") || !strcmp(mision.estado, "cancelada") || mision.n == 0) {
    bool comp = !strcmp(mision.estado, "completada");
    pantallaCompleta(comp ? "MISION COMPLETADA" : (mision.n ? "MISION CANCELADA" : "MISION SIN PARADAS"),
                     (String("#") + mision.id + "  entregas: " + contarEstado(P_ENTREGADA) + "/" + mision.n).c_str(),
                     nCola ? (String("Por enviar: ") + nCola).c_str() : "Espere nueva asignacion", comp ? TFT_DARKGREEN : TFT_RED);
    dirty = dirtyTodo = false;
    return;
  }
  dibujarPrincipal();
  dibujarControles();
  dirty = dirtyTodo = false;
}

// ---------------------------------------------------------------- tactil
bool dentro(int x, int y, int bx, int by, int bw, int bh) { return x >= bx && x < bx + bw && y >= by && y < by + bh; }

void manejarToque(int x, int y) {
  if (modo == M_CONFIRMAR) {
    if (dentro(x, y, 10, 190, 220, 54)) { registrar(confirmTipo); modo = M_NORMAL; dirty = dirtyTodo = true; }
    else if (dentro(x, y, 10, 254, 220, 54)) { modo = M_NORMAL; dirty = dirtyTodo = true; }
    return;
  }
  if (!mision.valida || mision.n == 0 || net == NET_TOKEN) return;
  if (!strcmp(mision.estado, "completada") || !strcmp(mision.estado, "cancelada")) return;
  if (dentro(x, y, 0, 210, 64, 40)) { sel = (sel + mision.n - 1) % mision.n; dirty = true; }
  else if (dentro(x, y, 176, 210, 64, 40)) { sel = (sel + 1) % mision.n; dirty = true; }
  else if (dentro(x, y, 2, 250, 117, 32)) registrar(E_LLEGADA);
  else if (dentro(x, y, 121, 250, 117, 32) || dentro(x, y, 2, 285, 236, 33)) {
    TipoEvento t = y >= 285 ? E_ENTREGA : E_INCIDENCIA;
    const Parada& p = mision.p[sel];
    if (!paradaAbierta(p)) { aviso("Parada ya cerrada"); return; }
    confirmTipo = t; confirmDesde = millis(); modo = M_CONFIRMAR; dirty = dirtyTodo = true;
  }
}

// ---------------------------------------------------------------- setup / loop
void setup() {
  Serial.begin(115200);
  lcd.begin();
  lcd.setRotation(0);
  lcd.fillScreen(COL_FONDO);
  ts.begin();
  ts.setRotation(ROTATION_NORMAL);

  prefs.begin("hidro360", false);
  bootCnt = prefs.getUInt("boot", 0) + 1;
  prefs.putUInt("boot", bootCnt);
  cargarCola();
  cargarMision();      // ultima mision conocida: se muestra marcada "sin sincronizar" hasta el primer sondeo
  seleccionarPrimeraAbierta();

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  dibujar();
}

void loop() {
  static bool tocando = false;
  static unsigned long tToque = 0;
  unsigned long ahora = millis();

  // WiFi: reconexion automatica + respaldo manual cada 10 s
  if (WiFi.status() != WL_CONNECTED) {
    if (net != NET_SIN_WIFI && net != NET_INICIANDO) { net = NET_SIN_WIFI; dirty = dirtyTodo = true; }
    if (net == NET_INICIANDO && ahora > 15000) { net = NET_SIN_WIFI; dirty = dirtyTodo = true; }
    if (ahora > proxWifi) { proxWifi = ahora + 10000; WiFi.disconnect(); WiFi.begin(WIFI_SSID, WIFI_PASS); }
  }

  // Tactil (se actua en el flanco de pulsacion)
  ts.read();
  if (ts.isTouched) {
    if (!tocando && ahora - tToque > 250) {
      tocando = true; tToque = ahora;
      manejarToque(ts.points[0].x, ts.points[0].y);
    }
  } else {
    tocando = false;
  }
  if (modo == M_CONFIRMAR && ahora - confirmDesde > CONFIRM_TIMEOUT_MS) { modo = M_NORMAL; dirty = dirtyTodo = true; }

  // Red: solo si no se esta confirmando (una peticion bloquea hasta HTTP_TIMEOUT_MS)
  if (modo == M_NORMAL && !tocando && WiFi.status() == WL_CONNECTED) {
    enviarCola();
    if (ahora >= proxPoll) { proxPoll = millis() + MISION_POLL_MS; sondearMision(); }
    if (ahora >= proxLatido) { proxLatido = millis() + LATIDO_MS; enviarLatido(); }
  }

  // Refresco periodico del "hace N s" y caducidad de avisos
  static unsigned long tRefresco = 0;
  if (ahora - tRefresco > 5000) { tRefresco = ahora; dirty = true; }
  if (avisoTxt[0] && ahora > avisoHasta) { avisoTxt[0] = 0; dirty = true; }
  if (dirty) dibujar();
  delay(15);
}
