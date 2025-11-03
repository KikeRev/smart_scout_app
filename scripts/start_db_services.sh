#!/bin/bash
# Script para levantar Postgres y Redis en EC2
# Ejecutar desde dentro de la instancia EC2

set -e

NETWORK="scouting-net"
DB_NAME="pg"
REDIS_NAME="redis"

# Crear red si no existe
docker network create "$NETWORK" 2>/dev/null || true

echo "📊 Starting PostgreSQL container..."
docker rm -f "$DB_NAME" 2>/dev/null || true
docker run -d --restart=always \
  --name "$DB_NAME" \
  --network "$NETWORK" \
  -p 5432:5432 \
  -e POSTGRES_USER=scout \
  -e POSTGRES_PASSWORD=scout \
  -e POSTGRES_DB=scouting \
  -v pgdata:/var/lib/postgresql/data \
  ankane/pgvector:latest

echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 5

# Crear extensión pgvector
docker exec "$DB_NAME" psql -U scout -d scouting -c "CREATE EXTENSION IF NOT EXISTS vector;" || true

echo "🔴 Starting Redis container..."
docker rm -f "$REDIS_NAME" 2>/dev/null || true
docker run -d --restart=always \
  --name "$REDIS_NAME" \
  --network "$NETWORK" \
  -p 6379:6379 \
  redis:7-alpine

echo "✅ Database services started!"
echo ""
echo "Verify with: docker ps"
echo "Check logs: docker logs $DB_NAME or docker logs $REDIS_NAME"


