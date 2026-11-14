"""Local D experiment: dev only, separate table and artifacts; no baseline edits."""

import csv
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

STARTER = Path(__file__).resolve().parents[1]
ROOT = STARTER.parent
sys.path.insert(0, str(STARTER))

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Jsonb
from src.embeddings import MyEmbedder
from src.evaluation import evaluate_query, summarize
from src.models import DocumentPage
from src.chunking import STRUCTURE_VERSION as VERSION, embedding_text, structure_chunks


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def main(output_dir=None):
    output = Path(output_dir) if output_dir is not None else ROOT / "results/improvement_D"
    output.mkdir(parents=True, exist_ok=True)
    load_dotenv(STARTER / ".env")
    config = json.loads((ROOT / "artifacts/strategies.json").read_text(encoding="utf-8-sig"))
    shared = config["shared"]
    settings = config["strategies"]["D"]
    if settings["version"] != VERSION:
        raise ValueError("D config/code version mismatch")
    if settings["database_table"] != "experimental_chunks_d" or settings["evaluation_split"] != "dev":
        raise ValueError("D is restricted to its separate table and dev split")
    target, hard_limit = settings["target_chars"], settings["hard_limit_chars"]
    if not settings["heading_prefix_in_embedding"] or settings["apply_question_filter"]:
        raise ValueError("D v2 uses heading context and no filter")
    source_path = ROOT / shared["source_units"]
    if not source_path.exists():
        source_path = ROOT / "results/reproduced/sections.jsonl"
    rows = read_jsonl(source_path)
    units = [DocumentPage(document_id=r["document_id"], source=r["source"], page=r["page"],
             text=r["text"], metadata={**r["metadata"], "unit_id": r["unit_id"]}) for r in rows]
    chunks = structure_chunks(units, target=target, hard_limit=hard_limit)
    print("D source chunks:", len(chunks), flush=True)
    unit_map = {u.metadata["unit_id"]: u for u in units}
    coverage = {key: bytearray(len(u.text)) for key, u in unit_map.items()}
    for c in chunks:
        u = unit_map[c.metadata["unit_id"]]
        start, end = c.metadata["start_char"], c.metadata["end_char"]
        assert c.text == u.text[start:end] and len(c.text) <= hard_limit
        coverage[u.metadata["unit_id"]][start:end] = b"\x01" * (end - start)
    for key, u in unit_map.items():
        assert all(coverage[key][i] or ch.isspace() for i, ch in enumerate(u.text))
    assert len({c.chunk_id for c in chunks}) == len(chunks)
    # Fail before loading/embedding if the local database is unavailable.
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as conn:
        baseline_before = conn.execute(
            "SELECT strategy,count(*) FROM ingestion_chunks GROUP BY strategy ORDER BY strategy"
        ).fetchall()
    model = MyEmbedder(shared["embedding_model"], shared["embedding_revision"])
    inputs = [embedding_text(c) for c in chunks]
    token_lengths = [len(ids) for ids in model.model.tokenizer(
        ["passage: " + t for t in inputs], truncation=False, padding=False)["input_ids"]]
    start = time.perf_counter()
    vectors = model.embed_documents(inputs)
    embedding_seconds = time.perf_counter() - start
    print("D embeddings complete:", len(vectors), flush=True)
    # Dedicated table: A/B/C rows cannot be replaced by this experiment.
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL lock_timeout = '10s'")
            cur.execute("SET LOCAL statement_timeout = '60s'")
            cur.execute("""CREATE TABLE IF NOT EXISTS experimental_chunks_d (
                chunk_id TEXT PRIMARY KEY, document_id TEXT NOT NULL,
                source TEXT NOT NULL, page INTEGER NOT NULL, text TEXT NOT NULL,
                metadata JSONB NOT NULL, embedding vector(384) NOT NULL)""")
            cur.execute("LOCK TABLE experimental_chunks_d IN EXCLUSIVE MODE")
            cur.execute("DELETE FROM experimental_chunks_d WHERE document_id = %s", (shared["source_id"],))
            cur.executemany("""INSERT INTO experimental_chunks_d VALUES
                (%s,%s,%s,%s,%s,%s,%s::vector)""", [
                (c.chunk_id,c.document_id,c.source,c.page,c.text,Jsonb(c.metadata),json.dumps(v))
                for c,v in zip(chunks,vectors)])
    questions = [q for q in read_jsonl(ROOT / shared["benchmark"]) if q["split"] == "dev"]
    assert len(questions) == 15
    traces = []
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout = '60s'")
            for q in questions:
                vector = model.embed_query(q["question"])
                cur.execute("""SELECT chunk_id,document_id,source,page,text,metadata,
                    embedding <=> %s::vector AS distance FROM experimental_chunks_d
                    ORDER BY distance,chunk_id LIMIT 3""", (json.dumps(vector),))
                hits = [dict(chunk_id=r[0],document_id=r[1],source=r[2],page=r[3],
                        text=r[4],metadata=r[5],distance=float(r[6]),score=1-float(r[6]))
                        for r in cur.fetchall()]
                result = evaluate_query(q,hits)
                result.update(strategy="D",applied_filter={})
                traces.append(result)
                print("Completed:",q["id"],flush=True)
            cur.execute("SELECT strategy,count(*) FROM ingestion_chunks GROUP BY strategy ORDER BY strategy")
            baseline_after = cur.fetchall()
            assert baseline_before == baseline_after, "Baseline row counts changed"
    for filename, records in [("chunks_D.jsonl",map(asdict,chunks)),("dev_traces.jsonl",traces)]:
        with (output / filename).open("w",encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r,ensure_ascii=False)+"\n")
    metrics = summarize(traces)
    with (output / "dev_metrics.csv").open("w",encoding="utf-8",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]));writer.writeheader();writer.writerows(metrics)
    run = dict(checked_at_utc=datetime.now(timezone.utc).isoformat(),strategy="D",
        version=VERSION,target_chars=target,hard_limit_chars=hard_limit,overlap=0,
        heading_prefix_in_embedding=True,filter=False,chunk_count=len(chunks),
        max_chunk_chars=max(len(c.text) for c in chunks),max_tokens=max(token_lengths),
        total_source_chars=sum(len(c.text) for c in chunks),
        total_embedding_chars=sum(len(t) for t in inputs),embedding_seconds=embedding_seconds,
        model=shared["embedding_model"],revision=shared["embedding_revision"],
        scope="dev-only exploratory experiment after original test was seen; no independent test claim",
        comparison_limit="D changes boundaries, heading context and soft size limit together; not an ablation",
        baseline_row_counts_unchanged=True, baseline_row_counts=baseline_after,
        paid_api_cost=0)
    (output/"run.json").write_text(json.dumps(run,indent=2)+"\n",encoding="utf-8")
    # Publish only aggregate/provenance records, never source excerpts.
    (ROOT / "results/improvement_D_run.json").write_text(
        json.dumps(run, indent=2) + "\n", encoding="utf-8")
    summary_rows = []
    baseline_metrics = ROOT / "results/dev_metrics.csv"
    if baseline_metrics.exists():
        with baseline_metrics.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                summary_rows.append(dict(strategy=row["strategy"], split="dev",
                    hit1=row["hit1_fraction"], hit3=row["hit3_fraction"],
                    note="Recorded baseline, unchanged"))
    summary_rows.append(dict(strategy="D", split="dev",
        hit1=metrics[0]["hit1_fraction"], hit3=metrics[0]["hit3_fraction"],
        note=f"Exploratory {VERSION}; soft limit {target}, hard limit {hard_limit}, heading context"))
    with (ROOT / "results/improvement_D_summary.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0]))
        writer.writeheader()
        writer.writerows(summary_rows)
    print(json.dumps(run,indent=2));print(metrics)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        output = ROOT / "results/improvement_D"
        output.mkdir(parents=True, exist_ok=True)
        with (output / "errors.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(dict(at_utc=datetime.now(timezone.utc).isoformat(),
                error=type(exc).__name__,message=str(exc)), ensure_ascii=False)+"\n")
        raise
