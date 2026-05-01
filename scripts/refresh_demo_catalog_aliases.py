"""Rewrite demo_games.json with normalized manual alias overrides."""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from report.services.demo_catalog import load_demo_games, save_demo_games


def main() -> int:
    catalog_path = BACKEND_DIR / "data" / "report" / "catalog" / "demo_games.json"
    games = load_demo_games(catalog_path)
    save_demo_games(catalog_path, games)
    print(str(catalog_path))
    print(f"updated_games={len(games)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
