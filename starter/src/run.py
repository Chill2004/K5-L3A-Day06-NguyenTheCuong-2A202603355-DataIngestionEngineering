"""Reproduce preparation, embedding and ingestion without overwriting original results."""

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path):
    return [json.loads(s) for s in path.read_text(encoding="utf-8-sig").splitlines()
            if s.strip()]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                    encoding="utf-8")


def prepare(output, config):
    from .ingestion import load_pdf, split_handbook_sections
    from .chunking import fixed_size, by_paragraph
    started = time.perf_counter()
    sources = read_json(ROOT / "data/manifest.json")["sources"]
    if len(sources) != 1 or sources[0]["source_id"] != config["shared"]["source_id"]:
        raise ValueError("Expected the verified single handbook source.")
    source = sources[0]
    pdf = ROOT / source["local_path"]
    pages = load_pdf(pdf, source["source_id"], source["source_path_or_url"],
                     included_pages=source["included_pages"],
                     error_log_path=output / "ingestion_errors.jsonl")
    if len(pages) < 30 or len(pages) != len(source["included_pages"]):
        raise ValueError("Missing/empty content pages.")
    units = split_handbook_sections(pages)
    questions = read_jsonl(ROOT / config["shared"]["benchmark"])
    if len({q["id"] for q in questions}) != len(questions):
        raise ValueError("Duplicate question IDs.")
    for split, minimum in [("dev", 15), ("test", 5)]:
        if sum(q["split"] == split for q in questions) < minimum:
            raise ValueError(f"Insufficient {split} questions.")
    filtered = [q for q in questions if q.get("filter")]
    if len(filtered) < 3 or not any(q["split"] == "test" for q in filtered):
        raise ValueError("Insufficient filter questions.")
    for q in questions:
        evidence = " ".join(q["evidence_quote"].split())
        candidates = [u for u in units if u.document_id == q["gold_source_id"]
                      and u.page == q["gold_page"] and all(
                          u.metadata.get(k) == v
                          for k, v in (q.get("filter") or {}).items())]
        if not evidence or not any(evidence in " ".join(u.text.split()) for u in candidates):
            raise ValueError(f"Evidence not found: {q['id']}")
    a, b = config["strategies"]["A"], config["strategies"]["B"]
    strategies = {
        "A": [c for u in units for c in fixed_size(u, a["chunk_size"], a["overlap"])],
        "B": [c for u in units for c in by_paragraph(u, b["max_size"])],
    }
    unit_map = {u.metadata["unit_id"]: u for u in units}
    for strategy, chunks in strategies.items():
        if not chunks or len({c.chunk_id for c in chunks}) != len(chunks):
            raise ValueError("Empty chunks or duplicate IDs.")
        covered = {key: bytearray(len(u.text)) for key, u in unit_map.items()}
        for c in chunks:
            u = unit_map[c.metadata["unit_id"]]
            start, end = c.metadata["start_char"], c.metadata["end_char"]
            if not (0 <= start < end <= len(u.text)) or c.text != u.text[start:end]:
                raise ValueError("Chunk offsets/text mismatch.")
            if c.page != u.page or c.metadata["section"] != u.metadata["section"]:
                raise ValueError("Chunk metadata mismatch.")
            covered[u.metadata["unit_id"]][start:end] = b"\x01" * (end - start)
        for key, u in unit_map.items():
            if any(not covered[key][i] and not ch.isspace() for i, ch in enumerate(u.text)):
                raise ValueError(f"Lost content: {strategy}/{key}")
    write_jsonl(output / "pages.jsonl", [dict(document_id=p.document_id,
        source=p.source, page=p.page, text=p.text, character_count=len(p.text)) for p in pages])
    write_jsonl(output / "sections.jsonl", [dict(document_id=u.document_id,
        source=u.source, page=u.page, unit_id=u.metadata["unit_id"], text=u.text,
        character_count=len(u.text), metadata={"section": u.metadata["section"]}) for u in units])
    for strategy, chunks in strategies.items():
        write_jsonl(output / f"chunks_{strategy}.jsonl", map(asdict, chunks))
        original = ROOT / "results" / f"chunks_{strategy}.jsonl"
        same = original.exists() and read_jsonl(original) == [asdict(c) for c in chunks]
        print(strategy, "chunks:", len(chunks), "| same as recorded:", same)
    write_json(output / "preparation_run.json", dict(
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        preparation_seconds=time.perf_counter() - started,
        page_count=len(pages), unit_count=len(units), evidence_checks=len(questions)))
    print("Preparation and evidence validation: OK")


