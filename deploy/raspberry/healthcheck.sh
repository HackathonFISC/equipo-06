#!/usr/bin/env bash
# Comprobación de salud: API (/salud) y panel Flet. Sale con código != 0 si algo falla. SIN PROBAR en una Raspberry.
API="${API_URL:-http://127.0.0.1:8000}"
UI="${UI_URL:-http://127.0.0.1:8501}"
fallo=0
if curl -fsS --max-time 5 "$API/api/v1/salud" >/dev/null; then echo "API ok"; else echo "API NO responde"; fallo=1; fi
if curl -fsS --max-time 5 "$UI/" >/dev/null; then echo "Panel ok"; else echo "Panel NO responde"; fallo=1; fi
exit $fallo
