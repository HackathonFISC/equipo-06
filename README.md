# HIDRO360 — TEAM VIFY AI

Coordinación explicable de reportes de falta de agua y propuesta de distribución de cisternas en Panamá Oeste, con **supervisión humana obligatoria**. La IA (Gemini, opcional) ayuda a leer mensajes; reglas deterministas calculan prioridad, plan y auditoría; **una persona decide**.

> **Datos ficticios.** Sectores, cisternas y reportes de la demo son inventados. El experimento de impacto es **sintético**: no es evidencia de impacto real.

> **Roles:** portal público sin cuenta + administración con login; ver `docs/SEGURIDAD.md`.

## Estado
| Funciona (probado por software) | Pendiente / no verificado |
|---|---|
| Bandeja → ingesta → revisión humana → sector/duplicados → prioridad → plan → aprobación → auditoría, en la **interfaz Flet** | **Gemini real**: integrado y probado con un cliente simulado; no se ha probado con una clave real |
| Demo completa sin internet ni claves (modo local) | **Firmware ESP32-S3** sin compilar ni probar en la placa; **Raspberry Pi** sin probar (pines libres de la placa: «no verificado», ver `docs/HARDWARE.md`) |
| Trazas y auditoría con cadena de hashes; máquina de estados y transacciones en el backend; API con tokens | Autenticación y roles: ver `docs/SEGURIDAD.md` (el estado vigente se documenta allí) |
| Planificador por flujo máximo; Gini; experimento línea base vs HIDRO360 (sintético) | Casos **oficiales**: la guía no los enumera; los del runner los redactó el equipo |
| Pruebas automáticas (`pytest -q`) y casos del runner (`python -m evaluation.run_cases`); cifras vigentes: ejecútelos | Escritorio en otros SO; video de demostración (solo hay guion) |

## Instalar y ejecutar (Windows)
Requiere Python 3.10+ (probado con 3.14).
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py                  # ventana de escritorio
python app.py --web            # o en el navegador: http://127.0.0.1:8501
pytest -q                      # pruebas (el resultado vigente lo da este comando)
```
**Internet:** el modo local de reportes/prioridad/plan no necesita internet ni claves. Aun así, la **primera** ejecución de escritorio descarga el cliente de Flet (una vez, a `%USERPROFILE%\.flet\client`), y el modo `--web` carga Flet desde internet en el navegador. Detalle en `docs/DECISIONES.md` D-04 y `docs/INSTALACION.md`.

## Primera demostración
1. `python -m scripts.crear_admin` (primer administrador; no hay cuentas por defecto).
2. Portal público: **Reportar** «En Vista Alegre no tenemos agua desde ayer» → recibe un código `HID-…`; **Consultar mi reporte** muestra el estado.
3. **Acceso administración** → login → *Diagnóstico y desarrollo → Cargar datos de ejemplo* (ficticios, pide confirmación) → **Revisión** → corrija y **confirme**. **Duplicados** → decida («sí/no»; nada se fusiona solo). **Priorización** → desglose y razones.
4. **Planificación** → generar propuesta, editar (pide motivo), **aprobar/rechazar** (con confirmación). **Comunicación** (borradores), **Trazas**, **Auditoría**, **Evaluación e impacto**.
Guía completa y errores frecuentes: `docs/INSTALACION.md`.

## Configurar Gemini (opcional)
```bash
copy .env.example .env         # luego escriba GEMINI_API_KEY=... en .env  (.env está en .gitignore)
python -m scripts.verificar_gemini --sin-llamada   # comprueba la configuración sin usar red
python -m scripts.verificar_gemini                  # lista modelos y hace una llamada mínima
```
`AI_PROVIDER=auto` (defecto) usa Gemini solo si hay clave; `local` fuerza reglas. Si Gemini falla se usa el modo local y se declara. Cambie de modelo con `GEMINI_MODEL`. Detalle, límites y privacidad: `docs/IA_GEMINI.md`.

## Pruebas y evaluación
`pytest -q` · `python -m evaluation.run_cases` (informe en `docs/RESULTADOS_EVALUACION.md`) · `python -m evaluation.run_impacto` (`docs/EXPERIMENTO_IMPACTO.md`). Qué está y qué no está probado: `docs/PRUEBAS.md`.

## API y dispositivos
`uvicorn api.main:app --port 8000` → `/docs`. Sin tokens solo acepta localhost. Contrato: `docs/API.md`. ESP32-S3: `firmware/esp32s3_monitor/` (sin compilar); Raspberry: `deploy/raspberry/` (sin probar); ver `docs/HARDWARE.md`.

## Mapa del repositorio
`interface/flet_app/` UI · `services/` lógica de negocio · `api/` FastAPI · `models/` contratos · `data/` SQLite y datos ficticios · `evaluation/` casos e impacto · `scripts/` utilidades · `firmware/`, `deploy/` hardware · `assets/` logo · `LOGO/` logo original y `PROTOTIPO/` referencia visual · `docs/` documentación · **`AGENTS.md`** guía para asistentes y personas · `.claude/skills/` skills de Claude Code.

## Documentación
`AGENTS.md` · `docs/ARQUITECTURA.md` · `INSTALACION.md` · `API.md` · `BASE_DE_DATOS.md` · `SEGURIDAD.md` · `IA_GEMINI.md` · `PRUEBAS.md` · `DECISIONES.md` · `DISENO_UI.md` · `HARDWARE.md` · `PLANIFICADOR.md` · `INVENTARIO_ARCHIVOS.md` · `AUDITORIA_TECNICA.md` (estado inicial) · `GUION_VIDEO.md` · `CHANGELOG.md`.

## Limitaciones conocidas
Autenticación de administración en integración (ver `docs/SEGURIDAD.md`); parámetros de prioridad y litros por persona son de demostración; extracción por regex; el plan no modela rutas ni ETA; sectores sin reportes siguen invisibles para la asignación (solo se marcan); el logo es un JPEG sin transparencia.

## Entrega
La guía no define procedimiento de entrega ni etiqueta de Git. **No se creó ningún tag**; `final-24h` queda pendiente de confirmar.
