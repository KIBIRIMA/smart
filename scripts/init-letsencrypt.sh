#!/usr/bin/env bash
# Obtention initiale des certificats Let's Encrypt (Certbot) pour le domaine LWS.
set -euo pipefail

DOMAIN="${1:-smart-transport.fr}"
EMAIL="${2:-admin@smart-transport.fr}"

echo "🔐 Initialisation TLS pour $DOMAIN"

# Certbot en mode webroot (nginx doit servir /.well-known/acme-challenge)
docker run --rm \
  -v "$(pwd)/nginx/certs:/etc/letsencrypt" \
  -v certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email

# Lien des certificats au chemin attendu par nginx
cp "nginx/certs/live/$DOMAIN/fullchain.pem" nginx/certs/fullchain.pem
cp "nginx/certs/live/$DOMAIN/privkey.pem"  nginx/certs/privkey.pem

docker compose restart nginx
echo "✅ HTTPS actif. Pensez à programmer 'certbot renew' (cron mensuel)."
