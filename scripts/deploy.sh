#!/usr/bin/env bash
# Déploiement Smart Transport AI sur VPS LWS
set -euo pipefail

echo "🚀 Déploiement Smart Transport AI"

if [ ! -f .env ]; then
  echo "⚠️  Fichier .env manquant. Copie depuis .env.example..."
  cp .env.example .env
  echo "❗ Éditez .env (SECRET_KEY, mots de passe) puis relancez."
  exit 1
fi

echo "📦 Build des images..."
docker compose build

echo "🗄️  Démarrage base + cache..."
docker compose up -d db redis

echo "⏳ Attente santé PostgreSQL..."
sleep 8

echo "🔧 Démarrage backend (schéma + seed automatiques)..."
docker compose up -d backend

echo "🎨 Démarrage frontend + nginx..."
docker compose up -d frontend nginx

echo ""
echo "✅ Déploiement terminé."
docker compose ps
echo ""
echo "   Frontend : https://votre-domaine"
echo "   API docs : https://votre-domaine/docs"
echo "   Santé    : https://votre-domaine/health"
