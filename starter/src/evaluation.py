"""Evaluate source/page and complete evidence containment."""

from typing import Any


def normalize_for_match(text: str) -> str:
    return " ".join(text.split())


def evaluate_query(
    question: dict[str, Any],
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    evidence = normalize_for_match(question["evidence_quote"])

    if not evidence:
        raise ValueError("Gold evidence must not be empty.")

    ranked_hits = []

    for rank, hit in enumerate(hits[:3], start=1):
        source_matches = (
            hit["document_id"] == question["gold_source_id"]
        )
        page_matches = hit["page"] == question["gold_page"]
        evidence_matches = (
            evidence in normalize_for_match(hit["text"])
        )

        is_hit = (
            source_matches
            and page_matches
            and evidence_matches
        )

        ranked_hits.append({
            **hit,
            "rank": rank,
            "source_matches": source_matches,
            "page_matches": page_matches,
            "evidence_matches": evidence_matches,
            "is_hit": is_hit,
        })

    return {
        "question_id": question["id"],
        "split": question["split"],
        "question": question["question"],
        "expected_answer": question["expected_answer"],
        "gold_source_id": question["gold_source_id"],
        "gold_page": question["gold_page"],
        "evidence_quote": question["evidence_quote"],
        "requested_filter": question.get("filter"),
        "hit_at_1": bool(
            ranked_hits and ranked_hits[0]["is_hit"]
        ),
        "evidence_hit_at_3": any(
            hit["is_hit"] for hit in ranked_hits
        ),
        "hits": ranked_hits,
        "evaluation_method": "source_page_and_evidence_containment",
    }

def summarize(
    traces: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Aggregate retrieval metrics by strategy and split."""
    groups = {}
    seen = set()

    for trace in traces:
        strategy = trace["strategy"]
        split = trace["split"]
        question_id = trace["question_id"]

        identity = (strategy, split, question_id)
        if identity in seen:
            raise ValueError(f"Duplicate trace: {identity}")
        seen.add(identity)

        groups.setdefault((strategy, split), []).append(trace)

    summaries = []

    for (strategy, split), rows in sorted(groups.items()):
        total = len(rows)
        hit1_count = sum(bool(row["hit_at_1"]) for row in rows)
        hit3_count = sum(
            bool(row["evidence_hit_at_3"]) for row in rows
        )

        summaries.append({
            "strategy": strategy,
            "split": split,
            "question_count": total,
            "hit1_count": hit1_count,
            "hit1_fraction": f"{hit1_count}/{total}",
            "hit1_rate": hit1_count / total,
            "hit3_count": hit3_count,
            "hit3_fraction": f"{hit3_count}/{total}",
            "hit3_rate": hit3_count / total,
        })

    return summaries