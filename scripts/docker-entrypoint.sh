#!/bin/sh
set -e

# Ensure staticfiles and media directories exist with correct permissions
if [ "$(id -u)" = "0" ]; then
    # Running as root - set permissions and switch to scout user
    mkdir -p /app/staticfiles /app/media/charts
    chown -R scout:scout /app/staticfiles /app/media
    chmod -R 2775 /app/staticfiles /app/media
    # Use su-exec if available, otherwise su
    if command -v su-exec >/dev/null 2>&1; then
        exec su-exec scout "$0" "$@"
    else
        exec su scout -c "$0 $*"
    fi
fi

# Running as scout user (non-root)
# Only run migrations/collectstatic if manage.py exists (Django app)
if [ -f "/app/manage.py" ]; then
    echo "▶ Running database migrations..."
    python manage.py migrate --noinput || echo "⚠ Migration failed, continuing..."

    echo "▶ Collecting static files..."
    python manage.py collectstatic --noinput || echo "⚠ collectstatic failed, continuing..."

    # Optional: wait for DB and bootstrap data if DB is empty
    if [ "${BOOTSTRAP_ON_EMPTY:-false}" = "true" ] || [ "${BOOTSTRAP_ON_EMPTY:-0}" = "1" ]; then
        echo "▶ BOOTSTRAP_ON_EMPTY enabled. Checking database status..."
        python - <<'PY'
import os, sys, time
import urllib.parse as u
import psycopg2

def db_ready(dsn: str, retries: int = 30, delay: float = 2.0) -> bool:
    for _ in range(retries):
        try:
            p = u.urlparse(dsn.replace('+psycopg2',''))
            conn = psycopg2.connect(
                host=p.hostname, port=p.port, user=p.username,
                password=p.password, dbname=p.path.lstrip('/')
            )
            conn.close()
            return True
        except Exception as e:
            time.sleep(delay)
    return False

dsn = os.getenv('DATABASE_URL', 'postgresql://scout:scout@pg:5432/scouting')
if not db_ready(dsn):
    print('DB not ready after retries; continuing without bootstrap')
    sys.exit(0)

import contextlib
from psycopg2 import sql
p = u.urlparse(dsn.replace('+psycopg2',''))
conn = psycopg2.connect(host=p.hostname, port=p.port, user=p.username, password=p.password, dbname=p.path.lstrip('/'))
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
    n = cur.fetchone()[0]
    empty = (n == 0)
print(f"Tables in public schema: {n}")
open('/tmp/__db_empty_flag__', 'w').write('1' if empty else '0')
conn.close()
PY

        if [ "$(cat /tmp/__db_empty_flag__ 2>/dev/null || echo 0)" = "1" ]; then
            echo "▶ Database appears empty. Running bootstrap ingest..."
            NEWS_CSV_PATH="${NEWS_CSV_PATH:-/app/data/news_export.csv}"
            PLAYERS_CSV_PATH="${PLAYERS_CSV_PATH:-/app/data/all_players_plus_historic_data_aggregated_v3.csv}"
            HISTORY_CSV_PATH="${HISTORY_CSV_PATH:-/app/data/all_players_plus_historic_data_non_aggregated_v3.csv}"
            RATINGS_CSV_PATH="${RATINGS_CSV_PATH:-/app/data/player_ratings.csv}"

            python -m apps.ingestion.seed_and_ingest \
              --players-csv "$PLAYERS_CSV_PATH" \
              --history-csv "$HISTORY_CSV_PATH" \
              --ratings-csv "$RATINGS_CSV_PATH" \
              --news-csv "$NEWS_CSV_PATH" \
              --replace --replace-history --replace-ratings --replace-news \
              --refresh-embs --verbose || echo "⚠ bootstrap ingest failed, continuing..."
        else
            echo "▶ Database already initialized. Skipping bootstrap ingest."
        fi
    fi
fi

echo "▶ Starting application..."
exec "$@"

