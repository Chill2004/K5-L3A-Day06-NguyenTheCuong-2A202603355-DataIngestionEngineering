"""Read PDF pages, normalize text, and log extraction problems."""

import json
import unicodedata
from pathlib import Path
import re
from pypdf import PdfReader

from .models import DocumentPage


def normalize_text(text: str) -> str:
    """Normalize spacing and remove the handbook's repeated page header."""
    text = unicodedata.normalize("NFC", text)

    lines = [
        " ".join(line.split())
        for line in text.splitlines()
    ]

    # Match only complete header/footer lines, not body text.
    title = r"S\u1ed5 tay sinh vi\u00ean 2024"
    header_pattern = rf"(?:\d+\s+{title}|{title}\s+\d+)"

    lines = [
        line for line in lines
        if not re.fullmatch(header_pattern, line)
    ]

    return "\n".join(lines).strip()


def load_pdf(
    path: Path,
    document_id: str,
    source: str,
    *,
    included_pages: list[int] | None = None,
    error_log_path: Path | None = None,
) -> list[DocumentPage]:
    """Extract selected physical PDF pages, numbered from 1."""
    path = Path(path)

    try:
        reader = PdfReader(path)
    except Exception as exc:
        _write_error(
            error_log_path,
            {
                "document_id": document_id,
                "source": source,
                "page": None,
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )
        raise

    page_numbers = (
        list(range(1, len(reader.pages) + 1))
        if included_pages is None
        else included_pages
    )

    if len(page_numbers) != len(set(page_numbers)):
        raise ValueError("included_pages contains duplicate page numbers.")

    if any(
        not isinstance(number, int)
        or isinstance(number, bool)
        or not 1 <= number <= len(reader.pages)
        for number in page_numbers
    ):
        raise ValueError("included_pages contains an invalid page number.")

    pages = []

    for number in page_numbers:
        try:
            raw_text = reader.pages[number - 1].extract_text() or ""
            text = normalize_text(raw_text)
        except Exception as exc:
            _write_error(
                error_log_path,
                {
                    "document_id": document_id,
                    "source": source,
                    "page": number,
                    "error": type(exc).__name__,
                    "message": str(exc),
                },
            )
            raise RuntimeError(
                f"Failed to extract PDF page {number}."
            ) from exc

        if not text:
            _write_error(
                error_log_path,
                {
                    "document_id": document_id,
                    "source": source,
                    "page": number,
                    "error": "EmptyText",
                    "message": "No text extracted; inspect page or use OCR.",
                },
            )
            continue

        pages.append(
            DocumentPage(
                document_id=document_id,
                source=source,
                page=number,
                text=text,
            )
        )

    return pages


def _write_error(path: Path | None, record: dict) -> None:
    """Append an extraction problem as one JSONL record."""
    if path is None:
        return

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")

def split_handbook_sections(
    pages: list[DocumentPage],
) -> list[DocumentPage]:
    """Assign verified sections for the selected OU handbook pages."""
    units = []

    def add(page, text, section, suffix):
        text = text.strip()
        if not text:
            raise ValueError(f"Empty section on page {page.page}.")

        units.append(
            DocumentPage(
                document_id=page.document_id,
                source=page.source,
                page=page.page,
                text=text,
                metadata={
                    **page.metadata,
                    "section": section,
                    "unit_id": (
                        f"{page.document_id}-p{page.page}-{suffix}"
                    ),
                },
            )
        )

    for page in pages:
        if 39 <= page.page <= 45:
            add(page, page.text, "cong_tac_sinh_vien", "1")

        elif 46 <= page.page <= 67:
            add(page, page.text, "quy_che_dao_tao", "1")

        elif page.page == 68:
            pattern = r"(?m)^[ \t]*2\.\s*QUY\s+\u0110\u1ecaNH\b"
            matches = list(re.finditer(pattern, page.text))

            if len(matches) != 1:
                raise ValueError(
                    "Expected exactly one section boundary on page 68."
                )

            position = matches[0].start()
            add(
                page,
                page.text[:position],
                "quy_che_dao_tao",
                "1",
            )
            add(
                page,
                page.text[position:],
                "ngoai_ngu_khong_chuyen",
                "2",
            )

        elif 69 <= page.page <= 77:
            add(page, page.text, "ngoai_ngu_khong_chuyen", "1")

        else:
            raise ValueError(
                f"Page outside selected corpus: {page.page}"
            )

    return units