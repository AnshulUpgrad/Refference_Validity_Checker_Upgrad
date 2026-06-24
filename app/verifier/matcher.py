import logging
from typing import List, Dict, Any
from app.verifier.scorer import calculate_confidence_score, extract_crossref_year
from app.verifier.arxiv_client import ArxivClient, extract_arxiv_id
from app.verifier.search_client import WebSearchClient
from app.verifier.llm_verifier import verify_match_with_llm, verify_unmatched_citation, verify_doi_redirect_metadata
from app.normalizer.reference_cleaner import clean_reference
from app.verifier.doi_client import DOIClient, extract_doi

logger = logging.getLogger("matcher")

async def verify_reference(raw_ref: str, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Orchestrates the multi-layered legitimacy check pipeline for a citation:
    1. Extract arXiv ID and verify via arXiv API if present.
    2. If no arXiv ID, score and verify Crossref candidates.
    3. If database lookup returns a mismatch or no match, run a DuckDuckGo web search
       and pass snippets to gemini-2.5-flash for contextual verification.
    4. Fall back gracefully to rule-based scores if no OpenRouter key is set.
    """
    arxiv_client = ArxivClient()
    search_client = WebSearchClient()
    doi_client = DOIClient()
    
    status = "UNVERIFIED"
    confidence = 0.0
    matched_metadata = None
    llm_verdict = None

    # ---------------- Layer 0: Direct DOI Check ----------------
    doi = extract_doi(raw_ref)
    if doi:
        logger.info(f"Extracted DOI '{doi}' from reference.")
        # Try Crossref works database first
        doi_match = await doi_client.query_doi_metadata(doi)
        if doi_match:
            # Evaluate using LLM or rule-based match
            llm_res = await verify_match_with_llm(raw_ref, doi_match)
            if llm_res is not None:
                if llm_res["is_match"]:
                    status = "VERIFIED"
                    matched_metadata = doi_match
                    confidence = llm_res["confidence"]
                    llm_verdict = {
                        "is_match": True,
                        "verdict": llm_res.get("verdict", "LEGITIMATE"),
                        "reasoning": llm_res["reasoning"]
                    }
            else:
                # Rule-based fallback
                score = calculate_confidence_score(raw_ref, {
                    "title": [doi_match["title"]],
                    "author": [{"family": a.split(",")[-1].strip()} for a in doi_match["authors"].split(", ")],
                    "published-print": {"date-parts": [[doi_match["year"]]]}
                })
                if score >= 70.0:
                    status = "VERIFIED"
                    matched_metadata = doi_match
                    confidence = score

        # If Crossref didn't resolve it or failed, try resolving the redirection
        if status == "UNVERIFIED":
            redirect_res = await doi_client.resolve_doi_redirect(doi)
            if redirect_res:
                final_url = redirect_res["final_url"]
                page_title = redirect_res["page_title"]
                meta_tags = redirect_res["meta_tags"]
                
                # Check redirect metadata using LLM
                llm_res = await verify_doi_redirect_metadata(
                    raw_ref, doi, final_url, page_title, meta_tags
                )
                if llm_res is not None:
                    llm_verdict = {
                        "is_match": llm_res["is_match"],
                        "verdict": llm_res.get("verdict"),
                        "reasoning": llm_res["reasoning"]
                    }
                    confidence = llm_res["confidence"]
                    if llm_res["is_match"]:
                        status = "VERIFIED"
                        matched_metadata = {
                            "title": page_title or meta_tags.get("citation_title", "Resolved Article"),
                            "authors": meta_tags.get("citation_author", "Verified via DOI Link"),
                            "year": None,
                            "doi": doi,
                            "url": final_url,
                            "publisher": "DOI Redirect Link",
                            "journal": meta_tags.get("citation_journal_title", "Resolved Publisher Portal")
                        }

    # ---------------- Layer 1: arXiv Preprint Check ----------------
    if status == "UNVERIFIED":
        arxiv_id = extract_arxiv_id(raw_ref)
        if arxiv_id:
            logger.info(f"Extracted arXiv ID '{arxiv_id}' from reference.")
            arxiv_match = await arxiv_client.query_arxiv(arxiv_id)
            if arxiv_match:
                # We found a matching preprint! Verify details using LLM or rule score
                matched_metadata = arxiv_match
                confidence = calculate_confidence_score(raw_ref, {
                    "title": [arxiv_match["title"]],
                    "author": [{"family": a.split(",")[-1].strip()} for a in arxiv_match["authors"].split(", ")],
                    "published-print": {"date-parts": [[arxiv_match["year"]]]}
                })
                
                # Double check match using LLM
                llm_res = await verify_match_with_llm(raw_ref, matched_metadata)
                if llm_res is not None:
                    llm_verdict = {
                        "is_match": llm_res["is_match"],
                        "verdict": llm_res.get("verdict"),
                        "reasoning": llm_res["reasoning"]
                    }
                    confidence = llm_res["confidence"]
                    if llm_res["is_match"]:
                        status = "VERIFIED"
                    else:
                        # If LLM rejects the exact arXiv ID match, fall back to web search
                        matched_metadata = None
                else:
                    # Rule-based fallback
                    if confidence >= 70.0:
                        status = "VERIFIED"
                    else:
                        matched_metadata = None

    # ---------------- Layer 2: Crossref Database Check ----------------
    # (Only run if arXiv lookup didn't yield a verified match)
    if status == "UNVERIFIED" and candidates:
        best_candidate = None
        highest_score = -1.0

        for candidate in candidates:
            score = calculate_confidence_score(raw_ref, candidate)
            if score > highest_score:
                highest_score = score
                best_candidate = candidate

        if best_candidate and highest_score >= 45.0:
            # Parse authors
            authors_list = []
            for auth in best_candidate.get("author", []):
                family = auth.get("family", "")
                given = auth.get("given", "")
                if family and given:
                    authors_list.append(f"{family}, {given}")
                elif family:
                    authors_list.append(family)

            candidate_metadata = {
                "title": best_candidate.get("title", [""])[0] if best_candidate.get("title") else "Unknown Title",
                "authors": ", ".join(authors_list) if authors_list else "Unknown Authors",
                "year": extract_crossref_year(best_candidate),
                "doi": best_candidate.get("DOI"),
                "url": best_candidate.get("URL"),
                "publisher": best_candidate.get("publisher", "Unknown Publisher"),
                "journal": best_candidate.get("container-title", [""])[0] if best_candidate.get("container-title") else "Unknown Journal"
            }

            llm_res = await verify_match_with_llm(raw_ref, candidate_metadata)
            if llm_res is not None:
                if llm_res["is_match"]:
                    status = "VERIFIED" if candidate_metadata["doi"] else "FOUND_NO_DOI"
                    matched_metadata = candidate_metadata
                    confidence = llm_res["confidence"]
                    llm_verdict = {
                        "is_match": True,
                        "verdict": llm_res.get("verdict", "LEGITIMATE"),
                        "reasoning": llm_res["reasoning"]
                    }
                else:
                    # Mismatch. It might still be a real paper, so we don't flag it as fake yet.
                    # We will run the web search fallback below.
                    pass
            else:
                # Rule-based fallback (no LLM key)
                if highest_score >= 80.0:
                    status = "VERIFIED" if candidate_metadata["doi"] else "FOUND_NO_DOI"
                    matched_metadata = candidate_metadata
                    confidence = highest_score
                elif highest_score >= 60.0:
                    status = "REVIEW_REQUIRED"
                    matched_metadata = candidate_metadata
                    confidence = highest_score

    # ---------------- Layer 3: Web Search Fallback & LLM Knowledge Audit ----------------
    # Run if we still haven't verified the paper (or if it was rejected as a database mismatch)
    if status == "UNVERIFIED":
        cleaned_ref = clean_reference(raw_ref)
        search_results = await search_client.search_citation(cleaned_ref)
        
        # Query LLM with search context
        llm_res = await verify_unmatched_citation(raw_ref, search_results)
        if llm_res is not None:
            llm_verdict = {
                "is_match": llm_res["is_match"],
                "verdict": llm_res.get("verdict"),
                "reasoning": llm_res["reasoning"]
            }
            confidence = llm_res["confidence"]
            
            # Map LLM verdict string to pipeline status
            if llm_res["verdict"] == "LEGITIMATE_KNOWN":
                status = "LEGITIMATE_KNOWN"
                # If we found a web link, attach it in metadata
                top_link = search_results[0]["href"] if search_results else None
                matched_metadata = {
                    "title": search_results[0]["title"] if search_results else "Verified on Web",
                    "authors": "Verified via LLM/Search",
                    "year": None,
                    "doi": None,
                    "url": top_link,
                    "publisher": "Web Results",
                    "journal": "Search verified"
                }
            elif llm_res["verdict"] == "SUSPECTED_FAKE":
                status = "SUSPECTED_FAKE"
            else:
                status = "UNVERIFIED"
        else:
            # No LLM key fallback
            if matched_metadata:
                # Keep database match if it existed (e.g. from review status in rule base)
                pass
            else:
                status = "UNVERIFIED"

    if status in ("FOUND_NO_DOI", "SUSPECTED_FAKE", "UNVERIFIED"):
        status = "REVIEW_REQUIRED"

    return {
        "status": status,
        "confidence": confidence,
        "matched_metadata": matched_metadata,
        "llm_verdict": llm_verdict
    }
