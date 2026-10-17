"""
Simulador de la terminal de cisterna (ESP32-S3): hace las MISMAS llamadas HTTP que el firmware
(`firmware/esp32s3_monitor/esp32s3_monitor.ino`) contra la API real, para probar el protocolo SIN la placa.

NO sustituye la prueba en la placa (WiFi, pantalla, tactil, NVS y tiempos reales siguen sin probar).

Dos usos:
  # 1) Autoprueba completa: crea una base temporal, registra una terminal, asigna una mision, arranca uvicorn en un
  #    puerto libre, ejecuta el escenario y limpia. No toca la base real.
  python -m scripts.simular_terminal --autoprueba

  # 2) Contra una API ya en marcha, con el token de un vehiculo (se ve una sola vez al registrarlo)
  python -m scripts.simular_terminal --base http://127.0.0.1:8000/api/v1 --token <TOKEN> [--bucle]

Escenario de la autoprueba (cada paso imprime OK/FALLO):
  token invalido -> 401; sondeo de mision; cola con uid unico; envio a un servidor caido (reintento con retroceso
  exponencial, la cola se conserva); envio real (aplicado); reenvio del mismo lote (duplicado = exito);
  evento invalido (rechazado, sale de la cola); latido; sondeo final (mision completada).
"""

import argparse
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

RAIZ = Path(__file__).resolve().parent.parent
BACKOFF_MIN_S, BACKOFF_MAX_S = 2.0, 60.0          # igual que BACKOFF_MIN_MS / BACKOFF_MAX_MS del firmware
FIRMWARE = "2.0.0"


class Terminal:
    """Misma logica que el firmware: cola persistente (aqui en memoria o en un JSON), uid unico, backoff."""

    def __init__(self, base: str, token: str, timeout: float = 5.0, escala_tiempo: float = 1.0):
        self.base, self.token, self.timeout = base.rstrip("/"), token, timeout
        self.cola: List[Dict[str, Any]] = []
        self.boot = 1
        self.seq = 0
        self.backoff_n = 0
        self.escala = escala_tiempo            # <1 acelera las esperas en pruebas
        self.t0 = time.time()

    # --- HTTP (equivalente a llamar() del firmware: timeout, cabecera X-Device-Token, JSON) ---
    def llamar(self, post: bool, ruta: str, cuerpo: Optional[dict] = None) -> Tuple[int, Any]:
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(self.base + ruta, data=datos, method="POST" if post else "GET")
        req.add_header("X-Device-Token", self.token)
        if post:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return r.status, json.loads(r.read().decode() or "null")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "null")
            except Exception:
                return e.code, None
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
            return -1, None                    # sin respuesta (equivale a codigo <= 0 en el firmware)

    # --- protocolo ---
    def uid(self) -> str:
        self.seq += 1
        return f"t{self.boot:x}-{self.seq:x}-{random.getrandbits(32):08x}"

    def sondear_mision(self) -> Tuple[int, Optional[dict]]:
        return self.llamar(False, "/dispositivo/mision")

    def encolar(self, tipo: str, mision_id: int, orden: int, litros: Optional[int] = None, nota: str = "") -> str:
        ev = {"uid": self.uid(), "tipo": tipo, "mision_id": mision_id, "parada_orden": orden,
              "nota": nota, "fecha_dispositivo": None}
        if tipo == "entrega":
            ev["litros_entregados"] = litros
        self.cola.append(ev)
        self.backoff_n = 0
        return ev["uid"]

    def espera_backoff(self) -> float:
        espera = min(BACKOFF_MIN_S * (2 ** min(self.backoff_n, 5)), BACKOFF_MAX_S)
        self.backoff_n = min(self.backoff_n + 1, 10)
        return espera

    def enviar_cola(self, lote: int = 10) -> Tuple[int, List[dict]]:
        """Un intento de envio. Quita de la cola SOLO lo que el servidor resuelve (aplicado|duplicado|rechazado)."""
        if not self.cola:
            return 0, []
        envio = self.cola[:lote]
        codigo, resp = self.llamar(True, "/dispositivo/eventos", {"eventos": envio})
        if codigo != 200 or not isinstance(resp, dict):
            return codigo, []
        resueltos = {r["uid"]: r for r in resp.get("resultados", [])
                     if r.get("resultado") in ("aplicado", "duplicado", "rechazado")}
        self.cola = [e for e in self.cola if e["uid"] not in resueltos]
        return codigo, list(resueltos.values())

    def latido(self, rssi: int = -60) -> Tuple[int, Any]:
        return self.llamar(True, "/dispositivo/latido", {"firmware": FIRMWARE, "wifi_rssi": rssi,
                                                          "pendientes": len(self.cola),
                                                          "uptime_s": int(time.time() - self.t0)})


