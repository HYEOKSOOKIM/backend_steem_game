from __future__ import annotations

import argparse
import sys

from sentence_transformers import SentenceTransformer


def main() -> int:
    parser = argparse.ArgumentParser(description="Preload embedding model into local cache.")
    parser.add_argument(
        "--model",
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        help="Hugging Face model id to cache locally",
    )
    parser.add_argument(
        "--local-files-only",
        action="store_true",
        help="Load only from existing local cache (no download)",
    )
    args = parser.parse_args()

    print(f"[preload] loading model: {args.model}")
    model = SentenceTransformer(args.model, local_files_only=args.local_files_only)
    _ = model.encode(
        ["warmup"],
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    print("[preload] done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

