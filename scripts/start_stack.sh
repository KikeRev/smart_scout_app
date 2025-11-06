#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   bash scripts/start_stack.sh <IMAGE[:TAG]> [ENV_FILE=/etc/app_env] [NETWORK=scouting-net]
# Example:
#   bash scripts/start_stack.sh 171870765902.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:1.6.3

IMAGE_REF="${1:-}"
ENV_FILE="${2:-/etc/app_env}"
NETWORK_NAME="${3:-scouting-net}"

if [[ -z "${IMAGE_REF}" ]]; then
  echo "ERROR: You must pass the full image reference (including tag), e.g.:"
  echo "  bash scripts/start_stack.sh 171870765902.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:1.6.3"
  exit 1
fi

echo "▶ Using image: ${IMAGE_REF}"
echo "▶ Env file: ${ENV_FILE}"
echo "▶ Docker network: ${NETWORK_NAME}"

# 0) Pull image (idempotent)
docker pull "${IMAGE_REF}" || true

# 1) Network
docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1 || docker network create "${NETWORK_NAME}"

# 2) Datastores: Postgres (pgvector) and Redis
echo "▶ Starting Postgres (pgvector) and Redis"
docker run -d --restart=always --name pg --network "${NETWORK_NAME}" -p 5432:5432 \
  -e POSTGRES_USER=scout -e POSTGRES_PASSWORD=scout -e POSTGRES_DB=scouting \
  ankane/pgvector:latest 2>/dev/null || docker start pg

docker run -d --restart=always --name redis --network "${NETWORK_NAME}" -p 6379:6379 \
  redis:7 2>/dev/null || docker start redis

# 3) Wait for Postgres
echo "▶ Waiting for Postgres..."
for i in {1..30}; do
  if docker exec pg pg_isready -U scout -d scouting >/dev/null 2>&1; then
    echo "   Postgres OK"; break
  fi
  sleep 2
done

# 4) API (FastAPI)
echo "▶ Starting API (uvicorn)"
docker rm -f api 2>/dev/null || true
docker run -d --restart=always --network "${NETWORK_NAME}" --name api \
  --env-file "${ENV_FILE}" \
  "${IMAGE_REF}" sh -lc 'uvicorn apps.agent_service.main:app \
    --host 0.0.0.0 --port 8001 \
    --workers ${UVICORN_WORKERS:-1} \
    --timeout-keep-alive ${UVICORN_TKA:-120} \
    --log-level info'

# 5) APP (Django + gunicorn)
echo "▶ Starting APP (gunicorn)"
docker rm -f app 2>/dev/null || true
docker run -d --restart=always --network "${NETWORK_NAME}" -p 80:8000 --name app \
  --env-file "${ENV_FILE}" \
  "${IMAGE_REF}" sh -lc 'gunicorn config.wsgi:application \
    -b 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-2} \
    --threads ${GUNICORN_THREADS:-2} \
    --timeout ${GUNICORN_TIMEOUT:-600} \
    --graceful-timeout ${GUNICORN_GRACEFUL_TIMEOUT:-60} \
    --max-requests ${GUNICORN_MAX_REQ:-1000} \
    --max-requests-jitter ${GUNICORN_MAX_REQ_JITTER:-50} \
    --access-logfile - --error-logfile -'

# 6) Basic checks with small waits
echo "▶ Waiting for API (health)"
for i in {1..30}; do
  if docker exec app sh -lc 'curl -sS http://api:8001/docs >/dev/null 2>&1'; then
    echo "   API OK"; break
  fi
  sleep 2
done

echo "▶ Waiting for APP (HTTP)"
for i in {1..30}; do
  if docker exec app sh -lc 'curl -sI -m 2 -s http://localhost:8000/ | head -n1 | grep -qE "HTTP/1.1|HTTP/2"'; then
    echo "   APP OK"; break
  fi
  sleep 2
done

echo "✅ Stack is up with image ${IMAGE_REF}"


