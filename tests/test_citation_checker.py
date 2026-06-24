import pytest
import asyncio
from app.normalizer.reference_cleaner import clean_reference
from app.verifier.scorer import (
    normalize_text,
    extract_year_from_string,
    extract_crossref_year,
    calculate_author_similarity,
    calculate_confidence_score
)
from app.verifier.matcher import verify_reference
from app.extractor.pdf_parser import split_references

# ----------------- Normalization Tests -----------------

def test_clean_reference():
    # Numbered brackets (IEEE)
    assert clean_reference("[12] Smith J, Deep Learning Applications.") == "Smith J, Deep Learning Applications."
    # Numbered periods
    assert clean_reference("5. Jones et al., Neural Networks.") == "Jones et al., Neural Networks."
    # Parentheses
    assert clean_reference("(2) White A. Recurrent Networks.") == "White A. Recurrent Networks."
    # Space collapses and newlines
    assert clean_reference("  [4]   Green B. \nTitle   Name  ") == "Green B. Title Name"
    # No changes if not matching prefix
    assert clean_reference("Taylor et al. Transformers.") == "Taylor et al. Transformers."


# ----------------- Scorer Tests -----------------

def test_normalize_text():
    assert normalize_text("Résumé: Café & tea.") == "resume cafe tea"
    assert normalize_text("Title (2020) [Special]!") == "title 2020 special"


def test_extract_year_from_string():
    assert extract_year_from_string("Smith (2020) paper") == 2020
    assert extract_year_from_string("No year here.") is None
    assert extract_year_from_string("Year is 1854.") == 1854
    assert extract_year_from_string("Invalid 2500 year") is None


def test_extract_crossref_year():
    item_print = {"published-print": {"date-parts": [[2021, 5, 12]]}}
    assert extract_crossref_year(item_print) == 2021
    
    item_online = {"published-online": {"date-parts": [[2019]]}}
    assert extract_crossref_year(item_online) == 2019
    
    item_empty = {}
    assert extract_crossref_year(item_empty) is None


def test_calculate_author_similarity():
    # Exact match
    authors = [{"family": "Smith"}, {"family": "Jones"}]
    assert calculate_author_similarity("Smith, Jones (2020)", authors) == 100.0
    
    # Partial match
    assert calculate_author_similarity("Smith (2020)", authors) == 50.0
    
    # First author missing penalty
    # Here, Jones is matched, but the first author (Smith) is missing from the reference
    assert calculate_author_similarity("Jones et al. (2020)", authors) == 25.0  # 50% * 0.5 penalty
    
    # Empty author in Crossref
    assert calculate_author_similarity("No Authors", []) == 80.0


def test_calculate_confidence_score():
    raw_ref = "Smith J. Deep learning for vision. Journal of AI, 2020."
    crossref_item = {
        "title": ["Deep Learning for Vision"],
        "author": [{"family": "Smith", "given": "John"}],
        "published-print": {"date-parts": [[2020]]},
        "DOI": "10.1234/vision.2020"
    }
    
    score = calculate_confidence_score(raw_ref, crossref_item)
    # The title matches almost exactly. Author matches. Year matches.
    # Score should be very high (close to 100)
    assert score >= 90.0


# ----------------- Matcher Tests -----------------

from unittest.mock import patch

def test_verify_reference_rule_based():
    # Test rule-based fallback when LLM API is not available/configured
    raw_ref = "Smith J. Deep learning for vision. Journal of AI, 2020."
    
    with patch("app.verifier.matcher.verify_match_with_llm", return_value=None), \
         patch("app.verifier.matcher.verify_unmatched_citation", return_value=None):
         
        # High confidence + DOI exists -> VERIFIED
        candidates = [{
            "title": ["Deep Learning for Vision"],
            "author": [{"family": "Smith", "given": "John"}],
            "published-print": {"date-parts": [[2020]]},
            "DOI": "10.1234/vision.2020"
        }]
        res = asyncio.run(verify_reference(raw_ref, candidates))
        assert res["status"] == "VERIFIED"
        assert res["confidence"] >= 85.0
        assert res["matched_metadata"]["doi"] == "10.1234/vision.2020"
        
        # High confidence + DOI missing -> REVIEW_REQUIRED
        candidates_no_doi = [{
            "title": ["Deep Learning for Vision"],
            "author": [{"family": "Smith", "given": "John"}],
            "published-print": {"date-parts": [[2020]]}
        }]
        res_no_doi = asyncio.run(verify_reference(raw_ref, candidates_no_doi))
        assert res_no_doi["status"] == "REVIEW_REQUIRED"
        
        # Low confidence -> REVIEW_REQUIRED
        candidates_low = [{
            "title": ["Completely Unrelated Title"],
            "author": [{"family": "Unknown", "given": "Writer"}],
            "published-print": {"date-parts": [[2010]]}
        }]
        res_low = asyncio.run(verify_reference(raw_ref, candidates_low))
        assert res_low["status"] == "REVIEW_REQUIRED"

