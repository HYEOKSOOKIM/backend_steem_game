"""Local JSON storage helpers for the review-insights MVP."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class FileStore:
    """Persist structured data into the local app data directory."""

    def __init__(
        self,
        root_dir: str | Path,
        fallback_root_dir: str | Path | None = None,
    ):
        self.root_dir = Path(root_dir)
        self.fallback_root_dir = (
            Path(fallback_root_dir) if fallback_root_dir is not None else None
        )

    def ensure_dir(self, relative_dir: str | Path) -> Path:
        target_dir = self.root_dir / Path(relative_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def write_json(self, relative_path: str | Path, payload: Any) -> Path:
        target_path = self.root_dir / Path(relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return target_path

    def read_json(self, relative_path: str | Path) -> Any:
        target_path = self.root_dir / Path(relative_path)
        return json.loads(target_path.read_text(encoding="utf-8"))

    def _sanitize_game_name_for_filename(self, game_name: str) -> str:
        """Sanitize a game name so it can be safely used in Windows filenames."""
        cleaned = re.sub(r'[<>:"/\\|?*]', "_", (game_name or "").strip())
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned or "unknown"

    def _build_appid_filename(self, appid: int, game_name: str | None = None) -> str:
        if game_name:
            safe_name = self._sanitize_game_name_for_filename(game_name)
            return f"{appid}({safe_name}).json"
        return f"{appid}.json"

    def _resolve_appid_file_path(self, relative_dir: str | Path, appid: int) -> Path:
        candidates = [self.root_dir]
        if self.fallback_root_dir is not None and self.fallback_root_dir != self.root_dir:
            candidates.append(self.fallback_root_dir)

        missing_targets: list[str] = []
        for base_root in candidates:
            base_dir = base_root / Path(relative_dir)
            exact_path = base_dir / f"{appid}.json"
            if not base_dir.exists():
                missing_targets.append(str(exact_path))
                continue

            named_candidates = sorted(
                path
                for path in base_dir.glob("*.json")
                if path.name.startswith(f"{appid}(") and path.name.endswith(".json")
            )
            if named_candidates:
                return max(named_candidates, key=lambda path: path.stat().st_mtime)

            if exact_path.exists():
                return exact_path

            loose_candidates = sorted(base_dir.glob(f"{appid}*.json"))
            if loose_candidates:
                return max(loose_candidates, key=lambda path: path.stat().st_mtime)

            missing_targets.append(str(exact_path))

        raise FileNotFoundError(", ".join(missing_targets))

    def write_raw_reviews(self, appid: int, payload: Any, game_name: str | None = None) -> Path:
        return self.write_json(Path("raw") / self._build_appid_filename(appid, game_name), payload)

    def write_game_metadata(self, appid: int, payload: Any, game_name: str | None = None) -> Path:
        return self.write_json(Path("metadata") / self._build_appid_filename(appid, game_name), payload)

    def write_processed_reviews(self, appid: int, payload: Any, game_name: str | None = None) -> Path:
        return self.write_json(Path("processed") / self._build_appid_filename(appid, game_name), payload)

    def write_analysis_result(self, appid: int, payload: Any, game_name: str | None = None) -> Path:
        return self.write_json(Path("analysis") / self._build_appid_filename(appid, game_name), payload)

    def write_report_view(self, appid: int, payload: Any, game_name: str | None = None) -> Path:
        return self.write_json(Path("report") / self._build_appid_filename(appid, game_name), payload)

    def read_raw_reviews(self, appid: int) -> Any:
        return json.loads(self._resolve_appid_file_path("raw", appid).read_text(encoding="utf-8"))

    def read_processed_reviews(self, appid: int) -> Any:
        return json.loads(self._resolve_appid_file_path("processed", appid).read_text(encoding="utf-8"))

    def read_analysis_result(self, appid: int) -> Any:
        return json.loads(self._resolve_appid_file_path("analysis", appid).read_text(encoding="utf-8"))

    def read_game_metadata(self, appid: int) -> Any:
        return json.loads(self._resolve_appid_file_path("metadata", appid).read_text(encoding="utf-8"))

    def read_report_view(self, appid: int) -> Any:
        return json.loads(self._resolve_appid_file_path("report", appid).read_text(encoding="utf-8"))
