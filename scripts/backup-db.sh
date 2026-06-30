#!/usr/bin/env bash
# Sauvegarde PostgreSQL horodatée
set -euo pipefail
mkdir -p backups
TS=$(date +%Y%m%d-%H%M%S)
docker compose exec -T db pg_dump -U "${POSTGRES_USER:-smarttransport}" "${POSTGRES_DB:-smarttransport}" > "backups/sta-$TS.sql"
echo "✅ Sauvegarde : backups/sta-$TS.sql"
