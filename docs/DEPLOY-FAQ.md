# Smart Scout App – Deployment FAQ (EC2 + ALB + Cloudflare + Okta)

Quick reference with real issues and proven fixes encountered during EC2 deployments.

## Table of Contents
- Docker networking and connectivity
- EC2 + SSM (Session Manager)
- Docker / ECR / Images
- Database (PostgreSQL + pgvector) and Redis
- Django (web app)
- FastAPI (api)
- Static files (CSS/JS/images)
- Health checks (ALB)
- Data ingestion and news CSV
- PowerShell vs Bash notes

---

## Docker networking and connectivity

- Symptom: `could not translate host name "pg" ...` or API “hangs”.
  - Cause: containers are not on the same user-defined network, or `pg` is down.
  - Fix (on EC2):
    ```bash
    docker network create scouting-net || true
    docker network connect scouting-net app || true
    docker network connect scouting-net api || true
    docker network connect scouting-net pg  || true
    docker network connect scouting-net redis || true
    docker exec app getent hosts pg
    docker exec app curl -sS http://api:8001/docs | head -n 3
    ```

- Symptom: frontend calls `http://api:8001` directly from the browser and fails.
  - Cause: `api` is an internal Docker hostname.
  - Fix: route requests through Django (proxy/views), not directly to `api` from the browser.

---

## EC2 + SSM (Session Manager)

- Symptom: `TargetNotConnected` when starting a session.
  - Causes/Fixes:
    - Instance profile missing `AmazonSSMManagedInstanceCore`.
    - Private subnet without VPC Endpoints: create `com.amazonaws.<region>.{ssm,ssmmessages,ec2messages}`.
    - Security Group without egress 443.
  - PowerShell example:
    ```powershell
    $Region="us-east-1"; $Profile="KikeRev"; $VpcId="vpc-..."; $SubnetIds="subnet-..."; $SgId="sg-..."
    aws ec2 create-vpc-endpoint --vpc-endpoint-type Interface --vpc-id $VpcId --service-name "com.amazonaws.$Region.ssm" --subnet-ids $SubnetIds --security-group-ids $SgId --region $Region --profile $Profile
    aws ec2 create-vpc-endpoint --vpc-endpoint-type Interface --vpc-id $VpcId --service-name "com.amazonaws.$Region.ssmmessages" --subnet-ids $SubnetIds --security-group-ids $SgId --region $Region --profile $Profile
    aws ec2 create-vpc-endpoint --vpc-endpoint-type Interface --vpc-id $VpcId --service-name "com.amazonaws.$Region.ec2messages" --subnet-ids $SubnetIds --security-group-ids $SgId --region $Region --profile $Profile
    ```

---

## Docker / ECR / Images

- Symptom: `pull access denied` after `Login Succeeded`.
  - Cause: expired token.
  - Fix (PowerShell):
    ```powershell
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <acct>.dkr.ecr.us-east-1.amazonaws.com
    ```

- Symptom: `containerd.io : Conflicts: containerd` while installing Docker.
  - Fix: remove conflicting packages and install via the official script.

- Symptom: container restarts with `/bin/sh: 1: [bash]: not found`.
  - Cause: `CMD`/`ENTRYPOINT` uses `bash` on an image with only `sh`.
  - Quick fix: run with `sh -lc "..."`. Permanent fix: exec-form `CMD ["python","-m","gunicorn",...]`.

- Symptom: immutable ECR tag.
  - Fix: use a new tag (e.g., `1.6.2`) or enable mutability.

---

## Database (PostgreSQL + pgvector) and Redis

- Symptom: `psycopg2.errors.FeatureNotSupported: extension "vector" is not available`.
  - Fix: use `ankane/pgvector:latest` and create the extension:
    ```bash
    docker exec pg psql -U scout -d scouting -c "CREATE EXTENSION IF NOT EXISTS vector;"
    ```

- Symptom: DB is empty after restart.
  - Cause: `pg` container recreated without the previous volume.
  - Fix: run with a named volume: `-v pgdata:/var/lib/postgresql/data` or reattach the old volume.

