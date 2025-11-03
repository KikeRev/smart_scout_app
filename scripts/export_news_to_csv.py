import os
import csv
from datetime import timezone

import psycopg2


def get_conn():
    """Create a PostgreSQL connection using environment variables.

    Expected env vars (with defaults for local dev):
      - DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME", "scouting"),
        user=os.getenv("DB_USER", "scout"),
        password=os.getenv("DB_PASSWORD", "scout"),
    )


def export_news(csv_path: str) -> int:
    """Export football_news and player links to a CSV compatible with
    apps.ingestion.seed_and_ingest.load_news_from_csv.

    Columns: url,title,published_at,article_text,summary,source_id,player_ids,player_names
    """
    conn = get_conn()
    try:
        cur = conn.cursor()

        # Get news
        cur.execute(
            """
            SELECT id, url, title, published_at, article_text, summary, COALESCE(source_id,'csv_export')
            FROM football_news
            ORDER BY published_at DESC, id DESC
            """
        )
        news_rows = cur.fetchall()

        # Build mapping news_id -> [player_id, player_name]
        cur.execute(
            """
            SELECT pn.news_id, p.id, p.full_name
            FROM player_news pn
            JOIN players p ON p.id = pn.player_id
            """
        )
        links = {}
        for news_id, pid, pname in cur.fetchall():
            links.setdefault(news_id, {"ids": [], "names": []})
            links[news_id]["ids"].append(str(pid))
            links[news_id]["names"].append(pname or "")

        # Write CSV
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "url",
                "title",
                "published_at",
                "article_text",
                "summary",
                "source_id",
                "player_ids",
                "player_names",
            ])

            for nid, url, title, published_at, article_text, summary, source_id in news_rows:
                # Normalize timestamp to ISO UTC
                if published_at is not None and published_at.tzinfo is None:
                    published_at = published_at.replace(tzinfo=timezone.utc)
                iso_ts = published_at.isoformat() if published_at is not None else ""

                link = links.get(nid, {"ids": [], "names": []})
                writer.writerow([
                    url or "",
                    title or "",
                    iso_ts,
                    (article_text or "").replace("\r\n", " ").replace("\n", " "),
                    (summary or "").replace("\r\n", " ").replace("\n", " "),
                    source_id or "csv_export",
                    ",".join(link["ids"]),
                    ",".join(link["names"]),
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


