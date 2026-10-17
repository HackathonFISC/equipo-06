# Instalación, configuración y primera demo (Windows)

Todo en una terminal, desde la raíz del repositorio. **La demo básica no necesita internet, claves ni hardware** (modo local).

## 1. Requisitos
Python 3.10+ (probado con 3.14.7). Comprobar: `python --version`.

## 2. Instalar
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -c "import flet, pydantic, fastapi, google.genai; print('imports ok')"
```
**Primera ejecución de escritorio: necesita internet UNA vez.** `flet-desktop` es un paquete pequeño; al primer arranque Flet muestra «Preparing Flet … one-time operation» y descarga su cliente a `%USERPROFILE%\.flet\client\` (se comprobó que esa carpeta se crea). Después funciona sin internet. Para un equipo sin internet, copie esa carpeta `.flet\client` desde otro equipo con la misma versión (no probado).

## 3. Probar el entorno
```bash
pytest -q                      # usa bases y trazas temporales (no toca agua_clara.db)
```

## 4. Iniciar
```bash
python app.py                  # ventana de escritorio (funciona sin internet)
python app.py --web            # navegador en http://127.0.0.1:8501 (el navegador carga Flet desde internet: ver docs/DECISIONES.md D-04; la 1.ª carga tarda 15-20 s)
uvicorn api.main:app --port 8000   # API opcional, en otra terminal → http://localhost:8000/docs
```
Comprobar la API: abrir `http://localhost:8000/api/v1/salud` → `{"ok": true, ...}`.

## 5. Primera demostración (≈5 min)
1. **Cree el primer administrador** (no hay cuentas por defecto): `python -m scripts.crear_admin` (pide usuario y contraseña de 10+ caracteres con mayúsculas, minúsculas y número).
2. Abra la app: verá el **portal público** (Inicio · Reportar · Consultar mi reporte · Avisos). **Reportar** → escriba «En Vista Alegre no tenemos agua desde ayer» → se guarda con su texto original y muestra un **código de seguimiento** `HID-…`; **Consultar mi reporte** con ese código muestra solo el estado público.
3. **Acceso administración** → inicie sesión. Con la base vacía: **Diagnóstico y desarrollo → Cargar datos de ejemplo** y confirme (ficticios; 19 reportes, 15 sectores, 6 cisternas).
4. **Revisión y validación** → corrija/complete (p. ej. personas = 120) → **Confirmar**. Confirme otros reportes (el #19 de la demo no trae sector: elíjalo).
5. **Ubicación y duplicados** → decida «sí/no» en los candidatos (nada se fusiona solo).
6. **Priorización** → ranking con desglose; **Explicar con IA** (modo local: texto de reglas).
7. **Planificación y aprobación** → **Generar propuesta**, edite una asignación (pide motivo), **Aprobar** (diálogo de confirmación) o **Rechazar** (exige motivo).
8. **Comunicación** (borradores, no se envían) · **Auditoría** (cadena íntegra) · **Métricas operativas**; en *Diagnóstico y desarrollo*: **Trazas**, **Evaluación e impacto**, **Verificar Gemini**.

## 6. Configuración opcional
Copie `.env.example` a `.env`. **No hace falta tocar nada para la primera prueba.**
| Variable | Para qué | Obligatoria |
|---|---|---|
| `AI_PROVIDER` | `auto` (Gemini solo con clave) · `local` · `gemini` | no |
| `GEMINI_API_KEY` | activar Gemini | solo para Gemini |
| `GEMINI_MODEL` | cambiar de modelo sin editar código | no |
| `AI_TIMEOUT_SECONDS`, `AI_MAX_REINTENTOS` | límites de tiempo/reintentos | no |
| `AGUA_CLARA_API_TOKEN`, `AGUA_CLARA_DEVICE_TOKEN` | usar la API desde la red local | solo para dispositivos |
| `AGUA_CLARA_DB`, `AGUA_CLARA_TRACE` | rutas de datos | no |

### Verificar Gemini
```bash
python -m scripts.verificar_gemini --sin-llamada   # solo configuración (no usa red ni cuota)
python -m scripts.verificar_gemini                  # lista modelos y hace una llamada mínima
```
Sin clave el comando responde «Gemini no está configurado: el sistema usa el modo local» (código 2) y la app sigue funcionando. Guía completa: `docs/IA_GEMINI.md`.

### Forzar el modo local
`AI_PROVIDER=local` (en `.env` o `set AI_PROVIDER=local` antes de iniciar).

## 7. Detener y reiniciar la demo
Cierre la ventana (o `Ctrl+C` en la terminal). Si la ventana no aparece en la primera ejecución, revise la conexión (descarga del cliente). **Reiniciar datos**: botón «Cargar datos de ejemplo» (borra reportes, planes y auditoría de la base local; copie antes `agua_clara.db` si necesita conservarla).

## 8. Errores frecuentes
| Síntoma | Causa y solución |
|---|---|
| `ModuleNotFoundError: flet` | Falta activar el venv o `pip install -r requirements.txt`. |
| `--web`: página en blanco 15-20 s | Primera carga de CanvasKit desde internet; espere. Sin internet use `python app.py`. |
| `--web`: página en blanco para siempre | Sin acceso a internet en el navegador. Use la app de escritorio. |
| Puerto 8501/8000 ocupado | Use `--port 8502` / `--port 8001`. |
| La API devuelve 403 desde otra máquina | Sin tokens solo acepta localhost: defina `AGUA_CLARA_API_TOKEN`/`AGUA_CLARA_DEVICE_TOKEN`. |
| «Gemini no estuvo disponible… modo local» en un reporte | Falta clave, cuota agotada (429), modelo inexistente o sin red: ver Trazas (estado `fallback`) y `scripts.verificar_gemini`. |
| «Elija un sector válido» al confirmar | El sector debe ser del catálogo; elíjalo en el desplegable. |
| «Transición no permitida» | El reporte/plan ya está en un estado final (rechazado, duplicado, aprobado…). |