- Symptom (Django): connects to `localhost` from within the container.
  - Fix: `DATABASE_URL=postgresql+psycopg2://scout:scout@pg:5432/scouting` (host `pg`).

---

## Django (web app)

- Recommended env vars (`/etc/app_env` or SSM):
  - `DJANGO_SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`
  - `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`

- Symptom: `Invalid HTTP_HOST header` / CSRF 403.
  - Fix: add public domain to `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS=https://<domain>`.

- Symptom: `/health` → 404.
  - Cause: build without health route.
  - Fix: add `path("health", ...)` in `config/urls.py`, or set ALB health check to `/` (accept 200–399).

- Quick start for tests:
  ```bash
  # With DEBUG=False and no static server, you can:
  python manage.py runserver 0.0.0.0:8000 --insecure
  ```

---

## FastAPI (api)

- Recommended command:
  ```bash
  uvicorn apps.agent_service.main:app --host 0.0.0.0 --port 8001 --workers 2 --log-level info
  ```

- Basic checks:
  ```bash
  docker exec app curl -sS http://api:8001/docs | head
  ```

---

## Static files (CSS/JS/images)

- Symptom: 404 on `/static/...` or images disappear after container restart.
  - Causes: `STATIC_ROOT` permissions or `DEBUG=False` without a static server. New containers start empty.
  - **Automatic fix (recommended)**: The Docker image includes `docker-entrypoint.sh` that automatically:
    - Sets correct permissions for `/app/staticfiles` and `/app/media`
    - Runs `migrate` and `collectstatic` on startup
    - Works whether container starts as root or scout user
  - When using the entrypoint, simply run:
    ```bash
    docker run -d --restart=always --network scouting-net -p 80:8000 --name app \
      --env-file /etc/app_env \
      <image>:<tag> \
      python manage.py runserver 0.0.0.0:8000 --insecure
    ```
    The entrypoint will handle migrations and collectstatic automatically.
  - Manual fix (if entrypoint not used):
    ```bash
    docker exec --user root app sh -lc 'mkdir -p /app/staticfiles && chown -R scout:scout /app/staticfiles && chmod -R 2775 /app/staticfiles'
    docker exec app python manage.py collectstatic --noinput
    ```
  - For tests with `runserver`: `--insecure` allows serving static with `DEBUG=False`.

- Stadium images not visible at first load:
  - If using the entrypoint script, images will be collected automatically. Hard refresh (Ctrl+F5) if needed. If using Cloudflare, enable Development Mode to bypass cache.

---

## Health checks (ALB)

- If the image does not expose `/health`, configure the Target Group to:
  - Path `/` and `HttpCode=200-399`.
  - Port `80` (if mapping `-p 80:8000`).

---

## Data ingestion and news CSV

- Flags in `apps/ingestion/seed_and_ingest.py`:
  - `--news-csv <path>` and `--replace-news`
  - CSV supports `embedding` (JSON) to avoid recomputation; missing vectors are generated.

- Export news with embeddings:
  ```bash
  python scripts/export_news_to_csv.py --out data/news_export.csv
  ```

- Import on EC2 (no image rebuild):
  ```bash
  docker exec --user root app sh -lc 'mkdir -p /app/data && chown -R scout:scout /app/data'
  docker exec app sh -lc 'curl -L -o /app/data/news_export.csv https://raw.githubusercontent.com/<org>/<repo>/main/app/data/news_export.csv'
  docker exec app python -m apps.ingestion.seed_and_ingest --news-csv /app/data/news_export.csv --replace-news --verbose
  ```

- If the running container lacks the flags (older build):
  - Overwrite the module in-place or deploy the clean image with the flags.

---

## PowerShell vs Bash notes

- Do not chain like Bash:
  - Bash: `cmd1 && cmd2`
  - PowerShell: use `;` or separate lines. Example:
    ```powershell
    aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <acct>.dkr.ecr.us-east-1.amazonaws.com
    docker build -t smart-scout-app:1.6.2 .
    docker tag smart-scout-app:1.6.2 <acct>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:1.6.2
    docker push <acct>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:1.6.2
    ```

---

## Quick recovery checklist

