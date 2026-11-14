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

STRUCTURE_VERSION = "structure-sentence-v2"
ARTICLE = re.compile(r"^\s*Điều\s+\d+\.")
BOUNDARY = re.compile(r"(?m)^\s*(?:Điều\s+\d+\.|\d+[.)]\s+|[a-zđ][.)]\s+|[-+]\s+)")


def structure_chunks(units: list[DocumentPage], target=500, hard_limit=900):
    """Retain exact source spans; heading context is metadata, not fabricated text.

    Target is soft: a complete sentence up to hard_limit remains intact. Beyond
    that split only at whitespace if possible. Never cross source page/section.
    """
    if not 0 < target <= hard_limit:
        raise ValueError("Require 0 < target <= hard_limit")
    chunks = []
    contexts = {}
    for unit in units:
        section = unit.metadata["section"]
        heading = contexts.get(section, "")
        # Blank lines and numbered clauses/bullets define candidate blocks.
        boundaries = {0, len(unit.text)}
        boundaries.update(m.start() for m in BOUNDARY.finditer(unit.text))
        boundaries.update(m.end() for m in re.finditer(r"\n[ \t]*\n", unit.text))
        bounds = sorted(boundaries)
        atoms = []
        for left, right in zip(bounds, bounds[1:]):
            while left < right and unit.text[left].isspace():
                left += 1
            while right > left and unit.text[right - 1].isspace():
                right -= 1
            if left == right:
                continue
            block = unit.text[left:right]
            first_line = block.splitlines()[0].strip()
            if ARTICLE.match(first_line):
                heading = first_line
            # Split long blocks at sentence endings; decimal numbers stay intact.
            cuts = [left]
            for match in re.finditer(r"(?<=[.!?;])\s+(?=[A-ZÀ-ỸĐ])", block):
                preceding_line = block[:match.start()].splitlines()[-1].strip()
                # A numbered clause/article label is not a complete sentence.
                if re.fullmatch(r"(?:Điều\s+)?\d+\.", preceding_line):
                    continue
                cuts.append(left + match.end())
            cuts.append(right)
            for start, end in zip(cuts, cuts[1:]):
                while end - start > hard_limit:
                    stop = start + hard_limit
                    whitespace = list(re.finditer(r"\s+", unit.text[start:stop]))
                    if whitespace and whitespace[-1].start() > 0:
                        stop = start + whitespace[-1].start()
                    atoms.append((start, stop, heading, True))
                    start = stop
                if start < end:
                    atoms.append((start, end, heading, False))
        contexts[section] = heading
        spans = []
        pending = None
        for start, end, title, fallback in atoms:
            if pending and pending[2] == title and end - pending[0] <= target:
                pending = (pending[0], end, title, pending[3] or fallback)
            else:
                if pending:
                    spans.append(pending)
                pending = (start, end, title, fallback)
        if pending:
            spans.append(pending)
        for start, end, title, fallback in spans:
            text = unit.text[start:end]
            if not text.strip():
                continue
            identity = f"{STRUCTURE_VERSION}|{unit.metadata['unit_id']}|{target}|{hard_limit}|{start}|{end}|{title}|{text}"
            chunks.append(Chunk(
                chunk_id=hashlib.sha256(identity.encode("utf-8")).hexdigest(),
                document_id=unit.document_id, source=unit.source, page=unit.page,
                text=text, metadata={**unit.metadata, "chunking": STRUCTURE_VERSION,
                    "start_char": start, "end_char": end,
                    "heading_context": title, "target_chars": target,
                    "hard_limit_chars": hard_limit, "forced_split": fallback},
            ))
    return chunks


def embedding_text(chunk: Chunk) -> str:
    heading = chunk.metadata.get("heading_context", "")
    # Context affects embeddings only; evaluation uses original source text.
    return f"{heading}\n{chunk.text}" if heading and not chunk.text.lstrip().startswith(heading) else chunk.text