def embed(output, config):
    from .embeddings import MyEmbedder
    shared = config["shared"]
    model = MyEmbedder(shared["embedding_model"], shared["embedding_revision"])
    runs = []
    for strategy in ["A", "B"]:
        path = output / f"chunks_{strategy}.jsonl"
        chunks = read_jsonl(path)
        start = time.perf_counter()
        vectors = model.embed_documents([c["text"] for c in chunks])
        elapsed = time.perf_counter() - start
        write_jsonl(output / f"vectors_{strategy}.jsonl", [
            dict(chunk_id=c["chunk_id"], embedding=v) for c, v in zip(chunks, vectors)])
        runs.append(dict(strategy=strategy, chunk_count=len(chunks),
            input_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            model=shared["embedding_model"], revision=shared["embedding_revision"],
            dimensions=model.dimensions, device="cpu", embedding_seconds=elapsed,
            paid_api_cost=0, cost_note="Local; electricity/hardware not estimated"))
        print(strategy, "vectors:", len(vectors))
    write_json(output / "embedding_runs.json", runs)


def ingest(output, config):
    from dotenv import load_dotenv
    import psycopg
    from .models import Chunk
    from .store import PgVectorStore
    load_dotenv(ROOT / "starter/.env")
    store = PgVectorStore(os.environ["DATABASE_URL"], config["shared"]["embedding_dimensions"])
    runs = {r["strategy"]: r for r in read_json(output / "embedding_runs.json")}
    prepared = {}
    for strategy in ["A", "B"]:
        path = output / f"chunks_{strategy}.jsonl"
        run = runs[strategy]
        if hashlib.sha256(path.read_bytes()).hexdigest() != run["input_sha256"]:
            raise ValueError("Chunks changed after embedding.")
        if (run["model"], run["revision"]) != (
            config["shared"]["embedding_model"], config["shared"]["embedding_revision"]):
            raise ValueError("Model/revision mismatch.")
        chunks = [Chunk(**r) for r in read_jsonl(path)]
        rows = read_jsonl(output / f"vectors_{strategy}.jsonl")
        vectors = {r["chunk_id"]: r["embedding"] for r in rows}
        if len(vectors) != len(rows) or set(vectors) != {c.chunk_id for c in chunks}:
            raise ValueError("Chunk/vector IDs mismatch.")
        prepared[strategy] = (chunks, [vectors[c.chunk_id] for c in chunks])
    store.create_schema()
    timings = []
    for strategy, (chunks, vectors) in prepared.items():
        start = time.perf_counter()
        store.upsert(strategy, chunks, vectors)
        timings.append(dict(strategy=strategy, chunk_count=len(chunks),
                            database_write_seconds=time.perf_counter() - start))
    with psycopg.connect(store.database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT strategy, count(*) FROM ingestion_chunks "
                           "GROUP BY strategy ORDER BY strategy")
            print("Database counts:", cursor.fetchall())
    write_json(output / "database_ingest_runs.json", timings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["prepare", "embed", "ingest", "all"], default="prepare")
    parser.add_argument("--output-dir", default="results/reproduced",
                        help="Output path relative to repository root")
    args = parser.parse_args()
    output = (ROOT / args.output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    config = read_json(ROOT / "artifacts/strategies.json")
    try:
        for stage, action in [("prepare", prepare), ("embed", embed), ("ingest", ingest)]:
            if args.stage in (stage, "all"):
                action(output, config)
    except Exception as exc:
        with (output / "pipeline_errors.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(dict(stage=args.stage, error=type(exc).__name__,
                                    message=str(exc)), ensure_ascii=False) + "\n")
        raise


if __name__ == "__main__":
    main()