def test_verify_reference_llm_verified():
    raw_ref = "Smith J. Deep learning for vision. Journal of AI, 2020."
    
    # Mock LLM returning True match
    mock_match = {
        "is_match": True,
        "verdict": "LEGITIMATE",
        "confidence": 95.0,
        "reasoning": "Matches exactly"
    }
    
    with patch("app.verifier.matcher.verify_match_with_llm", return_value=mock_match), \
         patch("app.verifier.matcher.verify_unmatched_citation", return_value=None):
         
        candidates = [{
            "title": ["Deep Learning for Vision"],
            "author": [{"family": "Smith", "given": "John"}],
            "published-print": {"date-parts": [[2020]]},
            "DOI": "10.1234/vision.2020"
        }]
        res = asyncio.run(verify_reference(raw_ref, candidates))
        assert res["status"] == "VERIFIED"
        assert res["confidence"] == 95.0

def test_verify_reference_llm_fake():
    raw_ref = "Smith J. Deep learning for vision. Journal of AI, 2020."
    
    # Mock LLM rejecting candidate, then search flagging as fake
    mock_mismatch = {
        "is_match": False,
        "verdict": "SUSPECTED_FAKE",
        "confidence": 90.0,
        "reasoning": "Mismatched details"
    }
    mock_fake = {
        "is_match": False,
        "verdict": "SUSPECTED_FAKE",
        "confidence": 92.0,
        "reasoning": "Hallucinated citation"
    }
    
    with patch("app.verifier.matcher.verify_match_with_llm", return_value=mock_mismatch), \
         patch("app.verifier.matcher.verify_unmatched_citation", return_value=mock_fake), \
         patch("app.verifier.matcher.WebSearchClient.search_citation", return_value=[]):
         
        candidates = [{
            "title": ["Deep Learning for Vision"],
            "author": [{"family": "Smith", "given": "John"}],
            "published-print": {"date-parts": [[2020]]}
        }]
        res = asyncio.run(verify_reference(raw_ref, candidates))
        assert res["status"] == "REVIEW_REQUIRED"
        assert res["confidence"] == 92.0
def test_verify_reference_doi_redirect_metadata():
    raw_ref = "Mochizuki Y. Policy guidance. https://doi.org/10.1080/01425692.2025.2502808"
    
    mock_redirect_data = {
        "final_url": "https://www.tandfonline.com/doi/full/10.1080/01425692.2025.2502808",
        "page_title": "The ethics of AI or techno-solutionism? UNESCO’s policy guidance on AI in education",
        "meta_tags": {
            "citation_title": "The ethics of AI or techno-solutionism? UNESCO’s policy guidance on AI in education",
            "citation_author": "Yoko Mochizuki; Eric Bruillard; Audrey Bryan",
            "citation_journal_title": "British Journal of Sociology of Education"
        }
    }
    
    mock_llm_res = {
        "is_match": True,
        "verdict": "LEGITIMATE",
        "confidence": 98.0,
        "reasoning": "Metadata and resolved URL match the citation exactly"
    }
    
    with patch("app.verifier.matcher.DOIClient.query_doi_metadata", return_value=None), \
         patch("app.verifier.matcher.DOIClient.resolve_doi_redirect", return_value=mock_redirect_data), \
         patch("app.verifier.matcher.verify_doi_redirect_metadata", return_value=mock_llm_res):
         
        res = asyncio.run(verify_reference(raw_ref, []))
        assert res["status"] == "VERIFIED"
        assert res["confidence"] == 98.0
        assert res["matched_metadata"]["doi"] == "10.1080/01425692.2025.2502808"
        assert "tandfonline.com" in res["matched_metadata"]["url"]



