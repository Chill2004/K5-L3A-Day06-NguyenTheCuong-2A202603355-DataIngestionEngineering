"""Persistent chunk storage using PostgreSQL and pgvector."""

import psycopg
from psycopg import sql
import json
import math

from psycopg.types.json import Jsonb
from .models import Chunk

class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int) -> None:
        if not database_url:
            raise ValueError("database_url is required.")

        if dimensions != 384:
            raise ValueError("This experiment requires 384 dimensions.")

        self.database_url = database_url
        self.dimensions = dimensions

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "CREATE EXTENSION IF NOT EXISTS vector"
                )

                cursor.execute(
                    sql.SQL("""
                        CREATE TABLE IF NOT EXISTS ingestion_chunks (
                            strategy TEXT NOT NULL,
                            chunk_id TEXT NOT NULL,
                            document_id TEXT NOT NULL,
                            source TEXT NOT NULL,
                            page INTEGER NOT NULL CHECK (page >= 1),
                            text TEXT NOT NULL CHECK (length(text) > 0),
                            metadata JSONB NOT NULL,
                            embedding vector({dimensions}) NOT NULL,
                            PRIMARY KEY (strategy, chunk_id)
                        )
                    """).format(
                        dimensions=sql.Literal(self.dimensions)
                    )
                )

                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS
                    ingestion_chunks_strategy_idx
                    ON ingestion_chunks (strategy)
                """)

                cursor.execute("""
                    SELECT format_type(atttypid, atttypmod)
                    FROM pg_attribute
                    WHERE attrelid = 'ingestion_chunks'::regclass
                      AND attname = 'embedding'
                      AND NOT attisdropped
                """)
                actual_type = cursor.fetchone()[0]

                if actual_type != f"vector({self.dimensions})":
                    raise ValueError(
                        f"Unexpected embedding column: {actual_type}"
                    )
    def upsert(
        self,
        strategy: str,
        chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> None:
        """Replace the selected documents' chunks atomically."""
        if strategy not in {"A", "B"}:
            raise ValueError("Store A/B only; C reuses B.")

        if not chunks or len(chunks) != len(vectors):
            raise ValueError("Chunks/vectors must be non-empty and aligned.")

        ids = [chunk.chunk_id for chunk in chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate chunk IDs in input.")

        rows = []

        for chunk, vector in zip(chunks, vectors):
            if len(vector) != self.dimensions:
                raise ValueError("Incorrect vector dimensions.")

            if not all(math.isfinite(value) for value in vector):
                raise ValueError("Vector contains non-finite values.")

            if not any(value != 0 for value in vector):
                raise ValueError("Zero vector cannot use cosine search.")

            if not chunk.text.strip():
                raise ValueError("Empty chunk text.")

            if not chunk.metadata.get("section"):
                raise ValueError("Missing section metadata.")

            rows.append((
                strategy,
                chunk.chunk_id,
                chunk.document_id,
                chunk.source,
                chunk.page,
                chunk.text,
                Jsonb(chunk.metadata),
                json.dumps(vector, allow_nan=False),
            ))

        document_ids = sorted({
            chunk.document_id for chunk in chunks
        })

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                # Lock per strategy while replacing a complete document set.
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"day6_ingest_{strategy}",),
                )

                cursor.execute(
                    """
                    DELETE FROM ingestion_chunks
                    WHERE strategy = %s
                      AND document_id = ANY(%s)
                    """,
                    (strategy, document_ids),
                )

                cursor.executemany(
                    """
                    INSERT INTO ingestion_chunks (
                        strategy, chunk_id, document_id, source,
                        page, text, metadata, embedding
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector)
                    """,
                    rows,
                )
    def search(
        self,
        strategy: str,
        query_vector: list[float],
        top_k: int = 3,
        filters: dict | None = None,
    ) -> list[dict]:
        """Exact cosine search; C reuses B's stored vectors."""
        if strategy not in {"A", "B", "C"}:
            raise ValueError("Unknown strategy.")

        if top_k <= 0:
            raise ValueError("top_k must be positive.")

        if len(query_vector) != self.dimensions:
            raise ValueError("Incorrect query vector dimensions.")

        if not all(math.isfinite(value) for value in query_vector):
            raise ValueError("Query contains non-finite values.")

        if not any(value != 0 for value in query_vector):
            raise ValueError("Query vector cannot be zero.")

        filters = {} if filters is None else filters
        if not isinstance(filters, dict):
            raise ValueError("filters must be a dictionary or None.")

        if set(filters) - {"section"}:
            raise ValueError("Only section filtering is supported.")

        if any(
            not isinstance(value, str) or not value.strip()
            for value in filters.values()
        ):
            raise ValueError("Filter values must be non-empty strings.")

        stored_strategy = "B" if strategy == "C" else strategy
        applied_filters = filters if strategy == "C" else {}

        vector_text = json.dumps(query_vector, allow_nan=False)

        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT chunk_id, document_id, source, page,
                           text, metadata,
                           embedding <=> %s::vector AS distance
                    FROM ingestion_chunks
                    WHERE strategy = %s
                      AND metadata @> %s::jsonb
                    ORDER BY distance ASC, chunk_id ASC
                    LIMIT %s
                    """,
                    (
                        vector_text,
                        stored_strategy,
                        Jsonb(applied_filters),
                        top_k,
                    ),
                )
                rows = cursor.fetchall()

        return [
            {
                "chunk_id": row[0],
                "document_id": row[1],
                "source": row[2],
                "page": row[3],
                "text": row[4],
                "metadata": row[5],
                "distance": float(row[6]),
                "score": 1.0 - float(row[6]),
            }
            for row in rows
        ]