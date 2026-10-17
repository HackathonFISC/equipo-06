#!/usr/bin/env bash
# Copia de seguridad consistente de SQLite + trazas. Programar con cron, p. ej.:  0 * * * * /opt/hidro360/deploy/raspberry/backup.sh
# SIN PROBAR en una Raspberry.
set -euo pipefail
DB="${AGUA_CLARA_DB:-/var/lib/hidro360/hidro360.db}"
TRACE="${AGUA_CLARA_TRACE:-/var/lib/hidro360/trazas.jsonl}"
DEST="${BACKUP_DIR:-/var/lib/hidro360/backups}"
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p "$DEST"
python3 - "$DB" "$DEST/hidro360-$STAMP.db" <<'PY'
import sqlite3, sys
src = sqlite3.connect(sys.argv[1]); dst = sqlite3.connect(sys.argv[2])
src.backup(dst); dst.close(); src.close()
PY
[ -f "$TRACE" ] && cp "$TRACE" "$DEST/trazas-$STAMP.jsonl"
find "$DEST" -type f -mtime +14 -delete
echo "Copia creada en $DEST ($STAMP)"