# ----------------- Extractor Splitter Tests -----------------

def test_split_references():
    # Numbered brackets (IEEE)
    text_brackets = "[1] Smith et al., Title 1.\n[2] Jones et al., Title 2."
    citations_brackets = split_references(text_brackets)
    assert len(citations_brackets) == 2
    assert citations_brackets[0]["reference_id"] == 1
    assert "Title 1" in citations_brackets[0]["raw_reference"]
    
    # Numbered periods
    text_periods = "1. Smith et al., Title A.\n2. Jones et al., Title B."
    citations_periods = split_references(text_periods)
    assert len(citations_periods) == 2
    assert citations_periods[0]["reference_id"] == 1
    assert "Title A" in citations_periods[0]["raw_reference"]

    # APA Grouping Heuristic
    text_apa = "Smith, J. (2018). Title of paper.\nJournal of AI, 12(3).\nJones, M. (2019). Second paper.\nNeural Networks, 5."
    citations_apa = split_references(text_apa)
    assert len(citations_apa) == 2
    assert "Title of paper" in citations_apa[0]["raw_reference"]
    assert "Second paper" in citations_apa[1]["raw_reference"]


def test_split_references_llm_success():
    from app.extractor.pdf_parser import split_references_with_llm
    from app.verifier.context import openrouter_key_var
    
    mock_response = {
        "choices": [
            {
                "message": {
                    "content": '{"references": ["Ref A", "Ref B"]}'
                }
            }
        ]
    }
    
    with patch("httpx.Client.post") as mock_post:
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_response
        mock_post.return_value = mock_resp
        
        token = openrouter_key_var.set("fake_key")
        try:
            with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}):
                citations = split_references_with_llm("raw text")
                
                assert citations is not None
                assert len(citations) == 2
                assert citations[0]["reference_id"] == 1
                assert citations[0]["raw_reference"] == "Ref A"
                assert citations[1]["reference_id"] == 2
                assert citations[1]["raw_reference"] == "Ref B"
        finally:
            openrouter_key_var.reset(token)

def test_split_references_llm_failure():
    from app.extractor.pdf_parser import split_references_with_llm
    from app.verifier.context import openrouter_key_var
    
    with patch("httpx.Client.post") as mock_post:
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp
        
        token = openrouter_key_var.set("fake_key")
        try:
            with patch.dict("os.environ", {"PYTEST_CURRENT_TEST": ""}):
                citations = split_references_with_llm("raw text")
                assert citations is None
        finally:
            openrouter_key_var.reset(token)


# ----------------- DOCX Generator Tests -----------------

def test_docx_generation():
    from app.reporting.docx_generator import build_docx_report
    mock_results = {
        "summary": {
            "total_references": 2,
            "verified": 1,
            "legitimate_llm": 0,
            "review_required": 1
        },
        "references": [
            {
                "reference_id": 1,
                "raw_reference": "Smith J, Deep Learning, 2020.",
                "status": "VERIFIED",
                "confidence": 95.0,
                "matched_metadata": {
                    "title": "Deep Learning",
                    "authors": "Smith J",
                    "year": 2020,
                    "journal": "AI Journal",
                    "publisher": "Springer",
                    "doi": "10.1000/xyz123",
                    "url": "https://doi.org/10.1000/xyz123"
                },
                "llm_verdict": {
                    "is_match": True,
                    "verdict": "LEGITIMATE",
                    "reasoning": "Title and authors match."
                }
            },
            {
                "reference_id": 2,
                "raw_reference": "Fake Citation 2021",
                "status": "REVIEW_REQUIRED",
                "confidence": 30.0,
                "matched_metadata": None,
                "llm_verdict": {
                    "is_match": False,
                    "verdict": "SUSPECTED_FAKE",
                    "reasoning": "Does not exist."
                }
            }
        ]
    }
    
    doc = build_docx_report(mock_results)
    assert doc is not None
    # Check that we have elements in the document
    assert len(doc.paragraphs) > 0
    assert len(doc.tables) > 0
    
    # Verify titles/headings
    headings = [p.text for p in doc.paragraphs if p.text]
    assert any("Literature Review Source Verification Report" in h for h in headings)
    assert any("Executive Analytics Summary" in h for h in headings)
    assert any("Detailed Reference Audit" in h for h in headings)

