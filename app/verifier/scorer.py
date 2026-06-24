import re
import unicodedata
from typing import Dict, Any, List, Optional
from rapidfuzz import fuzz

def normalize_text(text: str) -> str:
    """
    Remove accents, lowercase, and strip punctuation/extra whitespace.
    """
    if not text:
        return ""
    # Normalize unicode characters (accents removal)
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    # Lowercase
    text = text.lower()
    # Remove non-alphanumeric chars (keep spaces and alphanumeric)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def extract_year_from_string(text: str) -> Optional[int]:
    """
    Finds the first 4-digit number that looks like a year (between 1800 and 2100).
    """
    matches = re.findall(r'\b(1[89]\d{2}|20\d{2})\b', text)
    if matches:
        return int(matches[0])
    return None

def extract_crossref_year(item: Dict[str, Any]) -> Optional[int]:
    """
    Extracts the publication year from Crossref item metadata.
    """
    # Check published-print
    for key in ["published-print", "published-online", "published", "created"]:
        date_parts = item.get(key, {}).get("date-parts", [])
        if date_parts and date_parts[0] and date_parts[0][0]:
            try:
                return int(date_parts[0][0])
            except (ValueError, TypeError):
                continue
    return None

def calculate_author_similarity(raw_ref: str, crossref_authors: List[Dict[str, Any]]) -> float:
    """
    Calculates how many of the authors listed in Crossref are present in the raw reference.
    Returns a score between 0.0 and 100.0.
    """
    if not crossref_authors:
        # No author data available in Crossref, return a neutral score
        return 80.0
        
    normalized_ref = normalize_text(raw_ref)
    matched_count = 0
    
    # Extract family names
    family_names = []
    for author in crossref_authors:
        fam = author.get("family")
        if fam:
            family_names.append(normalize_text(fam))
            
    if not family_names:
        return 80.0
        
    for name in family_names:
        # Check if family name is a word/substring in the raw reference
        if name and name in normalized_ref:
            matched_count += 1
            
    # We also check the first author particularly. If the first author is missing,
    # it is a strong signal that this is a different citation.
    first_author_matched = True
    if family_names:
        first_author = family_names[0]
        if first_author not in normalized_ref:
            first_author_matched = False
            
    ratio = matched_count / len(family_names)
    score = ratio * 100.0
    
    # Penalize if the first author isn't matched
    if not first_author_matched:
        score *= 0.5
        
    return score

def calculate_confidence_score(raw_ref: str, item: Dict[str, Any]) -> float:
    """
    Calculates a weighted confidence score (0 to 100) indicating if the Crossref item
    is indeed the paper cited in the raw reference.
    
    Weights:
    - Title Similarity: 70%
    - Author Similarity: 20%
    - Year Similarity: 10%
    """
    # 1. Title Similarity
    raw_title = item.get("title", [""])[0] if item.get("title") else ""
    if not raw_title:
        title_similarity = 0.0
    else:
        # Crossref title vs entire normalized raw reference (since raw ref contains title)
        # Use token_set_ratio which works well for sub-string matching and word order differences
        title_similarity = fuzz.token_set_ratio(normalize_text(raw_title), normalize_text(raw_ref))
        
    # 2. Author Similarity
    crossref_authors = item.get("author", [])
    author_similarity = calculate_author_similarity(raw_ref, crossref_authors)
    
    # 3. Year Similarity
    raw_year = extract_year_from_string(raw_ref)
    crossref_year = extract_crossref_year(item)
    
    if raw_year is not None and crossref_year is not None:
        year_diff = abs(raw_year - crossref_year)
        if year_diff == 0:
            year_similarity = 100.0
        elif year_diff == 1:
            year_similarity = 80.0
        else:
            year_similarity = 0.0
    else:
        # If one or both years are missing, assign a neutral year similarity
        year_similarity = 50.0

    # 4. Final Weighted Score
    final_score = (0.70 * title_similarity) + (0.20 * author_similarity) + (0.10 * year_similarity)
    return round(final_score, 1)