# ----------------------------------------------------------------------------- utilidades de la autoprueba
def puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def preparar() -> None:
    """Subproceso: con AGUA_CLARA_DB apuntando a una base temporal, carga la demo, registra una terminal y asigna
    una mision de 2 paradas. Imprime una linea JSON con cisterna, token y mision."""
    sys.path.insert(0, str(RAIZ))
    from services import auth, workflow
    actor = auth.Actor("script-local", auth.Rol.ADMIN, "servicio")
    with auth.como(actor):
        workflow.cargar_datos_demo("script-local")
        cis = next(c for c in workflow.listar_cisternas() if c.litros_disponibles >= 3000)
        sectores = [s.nombre for s in workflow.listar_sectores()][:2]
        _, token = workflow.registrar_dispositivo(cis.id, "Simulador", "script-local")
        m = workflow.crear_mision(cis.id, [
            {"orden": 1, "sector": sectores[0], "litros": 1000, "instruccion": "Cerrar valvula y entregar en el punto A."},
            {"orden": 2, "sector": sectores[1], "litros": 1500, "instruccion": "Coordinar con el delegado del sector."},
        ], "script-local", motivo="Misión de prueba del simulador")
    print(json.dumps({"cisterna": cis.id, "token": token, "mision": m.id}))


def esperar_api(base: str, intentos: int = 60) -> bool:
    for _ in range(intentos):
        try:
            urllib.request.urlopen(base.replace("/api/v1", "") + "/api/v1/salud", timeout=1).read()
            return True
        except Exception:
            time.sleep(0.5)
    return False


class Informe:
    def __init__(self):
        self.fallos = 0

    def chk(self, nombre: str, ok: bool, detalle: Any = ""):
        print(f"[{'OK' if ok else 'FALLO'}] {nombre}" + (f"  -> {detalle}" if detalle != "" else ""))
        if not ok:
            self.fallos += 1


def escenario(base: str, token: str, puerto_caido: int) -> int:
    inf = Informe()
    # 1) token invalido -> 401 (el firmware muestra "TOKEN RECHAZADO")
    malo = Terminal(base, "token-que-no-existe")
    c, _ = malo.sondear_mision()
    inf.chk("token invalido responde 401", c == 401, c)

    t = Terminal(base, token, escala_tiempo=0.0)
    # 2) sondeo
    c, d = t.sondear_mision()
    inf.chk("GET /dispositivo/mision 200", c == 200, c)
    m = (d or {}).get("mision")
    inf.chk("hay mision con paradas", bool(m and m.get("paradas")), None if not m else f"mision {m['id']}, {len(m['paradas'])} paradas")
    if not m:
        return inf.fallos + 1
    inf.chk("servidor_hora presente", bool((d or {}).get("servidor_hora")), (d or {}).get("servidor_hora"))
    mid = m["id"]
    p1, p2 = m["paradas"][0], m["paradas"][1]

    # 3) cola con uid unico
    u1 = t.encolar("llegada", mid, p1["orden"])
    u2 = t.encolar("entrega", mid, p1["orden"], p1["litros"])
    inf.chk("uids unicos y de 8-64 caracteres", len({e["uid"] for e in t.cola}) == 2 and all(8 <= len(e["uid"]) <= 64 for e in t.cola),
            [e["uid"] for e in t.cola])

    # 4) servidor caido: no se pierde nada, backoff exponencial 2,4,8,16,32,60
    caido = Terminal(f"http://127.0.0.1:{puerto_caido}/api/v1", token, timeout=1.0)
    caido.cola = list(t.cola)
    esperas = []
    for _ in range(4):
        c, r = caido.enviar_cola()
        esperas.append(caido.espera_backoff())
        if c != -1 or r:
            break
    inf.chk("con la API caida la cola se conserva (2 eventos)", len(caido.cola) == 2, f"esperas de reintento {esperas}")
    inf.chk("backoff exponencial 2,4,8,16", esperas == [2.0, 4.0, 8.0, 16.0], esperas)

    # 5) envio real
    c, res = t.enviar_cola()
    estados = sorted(r["resultado"] for r in res)
    inf.chk("lote 1 aplicado y cola vacia", c == 200 and estados == ["aplicado", "aplicado"] and not t.cola, (c, estados))

    # 6) respuesta perdida: se reenvian los mismos uid -> duplicado (exito, deja de reintentarse)
    t.cola = [{"uid": u1, "tipo": "llegada", "mision_id": mid, "parada_orden": p1["orden"], "nota": "", "fecha_dispositivo": None},
              {"uid": u2, "tipo": "entrega", "mision_id": mid, "parada_orden": p1["orden"], "litros_entregados": p1["litros"],
               "nota": "", "fecha_dispositivo": None}]
    c, res = t.enviar_cola()
    inf.chk("reenvio del mismo lote -> duplicado y cola vacia", c == 200 and all(r["resultado"] == "duplicado" for r in res) and not t.cola,
            [r["resultado"] for r in res])

    # 7) evento invalido -> rechazado (sale de la cola; la pantalla muestra el motivo)
    t.encolar("entrega", mid + 999, 1, 10)
    c, res = t.enviar_cola()
    inf.chk("evento de mision ajena -> rechazado y sale de la cola", c == 200 and res and res[0]["resultado"] == "rechazado" and not t.cola,
            res[0] if res else c)
    t.encolar("entrega", mid, p1["orden"], p1["litros"])        # parada ya entregada: transicion no permitida
    c, res = t.enviar_cola()
    inf.chk("entrega repetida con uid nuevo -> rechazado", c == 200 and res and res[0]["resultado"] == "rechazado", res[0] if res else c)

    # 8) latido
    c, r = t.latido()
    inf.chk("POST /dispositivo/latido 200", c == 200, (c, r))

    # 9) mision de la segunda parada: incidencia y cierre
    t.encolar("llegada", mid, p2["orden"])
    t.encolar("incidencia", mid, p2["orden"], nota="incidencia reportada desde la terminal")
    c, res = t.enviar_cola()
    inf.chk("llegada+incidencia de la parada 2 aplicadas", c == 200 and [r["resultado"] for r in res] == ["aplicado", "aplicado"],
            [r["resultado"] for r in res])
    c, d = t.sondear_mision()
    inf.chk("tras cerrar todas las paradas el servidor ya no ofrece mision activa (completada)", c == 200 and d.get("mision") is None,
            None if d is None else d.get("mision"))
    print(f"\nResumen: {'TODO OK' if inf.fallos == 0 else str(inf.fallos) + ' fallo(s)'}")
    return inf.fallos


