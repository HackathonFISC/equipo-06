#!/usr/bin/env bash
# Instalación en Raspberry Pi OS Lite. SIN PROBAR en una Raspberry (escrito, no ejecutado).
# Uso: sudo bash deploy/raspberry/install.sh   (desde la raíz del repositorio clonado en /opt/hidro360)
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/hidro360}"
DATA_DIR=/var/lib/hidro360
ENV_DIR=/etc/hidro360
USER_SVC=hidro360

[ "$(id -u)" -eq 0 ] || { echo "Ejecute con sudo"; exit 1; }
[ -f "$APP_DIR/app.py" ] || { echo "No se encontró $APP_DIR/app.py (clone el repositorio en $APP_DIR)"; exit 1; }

id "$USER_SVC" &>/dev/null || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$USER_SVC"
mkdir -p "$DATA_DIR/backups" "$ENV_DIR"
chown -R "$USER_SVC":"$USER_SVC" "$DATA_DIR"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

if [ ! -f "$ENV_DIR/hidro360.env" ]; then
  install -m 640 -o root -g "$USER_SVC" "$APP_DIR/deploy/raspberry/.env.example" "$ENV_DIR/hidro360.env"
  echo "Se creó $ENV_DIR/hidro360.env: EDÍTELO y fije los tokens antes de iniciar los servicios."
fi

install -m 644 "$APP_DIR/deploy/raspberry/hidro360-api.service" /etc/systemd/system/
install -m 644 "$APP_DIR/deploy/raspberry/hidro360-ui.service" /etc/systemd/system/
systemctl daemon-reload
echo "Listo. Siguiente: systemctl enable --now hidro360-api hidro360-ui"
