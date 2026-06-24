import os
import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from datetime import datetime

logger = logging.getLogger("llm_verifier")

async def verify_match_with_llm(
    raw_ref: str, 
    matched_metadata: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Queries OpenRouter (gemini-2.5-flash) to evaluate whether a database match
    metadata candidate corresponds to the cited paper in the original reference.
    
    Returns a dict with:
      - is_match (bool)
      - verdict (str): "LEGITIMATE" or "SUSPECTED_FAKE"
      - confidence (float)
      - reasoning (str)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    current_date = datetime.now().strftime("%B %d, %Y")
    system_prompt = (
        "You are an academic citation auditing assistant. Your job is to analyze "
        "if the metadata returned from a database search corresponds to the actual "
        "citation in the original reference. Fake/hallucinated academic citations "
        "often get matched to random, unrelated papers because they share keywords. "
        "Compare them critically. "
        f"Note: Today's date is {current_date}. Keep in mind that publications up to "
        "this date are valid and exist in the present. "
        "Respond ONLY with a JSON object matching this schema:\n"
        "{\n"
        "  \"is_match\": boolean,\n"
        "  \"verdict\": \"LEGITIMATE\" or \"SUSPECTED_FAKE\",\n"
        "  \"confidence\": number (0-100),\n"
        "  \"reasoning\": \"string explaining why it is or is not a match\"\n"
        "}"
    )

    user_content = (
        f"Original Reference: \"{raw_ref}\"\n\n"
        f"Database Matched Metadata:\n"
        f"- Title: {matched_metadata.get('title')}\n"
        f"- Authors: {matched_metadata.get('authors')}\n"
        f"- Year: {matched_metadata.get('year')}\n"
        f"- Journal/Book: {matched_metadata.get('journal')}\n"
        f"- Publisher: {matched_metadata.get('publisher')}\n"
        f"- DOI: {matched_metadata.get('doi')}\n\n"
        f"Assess if the database match represents the same publication as the original citation. "
        f"Completely different titles, authors, or journals indicate a mismatch (SUSPECTED_FAKE)."
        f"Produce the JSON verdict."
    )

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                result = json.loads(content, strict=False)
                return {
                    "is_match": bool(result["is_match"]),
                    "verdict": str(result["verdict"]),
                    "confidence": float(result["confidence"]),
                    "reasoning": str(result["reasoning"])
                }
    except Exception as e:
        logger.error(f"Error in match verification: {e}")
    return None

async def verify_unmatched_citation(
    raw_ref: str, 
    search_results: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    Queries OpenRouter (gemini-2.5-flash) when no database match is found.
    Uses web search results and pre-trained knowledge to determine if the paper
    is legitimate (just missing from databases) or a suspected fake.
    
    Returns a dict with:
      - is_match (bool)
      - verdict (str): "LEGITIMATE_KNOWN", "SUSPECTED_FAKE", or "UNVERIFIED"
      - confidence (float)
      - reasoning (str)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    current_date = datetime.now().strftime("%B %d, %Y")
    system_prompt = (
        "You are an academic citation auditing assistant. Your job is to check if "
        "a citation is a legitimate academic publication or a hallucinated/fake reference. "
        "We searched databases for this citation and found no match. We then did a web search. "
        "Based on the web search snippets provided and your pre-trained knowledge of scientific "
        "literature (NIPS, ICML, CVPR, arXiv, etc.), decide if the paper is real. "
        f"Note: Today's date is {current_date}. Keep in mind that publications up to "
        "this date are valid and exist in the present. "
        "Respond ONLY with a JSON object matching this schema:\n"
        "{\n"
        "  \"is_match\": boolean (true if real/legitimate, false if fake or unknown),\n"
        "  \"verdict\": \"LEGITIMATE_KNOWN\" or \"SUSPECTED_FAKE\" or \"UNVERIFIED\",\n"
        "  \"confidence\": number (0-100),\n"
        "  \"reasoning\": \"string explaining why it is legitimate, suspected fake, or unverified\"\n"
        "}"
    )

    search_text = ""
    for idx, r in enumerate(search_results, 1):
        search_text += f"\nResult {idx}:\n- Title: {r['title']}\n- Snippet: {r['snippet']}\n- Link: {r['href']}\n"

    user_content = (
        f"Original Citation under review: \"{raw_ref}\"\n\n"
        f"Web Search Results for this citation:\n{search_text or 'No search results found.'}\n\n"
        f"Determine legitimacy:\n"
        f"- If the paper is famous or has clear matching web results (e.g. arXiv, ResearchGate, PDF link, "
        f"Google Scholar index showing correct authors & title), output LEGITIMATE_KNOWN.\n"
        f"- If there is strong evidence the citation is fabricated (e.g., matching a non-existent journal, "
        f"fictional DOI, or authors who never co-wrote this paper), output SUSPECTED_FAKE.\n"
        f"- If you cannot find any traces of the paper but cannot prove it's fake (could be a book, thesis, "
        f"or obscure workshop), output UNVERIFIED.\n"
        f"Produce the JSON verdict."
    )

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                result = json.loads(content, strict=False)
                return {
                    "is_match": bool(result["is_match"]),
                    "verdict": str(result["verdict"]),
                    "confidence": float(result["confidence"]),
                    "reasoning": str(result["reasoning"])
                }
    except Exception as e:
        logger.error(f"Error in unmatched verification: {e}")
    return None

async def verify_doi_redirect_metadata(
    raw_ref: str,
    doi: str,
    resolved_url: str,
    page_title: str,
    meta_tags: Dict[str, str]
) -> Optional[Dict[str, Any]]:
    """
    Queries OpenRouter (gemini-2.5-flash) to evaluate whether a resolved DOI URL redirect
    and extracted page HTML metadata correspond to the cited paper in the raw reference.
    
    Returns a dict with:
      - is_match (bool)
      - verdict (str): "LEGITIMATE" or "SUSPECTED_FAKE"
      - confidence (float)
      - reasoning (str)
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return None

    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    current_date = datetime.now().strftime("%B %d, %Y")
    system_prompt = (
        "You are an academic citation auditing assistant. Your job is to analyze "
        "if a resolved DOI redirect URL and its HTML metadata (like page title and meta tags) "
        "correspond to the actual citation in the original reference. "
        "Decide if they represent the same publication. "
        f"Note: Today's date is {current_date}. Keep in mind that publications up to "
        "this date are valid and exist in the present. "
        "Respond ONLY with a JSON object matching this schema:\n"
        "{\n"
        "  \"is_match\": boolean,\n"
        "  \"verdict\": \"LEGITIMATE\" or \"SUSPECTED_FAKE\",\n"
        "  \"confidence\": number (0-100),\n"
        "  \"reasoning\": \"string explaining why it is or is not a match\"\n"
        "}"
    )

    meta_text = ""
    for k, v in meta_tags.items():
        meta_text += f"- {k}: {v}\n"

    user_content = (
        f"Original Reference: \"{raw_ref}\"\n\n"
        f"DOI: {doi}\n"
        f"Resolved Publisher URL: {resolved_url}\n"
        f"HTML Page Title: {page_title}\n"
        f"Extracted Meta Tags:\n{meta_text or 'None extracted.'}\n\n"
        f"Assess if the resolved publisher portal and metadata represent the same publication as the original citation. "
        f"A matching title, author surnames, or a clear redirect to the article on a reputable academic site (e.g. Taylor & Francis, Springer, Elsevier, etc.) "
        f"indicates it is a match (LEGITIMATE). A mismatch in names or titles, or a redirect to an unrelated domain suggests it is not a match (SUSPECTED_FAKE)."
        f"Produce the JSON verdict."
    )

    payload = {
        "model": "google/gemini-2.5-flash",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "response_format": {"type": "json_object"}
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                result = json.loads(content, strict=False)
                return {
                    "is_match": bool(result["is_match"]),
                    "verdict": str(result["verdict"]),
                    "confidence": float(result["confidence"]),
                    "reasoning": str(result["reasoning"])
                }
    except Exception as e:
        logger.error(f"Error in DOI redirect metadata verification: {e}")
    return None

