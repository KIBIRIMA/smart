#!/bin/sh
set -e
echo "⏳ Attente de PostgreSQL..."
until python -c "import asyncio,asyncpg,os; asyncio.run(asyncpg.connect(host=os.getenv('POSTGRES_HOST','db'),port=int(os.getenv('POSTGRES_PORT','5432')),user=os.getenv('POSTGRES_USER'),password=os.getenv('POSTGRES_PASSWORD'),database=os.getenv('POSTGRES_DB')))" 2>/dev/null; do
  sleep 1
done
echo "✅ PostgreSQL prêt"
echo "🌱 Initialisation du schéma + seed..."
python -m app.db.seed
echo "🚀 Démarrage de l'API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WORKERS:-2}
