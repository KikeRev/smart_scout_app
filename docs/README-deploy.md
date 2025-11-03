## Deployment guide (env0 + EC2 + ALB + Cloudflare + Okta)

This document consolidates everything we validated while bringing the app up on env0 using the "aws-public-app-ec2" template. It includes prerequisites, variables, commands, and the most common pitfalls we hit (and how to fix them).

### 1) ECR repository
- Create the repository first (env0 template: `aws-ecr-private-repository`).
- Recommended settings:
  - `repository_name`: `smart-scout-app-test-v1` (or your preferred name)
  - Image tag immutability: enabled (you must push unique tags)
  - Scan on push: enabled
  - Lifecycle policy: keep last 10 images

### 2) Build and push the image (manual flow) — Actions optional
- Primary (manual) flow used in this deployment:
  1. Authenticate with AWS SSO (only once per session):
     - `aws sso login --profile <YOUR_PROFILE>`
     - `set/export AWS_PROFILE=<YOUR_PROFILE>` and `AWS_REGION=us-east-1`
  2. Login to ECR (token expires; repeat if push/pull is denied):
     - `aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com`
  3. Build, tag and push a unique tag:
     - `docker build -t smart-scout-app-test-v1:<TAG> .`
     - `docker tag smart-scout-app-test-v1:<TAG> <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG>`
     - `docker push <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG>`

- Optional: GitHub Actions (`.github/workflows/ecr-build-push.yml`) can automate the above once an OIDC role exists. For this guide we assume manual push.

### 3) env0 template "aws-public-app-ec2"
- Key variables:
  - `vpc_name`: existing VPC (pick from the dropdown; if empty, ensure permissions/region).
  - `instance_type`: `t3.medium` (or as needed)
  - `instance_num`: `1` (ASG>1 is supported)
  - `os`: Ubuntu 22.04/24.04
  - `custom_hostnames`: e.g. `["smartscoutapp.aws.bain.dev"]` (Bain convention)
  - Okta OIDC: client id/secret/issuer as provided
- Network/Access considerations for a private subnet:
  - If the instance runs in a private subnet without NAT: create VPC endpoints for `ecr.api`, `ecr.dkr`, `ssm`, `ssmmessages`, `ec2messages`, and `s3` (gateway) or use a NAT gateway.
  - The ALB Target Group should initially health-check `GET /` or `GET /health` on port 80.

### 4) Application runtime configuration (environment)
- We do not bake secrets into the image. Use an env file:`/etc/app_env` (or SSM Parameter Store in prod).
- Minimal variables (one per line):
```
DJANGO_SECRET_KEY=<your-secret>
ALLOWED_HOSTS=localhost,<instance_ip>,<public_hostname>
CSRF_TRUSTED_ORIGINS=https://<public_hostname>
SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https
SESSION_COOKIE_SECURE=true
CSRF_COOKIE_SECURE=true
DATABASE_URL=postgresql+psycopg2://scout:scout@pg:5432/scouting
REDIS_URL=redis://redis:6379/0
OPENAI_API_KEY=...
```
- If the shell makes it hard to type `@`, generate it via Python:
```
python3 - << 'PY' | sudo tee -a /etc/app_env >/dev/null
at = chr(64)
print("DATABASE_URL=postgresql+psycopg2://scout:scout"+at+"pg:5432/scouting")
PY
```

### 5) EC2 boot (user data)
- Script: `scripts/ec2_user_data.sh` logs into ECR, pulls the image and runs the Django container.
- It optionally reads SSM parameters if you set `SSM_PREFIX=/smart-scout/dev`.
- For quick tests, you can skip SSM and write `/etc/app_env` directly (see above).
- **Note**: The script only starts the `app` (Django) container. You must manually start `pg`, `redis`, and `api` containers as described in sections 7 and 8.

### 6) Running the app container (quick test)
- Development server (for quick validation):
```
docker run -d --restart=always --network scouting-net \
  -p 80:8000 --name app --env-file /etc/app_env \
  <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG> \
  sh -lc "python manage.py runserver 0.0.0.0:8000"
```
- Production server (recommended later):
  - Add `gunicorn` to `pyproject.toml`, rebuild, and run:
```
sh -lc "python -m gunicorn config.wsgi:application -b 0.0.0.0:8000 --workers 2"
```

### 7) Postgres & Redis (local containers vs managed services)
- For local dev on EC2:
```
docker network create scouting-net || true
docker run -d --name redis --network scouting-net -p 6379:6379 redis:7
```
- Use Postgres with pgvector support (required by the app):
```
docker rm -f pg || true
docker run -d --name pg --network scouting-net \
  -e POSTGRES_USER=scout -e POSTGRES_PASSWORD=scout -e POSTGRES_DB=scouting \
  -p 5432:5432 ankane/pgvector:latest

docker exec -it pg psql -U scout -d scouting -c 'CREATE EXTENSION IF NOT EXISTS vector;'
```
- The app must connect to the Postgres container using `pg` as host (Docker DNS), not `localhost`.

