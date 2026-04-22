from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen


APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"


def _http_get_json(url: str, params: dict[str, Any], retries: int = 5) -> dict[str, Any]:
    full_url = f"{url}?{urlencode(params)}"
    backoff = 1.2
    for attempt in range(retries):
        try:
            with urlopen(full_url, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.8
                continue
            raise
        except URLError:
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 1.6
                continue
            raise
    return {}


def _fetch_name(app_id: int, language: str) -> str:
    payload = _http_get_json(APP_DETAILS_URL, {"appids": app_id, "l": language})
    item = payload.get(str(app_id), {})
    if not item.get("success"):
        return ""
    data = item.get("data") or {}
    return str(data.get("name") or "").strip()


def backfill_names(db_path: Path, sleep_sec: float = 0.05) -> tuple[int, int]:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT app_id
            FROM games
            WHERE COALESCE(TRIM(name_en), '') = ''
               OR COALESCE(TRIM(name_ko), '') = ''
            ORDER BY app_id
            """
        ).fetchall()
        app_ids = [int(r["app_id"]) for r in rows]
        total = len(app_ids)
        updated = 0

        for idx, app_id in enumerate(app_ids, start=1):
            try:
                name_en = _fetch_name(app_id, "english")
                name_ko = _fetch_name(app_id, "koreana")
                default_name = name_ko or name_en
                if not default_name:
                    continue

                conn.execute(
                    """
                    UPDATE games
                    SET name = COALESCE(NULLIF(?, ''), name),
                        name_en = COALESCE(NULLIF(?, ''), name_en),
                        name_ko = COALESCE(NULLIF(?, ''), name_ko),
                        updated_at = datetime('now')
                    WHERE app_id = ?
                    """,
                    (default_name, name_en, name_ko, app_id),
                )
                updated += 1

                if idx % 50 == 0:
                    conn.commit()
                    print(f"[progress] {idx}/{total} processed, {updated} updated")
                if sleep_sec > 0:
                    time.sleep(sleep_sec)
            except Exception as exc:
                print(f"[warn] app_id={app_id} skipped: {exc}")
                continue

        conn.commit()
        return total, updated
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill English/Korean game names into games table.")
    parser.add_argument("--db", default="data/recommender/steam_mvp.db", help="SQLite DB path")
    parser.add_argument("--sleep", type=float, default=0.05, help="Sleep seconds between app calls")
    args = parser.parse_args()

    db_path = Path(args.db)
    total, updated = backfill_names(db_path=db_path, sleep_sec=max(0.0, args.sleep))
    print(f"[done] total={total}, updated={updated}, db={db_path}")


if __name__ == "__main__":
    main()
