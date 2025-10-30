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
ECR_REPOSITORY=${ECR_REPOSITORY:-smart-scout-app}
IMAGE_TAG=${IMAGE_TAG:-latest}

# Resolve region
REGION=$(curl -s http://169.254.169.254/latest/dynamic/instance-identity/document | jq -r .region)

# Login to ECR
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$(aws sts get-caller-identity --query Account --output text).dkr.ecr.$REGION.amazonaws.com"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
IMAGE_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$ECR_REPOSITORY:$IMAGE_TAG"

echo "Pulling $IMAGE_URI"
docker pull "$IMAGE_URI"

# Optional: load env vars from SSM Parameter or local file at /etc/app_env
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


