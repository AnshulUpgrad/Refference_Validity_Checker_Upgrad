import re
from typing import List, Dict, Any

from docx import Document

from app.extractor.pdf_parser import split_references


def extract_references_from_docx(docx_path: str) -> List[Dict[str, Any]]:
    """
    Extracts raw citations/references from the bibliography section of a Word document.

    Returns a list of dicts:
    [
        {"reference_id": 1, "raw_reference": "Smith J. Title..."},
        ...
    ]
    """
    doc = Document(docx_path)

    # Collect all paragraphs with their text and style info
    paragraphs = [(p.text.strip(), p.style.name if p.style else "") for p in doc.paragraphs]

    ref_headers = re.compile(
        r'^(?:\d+\.?\s*)?(?:references|bibliography|works\s+cited|literature\s+cited|references\s+and\s+notes)\s*$',
        re.IGNORECASE,
    )

    # 1. Find the references section start index
    ref_start = _find_references_start(paragraphs, ref_headers)

    if ref_start is None:
        # Fallback: use roughly the last 15% of paragraphs
        ref_start = max(0, len(paragraphs) - max(1, len(paragraphs) // 7))

    # 2. Gather all text after the heading
    ref_paragraphs = [text for text, _ in paragraphs[ref_start + 1:] if text]

    if not ref_paragraphs:
        return []

    # 3. Reuse the shared splitting logic from pdf_parser
    full_references_text = "\n".join(ref_paragraphs)
    return split_references(full_references_text)


def _find_references_start(
    paragraphs: List[tuple],
    header_pattern: re.Pattern,
) -> int | None:
    """
    Scan paragraphs backwards to find the references section heading.
    Prefers headings identified by Word style names (e.g. 'Heading 1'),
    but falls back to plain-text matching.
    """
    # Pass 1: look for a heading-styled paragraph whose text matches
    for i in range(len(paragraphs) - 1, -1, -1):
        text, style = paragraphs[i]
        if header_pattern.match(text) and "heading" in style.lower():
            return i

    # Pass 2: accept any paragraph whose text matches (no style requirement)
    for i in range(len(paragraphs) - 1, -1, -1):
        text, _ = paragraphs[i]
        if header_pattern.match(text):
            return i

    return None
