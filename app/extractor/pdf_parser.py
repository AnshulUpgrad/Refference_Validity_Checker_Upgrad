import fitz  # PyMuPDF
import re
from typing import List, Dict, Any

def extract_references_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts raw citations/references from the bibliography section of a research paper PDF.
    
    Returns a list of dicts:
    [
        {"reference_id": 1, "raw_reference": "Smith J. Title..."},
        ...
    ]
    """
    doc = fitz.open(pdf_path)
    full_text = ""
    page_texts = []
    
    # Extract text from all pages
    for page in doc:
        page_texts.append(page.get_text())
    
    # 1. Locate the references section
    # Search backwards from the last page to find where references start
    references_start_idx = -1
    ref_headers = [
        r'\b(?:references|bibliography|works\s+cited|literature\s+cited|references\s+and\s+notes)\b'
    ]
    
    # We will join page texts and look for reference headers.
    # To find the true bibliography section, we look towards the end of the paper.
    # We scan pages backwards.
    found_page_num = -1
    header_regex = re.compile('|'.join(ref_headers), re.IGNORECASE)
    
    for i in range(len(page_texts) - 1, -1, -1):
        text = page_texts[i]
        # Check if the page contains a reference header
        matches = list(header_regex.finditer(text))
        if matches:
            # We want to find a match that looks like a section heading.
            # Heading heuristics:
            # - It's usually on its own line or followed by a newline very soon.
            # - It is near the top of the page, or has spacing around it.
            for match in reversed(matches):
                start, end = match.span()
                # Extract surrounding text to check if it's a heading
                line_start = text.rfind('\n', 0, start) + 1
                line_end = text.find('\n', end)
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end].strip()
                
                # If the line is short (e.g. less than 30 characters), it's likely a header
                if len(line) < 30 and (line.lower() in ["references", "bibliography", "works cited", "literature cited", "references and notes"] or re.match(r'^\d*\.?\s*(references|bibliography|works\s+cited|literature\s+cited)\.?$', line, re.IGNORECASE)):
                    found_page_num = i
                    # The text after the header on this page, plus all subsequent pages, is references
                    references_text_list = [text[start:]]
                    for j in range(i + 1, len(page_texts)):
                        references_text_list.append(page_texts[j])
                    full_references_text = "\n".join(references_text_list)
                    break
            if found_page_num != -1:
                break
                
    # Fallback: if no clear header line was found backwards, search the whole text from the start
    if found_page_num == -1:
        # Just use the entire paper text or try to find the last occurrence of 'references' in the full text
        entire_text = "\n".join(page_texts)
        matches = list(header_regex.finditer(entire_text))
        if matches:
            # Pick the last match
            last_match = matches[-1]
            full_references_text = entire_text[last_match.start():]
        else:
            # Absolute fallback: assume the last 15% of the text is references
            total_len = len(entire_text)
            start_split = int(total_len * 0.85)
            full_references_text = entire_text[start_split:]
    
    # 2. Split the references text into individual citations
    # Clean up the header itself from the start
    first_newline = full_references_text.find('\n')
    if first_newline != -1 and first_newline < 50:
        full_references_text = full_references_text[first_newline + 1:]
        
    extracted = split_references(full_references_text)
    return extracted

def split_references(text: str) -> List[Dict[str, Any]]:
    """
    Heuristically splits a block of references text into individual citation strings.
    Supports:
    1. Numbered bracket style: [1] ... \n [2] ...
    2. Numbered period style: 1. ... \n 2. ...
    3. APA / Author-Year style (split by newlines and grouped)
    """
    # Normalize space characters but keep newlines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Check if the text is predominantly numbered (e.g. IEEE style)
    # Match "[1]", "1.", "1 " at the beginning of lines
    numbered_bracket_pattern = re.compile(r'^\[(\d+)\]')
    numbered_period_pattern = re.compile(r'^(\d+)\.')
    
    bracket_count = sum(1 for line in lines if numbered_bracket_pattern.match(line))
    period_count = sum(1 for line in lines if numbered_period_pattern.match(line))
    
    citations = []
    
    if bracket_count > 1:
        # Split by bracket pattern
        current_id = 0
        current_ref = []
        for line in lines:
            match = numbered_bracket_pattern.match(line)
            if match:
                if current_ref:
                    citations.append({
                        "reference_id": current_id or len(citations) + 1,
                        "raw_reference": " ".join(current_ref)
                    })
                current_id = int(match.group(1))
                current_ref = [line]
            else:
                if current_ref:
                    current_ref.append(line)
                else:
                    # In case of text before the first bracket
                    current_ref = [line]
        if current_ref:
            citations.append({
                "reference_id": current_id or len(citations) + 1,
                "raw_reference": " ".join(current_ref)
            })
            
    elif period_count > 1:
        # Split by period pattern
        current_id = 0
        current_ref = []
        for line in lines:
            match = numbered_period_pattern.match(line)
            if match:
                # To prevent matching things like "1.2%" or section numbers in random leftover text,
                # we also check if the number is incrementing or reasonably small, or we just trust the period
                if current_ref:
                    citations.append({
                        "reference_id": current_id or len(citations) + 1,
                        "raw_reference": " ".join(current_ref)
                    })
                current_id = int(match.group(1))
                current_ref = [line]
            else:
                if current_ref:
                    current_ref.append(line)
                else:
                    current_ref = [line]
        if current_ref:
            citations.append({
                "reference_id": current_id or len(citations) + 1,
                "raw_reference": " ".join(current_ref)
            })
            
    else:
        # APA / Author-Year style fallback (Unnumbered)
        # Citations are usually separate blocks.
        # Heuristic: A citation usually begins with an author's name (e.g. Capitalized letters followed by a comma or initials)
        # And often spans multiple lines, ending with a period.
        # Let's group lines. If a line starts with a Capitalized Word, or a year (e.g. (1998) or 2004), 
        # or matches an author pattern (e.g., Smith, J.), we might start a new citation.
        # However, a simpler and often highly effective heuristic for PDF text is:
        # If the line ends with a period and the next line starts with a capital letter, it's likely a boundary.
        # Or, we can group lines that are likely part of the same citation by checking hanging indents if layout is available.
        # Since get_text() merges text, we can use a simpler line-merging heuristic:
        current_ref = []
        author_start_pattern = re.compile(r'^[A-Z][a-zA-Z\-\s\u00C0-\u017F]+,\s+[A-Z]\.') # e.g. "Smith, J." or "Al-Fahim, M."
        
        for line in lines:
            # Heuristic to start a new citation block:
            # - current_ref is empty
            # - OR: the line looks strongly like the start of a new citation:
            #       - Starts with a standard author name prefix (e.g., "Smith, J.")
            #       - AND the previous reference ended with a period or looks complete.
            # - OR: the previous line ended with a period, and this line starts with a Capitalized Word and contains a year
            # Let's keep it simple: group lines until the current line ends with a period AND the next line starts with a pattern.
            # Alternatively, we can split references by lines that end with a year in parenthesis (e.g., "(2018).") or contains journal info.
            
            # Let's build a simple heuristic:
            # Group lines into references. If a line starts with an author pattern or is preceded by a line ending with a period + starts with uppercase.
            is_new = False
            if not current_ref:
                is_new = True
            else:
                prev_line = current_ref[-1]
                # If the previous line ends with a period, question mark, or closing quote:
                if prev_line.rstrip()[-1:] in ['.', '?', '"', '”']:
                    # If this line looks like a new citation (author name, year, or citation number):
                    starts_with_author = bool(author_start_pattern.match(line))
                    starts_with_year = bool(re.match(r'^\(?(19|20)\d{2}\)?', line))
                    starts_with_bracket_num = bool(re.match(r'^\[?\d+\]?[\.\s]', line))
                    
                    if starts_with_author or starts_with_year or starts_with_bracket_num:
                        is_new = True
            
            if is_new and current_ref:
                citations.append({
                    "reference_id": len(citations) + 1,
                    "raw_reference": " ".join(current_ref)
                })
                current_ref = [line]
            else:
                current_ref.append(line)
                
        if current_ref:
            citations.append({
                "reference_id": len(citations) + 1,
                "raw_reference": " ".join(current_ref)
            })
            
    # Post-process: clean up citation strings
    final_citations = []
    for citation in citations:
        raw_ref = citation["raw_reference"].strip()
        # Filter out obvious non-citation junk lines (e.g. page numbers, header leftovers)
        if len(raw_ref) > 15:
            final_citations.append({
                "reference_id": citation["reference_id"],
                "raw_reference": raw_ref
            })
            
    return final_citations
