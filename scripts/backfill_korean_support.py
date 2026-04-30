from __future__ import annotations

import argparse
import json
from pathlib import Path

from recommender.src.collector import _fetch_app_metadata
from recommender.src.db import get_connection, init_db


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Korean support fields for existing games.")
    parser.add_argument("--db", default="data/recommender/steam_mvp.db")
    parser.add_argument("--limit", type=int, default=0, help="0 means all")
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(db_path)

    with get_connection(db_path) as conn:
        rows = conn.execute(
            """
            SELECT app_id
            FROM games
            WHERE korean_interface IS NULL
               OR korean_subtitles IS NULL
               OR korean_audio IS NULL
            ORDER BY app_id
            """
        ).fetchall()
        app_ids = [int(r["app_id"]) for r in rows]

    if args.limit and args.limit > 0:
        app_ids = app_ids[: args.limit]

    updated = 0
    failed = 0
    for idx, app_id in enumerate(app_ids, start=1):
        try:
            meta = _fetch_app_metadata(app_id)
            if not meta:
                failed += 1
                continue
            with get_connection(db_path) as conn:
                conn.execute(
                    """
                    UPDATE games
                    SET korean_interface = ?,
                        korean_subtitles = ?,
                        korean_audio = ?
                    WHERE app_id = ?
                    """,
                    (
                        int(meta.get("korean_interface") or 0),
                        int(meta.get("korean_subtitles") or 0),
                        int(meta.get("korean_audio") or 0),
                        app_id,
                    ),
                )
                conn.commit()
            updated += 1
        except Exception:
            failed += 1

        if idx % 100 == 0:
            print(json.dumps({"processed": idx, "updated": updated, "failed": failed}, ensure_ascii=False), flush=True)

    with get_connection(db_path, readonly=True) as conn:
        remain = conn.execute(
            """
            SELECT COUNT(*) AS c
            FROM games
            WHERE korean_interface IS NULL
               OR korean_subtitles IS NULL
               OR korean_audio IS NULL
            """
        ).fetchone()["c"]

    print(
        json.dumps(
            {
                "target": len(app_ids),
                "updated": updated,
                "failed": failed,
                "remaining_null_rows": int(remain),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