1) `docker ps` → `app`, `api`, `pg`, `redis` must be Up.
2) Network: `docker network inspect scouting-net` (all present).  
3) DB: `DATABASE_URL` points to `pg`; migrations applied (automatic with entrypoint).  
4) Static: `collectstatic` without permission errors (automatic with entrypoint); `curl -I /static/css/custom.css` → 200.  
5) ALB: health check to `/` if `/health` is missing.  
6) API: `curl` from `app` to `http://api:8001/docs` responds.  
7) News: use `--news-csv` for quick bootstrap.

---

## Recommended Docker Run Commands (EC2)

With the updated Dockerfile and entrypoint script, use these commands:

**App container (Django with Gunicorn - recommended for production):**
```bash
docker run -d --restart=always --network scouting-net -p 80:8000 --name app \
  --env-file /etc/app_env \
  <ecr-registry>/smart-scout-app-test-v1:<tag> \
  gunicorn config.wsgi:application \
    -b 0.0.0.0:8000 \
    --workers 2 \
    --threads 2 \
    --timeout 300 \
    --graceful-timeout 30 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --access-logfile - \
    --error-logfile -
```

**App container (Django with runserver - for development/testing only):**
```bash
docker run -d --restart=always --network scouting-net -p 80:8000 --name app \
  --env-file /etc/app_env \
  <ecr-registry>/smart-scout-app-test-v1:<tag> \
  python manage.py runserver 0.0.0.0:8000 --insecure
```

**API container (FastAPI):**
```bash
docker run -d --restart=always --network scouting-net --name api \
  --env-file /etc/app_env \
  <ecr-registry>/smart-scout-app-test-v1:<tag> \
  uvicorn apps.agent_service.main:app \
    --host 0.0.0.0 \
    --port 8001 \
    --workers 2 \
    --timeout-keep-alive 60 \
    --limit-max-requests 300 \
    --limit-keep-alive 30 \
    --log-level info
```

**Note**: If you see "Child process died" errors in logs, reduce workers to 1 or increase instance memory:
```bash
# Single worker (more stable, less parallelism)
uvicorn apps.agent_service.main:app --host 0.0.0.0 --port 8001 --workers 1 --timeout-keep-alive 60
```

The entrypoint automatically handles:
- Permissions setup for staticfiles/media
- Database migrations
- Static file collection

No manual intervention needed after container restarts.

---

## Timeout Configuration

- **Symptom**: Requests timeout during player searches or heavy operations.
  - **Causes**: Default timeouts too low for vector similarity searches, large dataset queries, or LLM calls.
  - **Fixes applied**:
    - **Gunicorn**: `--timeout 300` (5 minutes for long-running requests)
    - **Django DB**: `statement_timeout=300000` (5 minutes), `connect_timeout=30`
    - **FastAPI/Uvicorn**: `--timeout-keep-alive 60`
    - **HTTP requests**: Increased from 15s to 120s for internal API calls
    - **Environment variables** (optional overrides in `/etc/app_env`):
      - `DB_STATEMENT_TIMEOUT=300000` (milliseconds)
      - `DB_CONNECT_TIMEOUT=30` (seconds)
      - `DB_CONN_MAX_AGE=600` (seconds, connection pool lifetime)
  - **If timeouts persist**:
    - Increase instance size (more CPU/RAM)
    - Add database indexes on columns used in WHERE/ORDER BY
    - Consider pagination for large result sets
    - Use async queries for independent operations
  - **"Connection aborted" or "RemoteDisconnected" errors**:
    - API workers may be crashing (OOM). Check logs: `docker logs api`
    - Reduce uvicorn workers from 2 to 1 if instance is small (<4GB RAM)
    - Ensure API container has retry logic for transient failures
    - Check if `/players/search` endpoint is called without required `query` parameter (should use `/players/all` instead)

---

For a “clean” deployment, build an image that includes:
- Updated `seed_and_ingest.py` (news flags)
- `data/news_export.csv`
- WhiteNoise or Nginx for `/static` with `DEBUG=False`
- `/health` route in `config/urls.py`

This minimizes manual steps and avoids intermittent issues with static files and health checks.


