"""Run retrieval; preserve the recorded experiment by default."""

import csv
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import argparse

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
sys.path.insert(0, str(STARTER))

from dotenv import load_dotenv

from src.embeddings import MyEmbedder
from src.evaluation import evaluate_query, summarize
from src.store import PgVectorStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--split",
        choices=["dev", "test"],
        default="dev",
    )
    parser.add_argument(
        "--output-dir", default="results/reproduced/benchmark",
        help="Output directory relative to repository root; original traces stay unchanged",
    )
    args = parser.parse_args()
    split = args.split

    if split == "test":
        decision = ROOT / "artifacts/selection_decision.md"
        if not decision.is_file() or not decision.read_text(
            encoding="utf-8-sig"
        ).strip():
            raise ValueError("Save the selection decision before test.")
    load_dotenv(STARTER / ".env")

    config = json.loads(
        (ROOT / "artifacts/strategies.json").read_text(
            encoding="utf-8-sig"
        )
    )
    shared = config["shared"]

    questions = [
        json.loads(line)
        for line in (ROOT / shared["benchmark"])
        .read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    questions = [q for q in questions if q["split"] == split]

    expected_count = 15 if split == "dev" else 5

    if len(questions) != expected_count:
        raise ValueError(
            f"Expected {expected_count} questions for {split}."
        )

    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError(f"Duplicate {split} question IDs.")

    embedder = MyEmbedder(
        shared["embedding_model"],
        revision=shared["embedding_revision"],
    )
    store = PgVectorStore(
        os.environ["DATABASE_URL"],
        shared["embedding_dimensions"],
    )

    started_at = datetime.now(timezone.utc).isoformat()
    traces = []

    for question in questions:
        start = time.perf_counter()
        query_vector = embedder.embed_query(question["question"])
        embedding_seconds = time.perf_counter() - start

        for strategy in ["A", "B", "C"]:
            applied_filter = (
                question.get("filter") or {}
                if strategy == "C"
                else {}
            )

            start = time.perf_counter()
            hits = store.search(
                strategy,
                query_vector,
                top_k=shared["top_k"],
                filters=applied_filter,
            )
            search_seconds = time.perf_counter() - start

            result = evaluate_query(question, hits)
            result.update({
                "strategy": strategy,
                "stored_strategy": "B" if strategy == "C" else strategy,
                "applied_filter": applied_filter,
                "query_embedding_seconds": embedding_seconds,
                "search_seconds": search_seconds,
            })
            traces.append(result)

        print("Completed:", question["id"], flush=True)

    summaries = summarize(traces)
    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    with (output_dir / f"{split}_traces.jsonl").open(
        "w", encoding="utf-8"
    ) as output:
        for trace in traces:
            output.write(json.dumps(trace, ensure_ascii=False) + "\n")

    with (output_dir / f"{split}_metrics.csv").open(
        "w", encoding="utf-8", newline=""
    ) as output:
        writer = csv.DictWriter(
            output, fieldnames=list(summaries[0])
        )
        writer.writeheader()
        writer.writerows(summaries)

    (output_dir / f"{split}_run.json").write_text(
        json.dumps({
            "started_at_utc": started_at,
            "split": split,
            "question_ids": [q["id"] for q in questions],
            "model": shared["embedding_model"],
            "revision": shared["embedding_revision"],
            "trace_count": len(traces),
            "metric": "cosine",
            "search_mode": "exact",
            "top_k": shared["top_k"],
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    for row in summaries:
        print(
            row["strategy"],
            "| Hit@1:", row["hit1_fraction"],
            "| Evidence Hit@3:", row["hit3_fraction"],
        )

    print(f"Saved {split} traces, metrics, and run metadata.")


if __name__ == "__main__":
    main()