### 8) FastAPI service (required for agent functionality)
- **CRITICAL**: The agent service requires a separate FastAPI container running on port 8001.
- The Django app (`app` container) communicates with the API service via Docker networking.
- Start the API service (must be in the same `scouting-net` network):
```
docker run -d --restart=always --network scouting-net \
  --name api \
  --env-file /etc/app_env \
  <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG> \
  sh -lc "uvicorn apps.agent_service.main:app --host 0.0.0.0 --port 8001"
```
- Verify the API is running:
```
docker logs api
docker exec app curl http://api:8001/docs  # Should return Swagger UI HTML
```
- **Note**: If `DATABASE_URL` in `/etc/app_env` already points to `pg:5432`, the `--env-file` will provide all required environment variables automatically.
- **Architecture**: The app uses two services:
  - `app` (Django, port 8000) - Web interface and dashboard
  - `api` (FastAPI, port 8001) - Player search, similarity, ratings endpoints used by the agent

### 9) Health check and host configuration
- `config/urls.py` already exposes: `path("health", lambda r: HttpResponse("ok"))` (no trailing slash).
- ALB Target Group can use `/` or `/health` on port 80.
- `ALLOWED_HOSTS` must include your public hostname (e.g. `smartscoutapp.aws.bain.dev`).
- Behind Cloudflare/ALB you must set (via env):
  - `CSRF_TRUSTED_ORIGINS=https://<public_hostname>`
  - `SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https`
  - `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true`

### 10) Seeding/ingestion
- Full initial ingestion (players + history + ratings + news from CSV) using CSVs already in the repo:
```
docker run --rm -it --network scouting-net --env-file /etc/app_env \
  <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG> \
  sh -lc 'python -m apps.ingestion.seed_and_ingest \
    --players-csv data/all_players_plus_historic_data_aggregated_v3.csv \
    --history-csv data/all_players_plus_historic_data_non_aggregated_v3.csv \
    --ratings-csv data/player_ratings.csv \
    --news-csv data/news_template.csv \
    --replace --replace-history --replace-ratings --replace-news --refresh-embs \
    --verbose'
```
- **News CSV format** (`data/news_template.csv` is an example):
  - Required columns: `url`, `title`, `published_at` (ISO format: `2024-10-31T10:00:00Z`)
  - Optional columns: `article_text`, `summary`, `source_id`, `player_ids` (comma-separated), `player_names` (comma-separated)
  - If `summary` is missing, it will be auto-generated from `article_text` or `title`
  - If `article_text` is missing, `title` will be used as fallback
- **Ongoing news updates via RSS** (for production cron jobs):
```
docker run --rm --network scouting-net --env-file /etc/app_env \
  <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG> \
  sh -lc 'python -m apps.ingestion.seed_and_ingest --ingest-news --verbose'
```
- View logs in real time: add `-it` and drop the container name; or run detached with `--name ingest` and `docker logs -f ingest`.
- **Export existing news to CSV** (for backup):
```
docker run --rm --network scouting-net --env-file /etc/app_env \
  -v $(pwd)/data:/app/data \
  <ACCOUNT>.dkr.ecr.us-east-1.amazonaws.com/smart-scout-app-test-v1:<TAG> \
  sh -lc 'python scripts/export_news_to_csv.py --output data/news_backup.csv --verbose'
```
- **Recommended workflow**:
  1. **Export existing news**: Use `scripts/export_news_to_csv.py` to create a backup CSV from current database
  2. **Initial deployment**: Use `--news-csv` with the backup CSV for baseline news data
  3. **Production**: Set up a cron job to run `--ingest-news` periodically (e.g., every 6 hours) to fetch latest RSS feeds
  4. **Periodic backups**: Periodically export news to CSV for disaster recovery

### 11) SSM Session Manager connectivity issues

If you get `TargetNotConnected` when trying to connect via SSM:

**Problem**: Instance in private subnet cannot reach SSM service endpoints.

**Solution 1: Create VPC endpoints for SSM (recommended for private subnets)**

You need to create 3 VPC endpoints:
1. `com.amazonaws.us-east-1.ssm` (SSM service)
2. `com.amazonaws.us-east-1.ssmmessages` (SSM messages)
3. `com.amazonaws.us-east-1.ec2messages` (EC2 messages)

**Quick method (PowerShell)**:
```powershell
.\scripts\create-ssm-vpc-endpoints.ps1
```

