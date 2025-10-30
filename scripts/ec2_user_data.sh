#!/bin/bash
set -euo pipefail

# Install dependencies
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y jq awscli docker.io
systemctl enable docker
systemctl start docker

# Configuration (override via EC2 user data variables if needed)
APP_PORT=${APP_PORT:-8000}
# Defaults basados en tu ECR
ACCOUNT_ID=${ACCOUNT_ID:-171870765902}
REGION=${REGION:-us-east-1}
ECR_REPOSITORY=${ECR_REPOSITORY:-smart-scout-app-test-v1}
IMAGE_TAG=${IMAGE_TAG:-latest}
# Prefijo SSM para entorno de desarrollo
SSM_PREFIX=${SSM_PREFIX:-/smart-scout/dev}

# Resolve region (permite override por variable y si no, detecta)
if [ -z "${REGION}" ]; then
  REGION=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region)
fi

# Login to ECR
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

echo "Pulling $IMAGE_URI"
docker pull "$IMAGE_URI"

# Optional: load env vars from SSM Parameter or local file at /etc/app_env
# Preferir SSM si SSM_PREFIX está definido
if [ -n "$SSM_PREFIX" ]; then
  echo "Fetching env vars from SSM prefix: $SSM_PREFIX"
  aws ssm get-parameters-by-path --path "$SSM_PREFIX" --with-decryption --region "$REGION" \
    --query 'Parameters[].{Name:Name,Value:Value}' --output text \
    | awk '{sub(".*/","",$1); print $1"="$2}' > /etc/app_env || true
fi

if [ -f /etc/app_env ]; then
  ENV_FILE_ARG=(--env-file /etc/app_env)
else
  ENV_FILE_ARG=()
fi

# Run container
docker rm -f app || true
docker run -d --restart=always \
  -p "$APP_PORT:$APP_PORT" \
  --name app \
  "${ENV_FILE_ARG[@]}" \
  "$IMAGE_URI"

echo "Container started on port $APP_PORT"

# Post-deploy: ejecutar migraciones y collectstatic (idempotentes)
echo "Running database migrations..."
docker exec app python manage.py migrate --noinput || true

echo "Collecting static files..."
docker exec app python manage.py collectstatic --noinput || true


