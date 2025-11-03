import os
import csv
from datetime import timezone
import json
from urllib.parse import urlparse

import psycopg2


def _conn_from_database_url(dsn: str):
    """Build psycopg2 connection from DATABASE_URL.

    Accepts URLs like postgresql:// or postgresql+psycopg2://
    """
    # Normalize driver segment for psycopg2
    dsn = dsn.replace("postgresql+psycopg2://", "postgresql://")
    parsed = urlparse(dsn)
    return psycopg2.connect(
        dbname=(parsed.path or "/").lstrip("/"),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname,
        port=parsed.port or 5432,
    )


def get_conn():
    """Create a PostgreSQL connection using environment variables.

    Expected env vars (with defaults for local dev):
      - DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return _conn_from_database_url(database_url)
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "scouting"),
        user=os.getenv("DB_USER", "scout"),
        password=os.getenv("DB_PASSWORD", "scout"),
    )


def export_news(csv_path: str) -> int:
    """Export a CSV compatible with load_news_from_csv for bootstrap.

    Columns: url,title,published_at,article_text,summary,source_id,embedding
    - embedding is exported as JSON (list of floats) to avoid recalculation.
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        # Get news (minimal set of columns)
        cur.execute(
            """
            SELECT url, title, published_at, article_text, summary,
                   COALESCE(source_id,'csv_export') AS source_id,
                   embedding
            FROM football_news
            ORDER BY published_at DESC
            """
        )
        news_rows = cur.fetchall()

        # Write CSV
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["url","title","published_at","article_text","summary","source_id","embedding"])

            for url, title, published_at, article_text, summary, source_id, embedding in news_rows:
                # Normalize timestamp to ISO UTC
                if published_at is not None and published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                iso_ts = published_at.isoformat() if published_at is not None else ""
                emb_json = json.dumps(embedding) if embedding is not None else ""
                writer.writerow([
                    url or "",
                    title or "",
                    iso_ts,
                    (article_text or "").replace("\r\n", " ").replace("\n", " "),
                    (summary or "").replace("\r\n", " ").replace("\n", " "),
                    source_id or "csv_export",
                    emb_json,
                ])

        return len(news_rows)
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser("Export football_news to CSV")
    parser.add_argument("--out", default="data/news_export.csv", help="Output CSV path")
    args = parser.parse_args()

    total = export_news(args.out)
    print(f"✅ Exported {total} news rows to {args.out}")


