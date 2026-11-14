"""Invariant checks for experimental D, without model or database."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models import DocumentPage
from src.chunking import structure_chunks


def unit(page, text, section="one"):
    return DocumentPage("test", "local", page, text,
                        {"unit_id": f"u{page}", "section": section})


text = "First complete sentence. " + "Second complete sentence. " * 35
chunks = structure_chunks([unit(1, text)], target=100, hard_limit=200)
coverage = set()
for chunk in chunks:
    start, end = chunk.metadata["start_char"], chunk.metadata["end_char"]
    assert chunk.text == text[start:end]
    assert len(chunk.text) <= 200
    coverage.update(range(start, end))
assert all(i in coverage or ch.isspace() for i, ch in enumerate(text))
assert not any(c.metadata["forced_split"] for c in chunks)

heading = "\u0110i\u1ec1u 1. Scope"
units = [unit(1, heading + "\n1. A complete rule."),
         unit(2, "A continued provision."), unit(3, "Another section.", "two")]
chunks = structure_chunks(units)
assert all(c.metadata["heading_context"] == heading for c in chunks if c.page in (1, 2))
assert all(not c.metadata["heading_context"] for c in chunks if c.page == 3)
# Do not detach clause labels as sentence endings.
labelled = "1. " + "A" * 100 + ". " + "B" * 100 + "."
chunks = structure_chunks([unit(4, labelled)], target=120, hard_limit=200)
assert chunks[0].text.startswith("1. A")
assert all(c.text.strip() != "1." for c in chunks)

long = "word " * 400
chunks = structure_chunks([unit(5, long)], target=100, hard_limit=200)
assert all(len(c.text) <= 200 for c in chunks)
assert all(c.metadata["end_char"] == len(long)
           or long[c.metadata["end_char"]].isspace() for c in chunks[:-1])
print("D checks: coverage, offsets, sentence/clause boundaries, context isolation, long-block splitting OK")