def autoprueba() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="hidro360_sim_"))
    env = {**os.environ, "AGUA_CLARA_DB": str(tmp / "sim.db"), "AGUA_CLARA_TRACE": str(tmp / "trazas.jsonl"),
           "AI_PROVIDER": "local", "PYTHONIOENCODING": "utf-8"}
    for k in ("AGUA_CLARA_API_TOKEN", "AGUA_CLARA_DEVICE_TOKEN", "GEMINI_API_KEY"):
        env.pop(k, None)
    p = subprocess.run([sys.executable, "-m", "scripts.simular_terminal", "--preparar"], cwd=RAIZ, env=env,
                       capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        print("No se pudo preparar la base temporal:\n", p.stdout, p.stderr)
        return 2
    datos = json.loads(p.stdout.strip().splitlines()[-1])
    puerto = puerto_libre()
    base = f"http://127.0.0.1:{puerto}/api/v1"
    srv = subprocess.Popen([sys.executable, "-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", str(puerto),
                            "--log-level", "warning"], cwd=RAIZ, env=env)
    try:
        if not esperar_api(base):
            print("La API no arranco a tiempo.")
            return 2
        print(f"API temporal en {base} (cisterna {datos['cisterna']}, mision {datos['mision']}, base {tmp})\n")
        return escenario(base, datos["token"], puerto_libre())
    finally:
        srv.terminate()
        try:
            srv.wait(10)
        except Exception:
            srv.kill()


def bucle(base: str, token: str, poll: float) -> None:
    """Uso manual: sondea la mision cada `poll` s y envia un latido por minuto, como la terminal real."""
    t = Terminal(base, token)
    ult_latido = 0.0
    while True:
        c, d = t.sondear_mision()
        m = (d or {}).get("mision")
        print(time.strftime("%H:%M:%S"), "HTTP", c, "mision:", None if not m else (m["id"], m["estado"], [p["estado"] for p in m["paradas"]]))
        if time.time() - ult_latido > 60:
            print("  latido:", t.latido())
            ult_latido = time.time()
        time.sleep(poll)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--autoprueba", action="store_true", help="base temporal + API temporal + escenario completo")
    ap.add_argument("--preparar", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
    ap.add_argument("--token", default=os.environ.get("HIDRO360_DEVICE_TOKEN", ""))
    ap.add_argument("--bucle", action="store_true", help="sondeo continuo (uso manual)")
    ap.add_argument("--poll", type=float, default=10.0)
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # consola de Windows (cp1252)
    except Exception:
        pass
    if a.preparar:
        preparar()
        return 0
    if a.autoprueba:
        return 1 if autoprueba() else 0
    if not a.token:
        ap.error("indique --token (o la variable HIDRO360_DEVICE_TOKEN) o use --autoprueba")
    if a.bucle:
        bucle(a.base, a.token, a.poll)
        return 0
    return 1 if escenario(a.base, a.token, puerto_libre()) else 0


if __name__ == "__main__":
    sys.exit(main())
