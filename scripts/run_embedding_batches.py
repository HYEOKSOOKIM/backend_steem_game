from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from recommender.src.chroma_store import sync_game_profiles_to_chroma
from recommender.src.db import get_connection, init_db
from recommender.src.features import TRUST_WEIGHTS


def _serialize_vector(vec: np.ndarray) -> bytes:
    return vec.astype(np.float32).tobytes()


def _load_model(model_name: str) -> SentenceTransformer:
    offline = os.getenv("HF_HUB_OFFLINE", "").strip() == "1" or os.getenv(
        "TRANSFORMERS_OFFLINE", ""
    ).strip() == "1"
    if offline:
        return SentenceTransformer(model_name, local_files_only=True)
    return SentenceTransformer(model_name)


def _remaining(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS c FROM reviews WHERE cleaned_text IS NOT NULL AND cleaned_text != '' AND embedding IS NULL").fetchone()
    return int(row["c"] if row else 0)


def run_embedding_batches(
    db_path: Path,
    model_name: str,
    select_batch: int,
    encode_batch: int,
    max_loops: int,
) -> dict:
    model = _load_model(model_name)
    total_updated = 0
    loops = 0
    started = datetime.now(timezone.utc).isoformat()

    with get_connection(db_path) as conn:
        while loops < max_loops:
            loops += 1
            rows = conn.execute(
                """
                SELECT review_id, cleaned_text
                FROM reviews
                WHERE cleaned_text IS NOT NULL AND cleaned_text != '' AND embedding IS NULL
                LIMIT ?
                """,
                (int(select_batch),),
            ).fetchall()
            if not rows:
                break

            texts = [str(r["cleaned_text"]) for r in rows]
            emb = model.encode(
                texts,
                batch_size=int(encode_batch),
                convert_to_numpy=True,
                show_progress_bar=False,
                normalize_embeddings=True,
            )
            for row, vec in zip(rows, emb):
                conn.execute(
                    "UPDATE reviews SET embedding = ? WHERE review_id = ?",
                    (_serialize_vector(vec), str(row["review_id"])),
                )
            conn.commit()
            total_updated += len(rows)

            rem = _remaining(conn)
            print(
                json.dumps(
                    {
                        "loop": loops,
                        "updated_this_loop": len(rows),
                        "updated_total": total_updated,
                        "remaining": rem,
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
            if rem <= 0:
                break

    finished = datetime.now(timezone.utc).isoformat()
    with get_connection(db_path, readonly=True) as ro:
        remaining = _remaining(ro)
    return {
        "started_at": started,
        "finished_at": finished,
        "loops": loops,
        "updated_total": total_updated,
        "remaining": remaining,
    }


def _deserialize_vector(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def rebuild_profiles(db_path: Path) -> dict:
    from collections import defaultdict
    from datetime import timedelta

    app_to_vectors: dict[int, list[np.ndarray]] = defaultdict(list)
    app_to_dates: dict[int, list[datetime]] = defaultdict(list)
    app_to_votes: dict[int, list[int]] = defaultdict(list)
    app_to_playtime: dict[int, list[int]] = defaultdict(list)
    app_to_weights: dict[int, list[float]] = defaultdict(list)

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=365)
    profile_count = 0

    with get_connection(db_path) as conn:
        vec_rows = conn.execute(
            """
            SELECT app_id, embedding, review_date, voted_up, playtime_forever, trust_label
            FROM reviews
            WHERE embedding IS NOT NULL
            """
        ).fetchall()

        for row in vec_rows:
            app_id = int(row["app_id"])
            app_to_vectors[app_id].append(_deserialize_vector(row["embedding"]))
            app_to_votes[app_id].append(int(row["voted_up"] or 0))
            app_to_playtime[app_id].append(int(row["playtime_forever"] or 0))
            trust = str(row["trust_label"] or "").lower()
            app_to_weights[app_id].append(float(TRUST_WEIGHTS.get(trust, 0.3)))
            try:
                app_to_dates[app_id].append(datetime.fromisoformat(row["review_date"]))
            except Exception:
                pass

        for app_id, vectors in app_to_vectors.items():
            if not vectors:
                continue
            mat = np.vstack(vectors)
            weights = np.asarray(app_to_weights.get(app_id, []), dtype=np.float32)
            if weights.shape[0] != mat.shape[0] or float(weights.sum()) <= 0.0:
                profile = mat.mean(axis=0)
            else:
                w = weights / float(weights.sum())
                profile = (mat * w[:, None]).sum(axis=0)
            norm = np.linalg.norm(profile)
            if norm > 0:
                profile = profile / norm

            dates = app_to_dates.get(app_id, [])
            recent_review_count = sum(1 for d in dates if d >= cutoff)
            votes = app_to_votes.get(app_id, [])
            positive_ratio = float(sum(votes) / len(votes)) if votes else 0.0
            playtimes = app_to_playtime.get(app_id, [])
            median_playtime = float(np.median(playtimes)) if playtimes else 0.0

            conn.execute(
                """
                INSERT INTO game_profiles (
                  app_id, profile_embedding, top_keywords, mood_tags,
                  recent_review_count, positive_ratio_1y, median_playtime_1y, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id) DO UPDATE SET
                  profile_embedding=excluded.profile_embedding,
                  recent_review_count=excluded.recent_review_count,
                  positive_ratio_1y=excluded.positive_ratio_1y,
                  median_playtime_1y=excluded.median_playtime_1y,
                  updated_at=excluded.updated_at
                """,
                (
                    app_id,
                    _serialize_vector(profile),
                    json.dumps([], ensure_ascii=False),
                    json.dumps([], ensure_ascii=False),
                    int(recent_review_count),
                    float(positive_ratio),
                    float(median_playtime),
                    now.isoformat(),
                ),
            )
            profile_count += 1
        conn.commit()

    return {"profile_count": profile_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run review embedding in short commit-safe batches.")
    parser.add_argument("--db", default="data/recommender/steam_mvp.db")
    parser.add_argument("--model", default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
    parser.add_argument("--select-batch", type=int, default=2500)
    parser.add_argument("--encode-batch", type=int, default=128)
    parser.add_argument("--max-loops", type=int, default=4)
    parser.add_argument("--finalize", action="store_true", help="Also rebuild profiles and sync chroma")
    parser.add_argument("--chroma-path", default="data/recommender/chroma_v2")
    parser.add_argument("--chroma-collection", default="steam_game_profiles_v2")
    args = parser.parse_args()

    db_path = Path(args.db)
    init_db(db_path)

    res = run_embedding_batches(
        db_path=db_path,
        model_name=args.model,
        select_batch=max(100, int(args.select_batch)),
        encode_batch=max(16, int(args.encode_batch)),
        max_loops=max(1, int(args.max_loops)),
    )
    print("embedding_batches=", json.dumps(res, ensure_ascii=False))

    if args.finalize:
        profile_res = rebuild_profiles(db_path)
        print("profiles=", json.dumps(profile_res, ensure_ascii=False))
        chroma_res = sync_game_profiles_to_chroma(
            db_path=db_path,
            chroma_path=args.chroma_path,
            collection_name=args.chroma_collection,
        )
        print("chroma=", json.dumps(chroma_res, ensure_ascii=False))


if __name__ == "__main__":
    main()
