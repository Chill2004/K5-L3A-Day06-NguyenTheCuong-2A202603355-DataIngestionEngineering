"""Split source units into traceable chunks."""
import re
import hashlib

from .models import Chunk, DocumentPage


def fixed_size(
    page: DocumentPage,
    size: int,
    overlap: int,
) -> list[Chunk]:
    """Split one source unit into overlapping character windows."""
    if size <= 0:
        raise ValueError("size must be positive.")

    if not 0 <= overlap < size:
        raise ValueError("overlap must satisfy 0 <= overlap < size.")

    if not page.text.strip():
        return []

    unit_id = page.metadata.get("unit_id")
    if not unit_id:
        raise ValueError("Source unit must have a stable unit_id.")

    chunks = []
    start = 0

    while start < len(page.text):
        end = min(start + size, len(page.text))
        text = page.text[start:end]

        if text.strip():
            identity = (
                f"{page.document_id}|{unit_id}|fixed|"
                f"{size}|{overlap}|{start}|{end}|{text}"
            )
            chunk_id = hashlib.sha256(
                identity.encode("utf-8")
            ).hexdigest()

            chunks.append(
                Chunk(
                    chunk_id=chunk_id,
                    document_id=page.document_id,
                    source=page.source,
                    page=page.page,
                    text=text,
                    metadata={
                        **page.metadata,
                        "chunking": "fixed",
                        "chunk_size": size,
                        "overlap": overlap,
                        "start_char": start,
                        "end_char": end,
                    },
                )
            )

        if end == len(page.text):
            break

        start += size - overlap

    return chunks

def by_paragraph(
    page: DocumentPage,
    max_size: int,
) -> list[Chunk]:
    """Group paragraphs; split oversized paragraphs into bounded windows."""
    if max_size <= 0:
        raise ValueError("max_size must be positive.")

    if not page.text.strip():
        return []

    unit_id = page.metadata.get("unit_id")
    if not unit_id:
        raise ValueError("Source unit must have a stable unit_id.")

    # Blank lines separate paragraphs. Single line breaks are retained.
    paragraphs = []
    for match in re.finditer(
        r"\S.*?(?=\n\s*\n|\Z)",
        page.text,
        flags=re.DOTALL,
    ):
        start, end = match.span()
        while end > start and page.text[end - 1].isspace():
            end -= 1
        if start < end:
            paragraphs.append((start, end))

    spans = []
    pending = None

    for start, end in paragraphs:
        if end - start > max_size:
            if pending is not None:
                spans.append(pending)
                pending = None

            length = end - start
            part_count = (length + max_size - 1) // max_size
            base_size, extra = divmod(length, part_count)

            position = start
            for index in range(part_count):
                part_size = base_size + (1 if index < extra else 0)
                next_position = position + part_size
                spans.append((position, next_position))
                position = next_position

            continue

        if pending is None:
            pending = (start, end)
        elif end - pending[0] <= max_size:
            pending = (pending[0], end)
        else:
            spans.append(pending)
            pending = (start, end)

    if pending is not None:
        spans.append(pending)

    chunks = []

    for start, end in spans:
        text = page.text[start:end]
        if not text.strip():
            continue

        identity = (
            f"{page.document_id}|{unit_id}|paragraph|"
            f"{max_size}|{start}|{end}|{text}"
        )
        chunk_id = hashlib.sha256(
            identity.encode("utf-8")
        ).hexdigest()

        chunks.append(
            Chunk(
                chunk_id=chunk_id,
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=text,
                metadata={
                    **page.metadata,
                    "chunking": "paragraph",
                    "max_size": max_size,
                    "overlap": 0,
                    "start_char": start,
                    "end_char": end,
                },
            )
        )

    return chunks