**Manual method (AWS CLI)**:
```bash
VPC_ID="vpc-0db5698e5cb443dbf"
SUBNET_ID="subnet-0995876dededa596d"
SG_ID="sg-05086b4bff4981532"

# Create SSM endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.ssm \
  --subnet-ids $SUBNET_ID \
  --security-group-ids $SG_ID \
  --region us-east-1 \
  --profile KikeRev

# Create SSM messages endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.ssmmessages \
  --subnet-ids $SUBNET_ID \
  --security-group-ids $SG_ID \
  --region us-east-1 \
  --profile KikeRev

# Create EC2 messages endpoint
aws ec2 create-vpc-endpoint \
  --vpc-id $VPC_ID \
  --vpc-endpoint-type Interface \
  --service-name com.amazonaws.us-east-1.ec2messages \
  --subnet-ids $SUBNET_ID \
  --security-group-ids $SG_ID \
  --region us-east-1 \
  --profile KikeRev
```

**Note**: Security group must allow outbound HTTPS (443) to AWS endpoints.

**Solution 2: Move instance to public subnet**

If VPC endpoints are not an option, move the instance to a public subnet with Internet Gateway access so SSM Agent can reach AWS services via internet.

**Solution 3: Verify IAM role permissions**

Ensure the instance role has `AmazonSSMManagedInstanceCore` policy attached:
```bash
aws iam list-attached-role-policies --role-name <role-name> --profile KikeRev
```

**After creating endpoints**, wait 2-3 minutes and try connecting again:
```bash
aws ssm start-session --target i-<instance-id> --region us-east-1 --profile KikeRev
```

### 13) Common errors and fixes (field notes)
- ECR: `denied: Your authorization token has expired`
  - Re-run ECR login: `aws ecr get-login-password ... | docker login ...`
- GitHub OIDC error: `Source Account ID is needed` or empty role list
  - Use role ARN in `AWS_ROLE_TO_ASSUME` and ensure a GitHub OIDC role exists with trust `repo:<ORG>/<REPO>` and ECR push permissions.
- ALLOWED_HOSTS / 400 Bad Request
  - Add your hostname to `ALLOWED_HOSTS` and restart the app container.
- CSRF 403 behind ALB/Cloudflare
  - Set env vars: `CSRF_TRUSTED_ORIGINS=https://<public_hostname>`, `SECURE_PROXY_SSL_HEADER=HTTP_X_FORWARDED_PROTO,https`, and secure cookies.
- Health 404
  - Use `/` or ensure `path("health", ...)` is present (no trailing slash).
- Postgres connection refused from ingestion container
  - Use `--network scouting-net` and set `DATABASE_URL=...@pg:5432/...` (not `localhost`).
- `extension "vector" is not available`
  - Run Postgres with pgvector (e.g. `ankane/pgvector`) and `CREATE EXTENSION IF NOT EXISTS vector;`.
- Port mapping mismatch (ALB targets 80 but container listens on 8000)
  - Run with `-p 80:8000` or change the Target Group port accordingly.
- Tag immutability
  - Push a new unique tag (e.g. `dev-YYYYMMDDHHmmss`) and update the instance to use that tag.
- Agent API connection errors: `Failed to resolve 'api'` or `ConnectionError` to `http://api:8001`
  - **CRITICAL**: The FastAPI service must be running. See section 8 for setup.
  - Verify: `docker ps | grep api` should show the container running.
  - Test connectivity: `docker exec app curl http://api:8001/docs` should return Swagger UI.
  - Ensure both `app` and `api` containers are on `scouting-net`: `docker inspect <container> | grep -A 5 Networks`
- Static files permission errors during `collectstatic`
  - Run as root to fix permissions: `docker exec -u root app sh -c "rm -rf /app/staticfiles && mkdir -p /app/staticfiles && chown -R scout:scout /app/staticfiles && python manage.py collectstatic --noinput"`
- Unapplied migrations / missing tables (e.g. `django_session`)
  - Run migrations: `docker exec app python manage.py migrate`

### 14) Minimal smoke test
1) `curl -I http://localhost/health` → 200
2) Load `https://<public_hostname>` → if 400, fix `ALLOWED_HOSTS`; if 403 CSRF, fix `CSRF_TRUSTED_ORIGINS` and proxy header.
3) Try login page loads and static assets return 200.
4) Verify API service: `docker exec app curl http://api:8001/docs` → Should return Swagger UI HTML
5) Test agent functionality: Try asking the agent a question (e.g., "search for players similar to Toni Kroos") → Should not fail with connection errors

### 15) Next steps (hardening)
- Switch `runserver` to `gunicorn` and enable a process manager (systemd or Docker restart policy already in use).
- Move runtime secrets to SSM Parameter Store and let `scripts/ec2_user_data.sh` pull them using `SSM_PREFIX`.
- Add CloudWatch Logs or a log shipper.
- Optionally move DB/Redis to managed services (RDS / ElastiCache).

 
