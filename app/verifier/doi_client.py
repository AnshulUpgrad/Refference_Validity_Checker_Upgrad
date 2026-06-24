import re
import logging
import asyncio
from typing import Optional, Dict, Any, List
import httpx
from dotenv import load_dotenv
import os

from app.verifier.crossref_client import SQLiteCache
from app.verifier.context import crossref_mailto_var

logger = logging.getLogger("doi_client")
load_dotenv()

def extract_doi(text: str) -> Optional[str]:
    """
    Extracts a DOI from a citation string using regex.
    Supports standard DOI prefixes starting with 10.
    """
    # Look for a DOI pattern
    match = re.search(r'\b(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)', text)
    if match:
        doi = match.group(1)
        # Clean trailing punctuation commonly captured at the end of a sentence
        while doi and doi[-1] in '.,;)]}':
            doi = doi[:-1]
        return doi
    return None

class DOIClient:
    """
    Client to query Crossref Works API by exact DOI and resolve direct doi.org redirect HTML metadata.
    """
    def __init__(self, cache_db_path: str = "cache/citation_cache.db"):
        self.cache = SQLiteCache(cache_db_path)
        self.mailto = crossref_mailto_var.get() or os.getenv("CROSSREF_MAILTO", "anonymous@example.com")
        self.headers = {
            "User-Agent": f"LiteratureReviewSourceChecker/1.0 (mailto:{self.mailto})"
        }
        self.semaphore = asyncio.Semaphore(3)

    async def query_doi_metadata(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Looks up a DOI directly in Crossref works database.
        Checks SQLite cache first.
        """
        cache_key = f"doi_meta:{doi}"
        
        # Check Cache
        cached_result = await asyncio.to_thread(self.cache.get, cache_key)
        if cached_result is not None:
            logger.debug(f"DOI Metadata Cache hit for: '{doi}'")
            return cached_result[0] if cached_result else None

        # Fetch from Crossref Works API
        async with self.semaphore:
            result = await self._fetch_crossref_doi(doi)
            
            # Save to Cache
            cache_val = [result] if result else []
            await asyncio.to_thread(self.cache.set, cache_key, cache_val)
            return result

    async def _fetch_crossref_doi(self, doi: str) -> Optional[Dict[str, Any]]:
        url = f"https://api.crossref.org/works/{doi}"
        async with httpx.AsyncClient(timeout=20.0) as client:
            try:
                logger.info(f"Crossref Direct DOI request for: '{doi}'")
                response = await client.get(url, headers=self.headers)
                if response.status_code == 200:
                    data = response.json()
                    item = data.get("message", {})
                    
                    # Parse authors
                    authors_list = []
                    for auth in item.get("author", []):
                        family = auth.get("family", "")
                        given = auth.get("given", "")
                        if family and given:
                            authors_list.append(f"{family}, {given}")
                        elif family:
                            authors_list.append(family)
                            
                    # Extract year
                    year = None
                    pub_print = item.get("published-print", {})
                    pub_online = item.get("published-online", {})
                    if pub_print and pub_print.get("date-parts"):
                        year = pub_print["date-parts"][0][0]
                    elif pub_online and pub_online.get("date-parts"):
                        year = pub_online["date-parts"][0][0]
                        
                    return {
                        "title": item.get("title", [""])[0] if item.get("title") else "Unknown Title",
                        "authors": ", ".join(authors_list) if authors_list else "Unknown Authors",
                        "year": year,
                        "doi": item.get("DOI"),
                        "url": item.get("URL"),
                        "publisher": item.get("publisher", "Unknown Publisher"),
                        "journal": item.get("container-title", [""])[0] if item.get("container-title") else "Unknown Journal"
                    }
            except Exception as e:
                logger.error(f"Failed to fetch DOI metadata from Crossref: {e}")
        return None

    async def resolve_doi_redirect(self, doi: str) -> Optional[Dict[str, Any]]:
        """
        Resolves a DOI URL (https://doi.org/{doi}), finds the redirect endpoint,
        scrapes the HTML title and scholar metadata, and caches it.
        """
        cache_key = f"doi_redirect:{doi}"
        
        # Check Cache
        cached_result = await asyncio.to_thread(self.cache.get, cache_key)
        if cached_result is not None:
            logger.debug(f"DOI Redirect Cache hit for: '{doi}'")
            return cached_result[0] if cached_result else None

        # Resolve live
        async with self.semaphore:
            result = await self._fetch_doi_redirect(doi)
            
            # Save to Cache
            cache_val = [result] if result else []
            await asyncio.to_thread(self.cache.set, cache_key, cache_val)
            return result

    async def _fetch_doi_redirect(self, doi: str) -> Optional[Dict[str, Any]]:
        url = f"https://doi.org/{doi}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                logger.info(f"Resolving DOI Redirect for: '{doi}'")
                # Do not follow redirects automatically to capture Location header from doi.org (never blocked by Cloudflare)
                response = await client.get(url, headers=headers, follow_redirects=False)
                
                final_url = None
                if response.status_code in (301, 302, 303, 307, 308):
                    final_url = response.headers.get("Location")
                elif response.status_code == 200:
                    final_url = str(response.url)
                    
                if not final_url:
                    # Fallback: try with follow_redirects=True in case of direct resolution
                    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client_follow:
                        response_follow = await client_follow.get(url, headers=headers)
                        final_url = str(response_follow.url)
                
                if final_url:
                    logger.info(f"DOI '{doi}' resolved to redirect URL: '{final_url}'")
                    page_title = "No Title (Cloudflare/Access Restricted)"
                    meta_tags = {}
                    
                    # Try to fetch HTML content to scrape titles/meta tags
                    try:
                        pub_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                            "Accept-Language": "en-US,en;q=0.5"
                        }
                        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as pub_client:
                            pub_response = await pub_client.get(final_url, headers=pub_headers)
                            if pub_response.status_code == 200:
                                html_text = pub_response.text
                                
                                # Extract title
                                title_match = re.search(r'<title[^>]*>(.*?)</title>', html_text, re.IGNORECASE | re.DOTALL)
                                if title_match:
                                    page_title = title_match.group(1).strip()
                                    page_title = re.sub(r'\s+', ' ', page_title)
                                    
                                # Extract meta tags
                                matches1 = re.findall(
                                    r'<meta\s+[^>]*?(?:name|property)=["\'](.*?)["\']\s+[^>]*?content=["\'](.*?)["\']', 
                                    html_text, 
                                    re.IGNORECASE | re.DOTALL
                                )
                                matches2 = re.findall(
                                    r'<meta\s+[^>]*?content=["\'](.*?)["\']\s+[^>]*?(?:name|property)=["\'](.*?)["\']', 
                                    html_text, 
                                    re.IGNORECASE | re.DOTALL
                                )
                                
                                raw_meta = {}
                                for key, val in matches1:
                                    raw_meta[key.lower()] = val.strip()
                                for val, key in matches2:
                                    raw_meta[key.lower()] = val.strip()
                                    
                                interesting_keys = [
                                    "citation_title", "citation_author", "citation_publication_date", 
                                    "citation_journal_title", "og:title", "og:description"
                                ]
                                for k, v in raw_meta.items():
                                    if any(ik in k for ik in interesting_keys):
                                        clean_val = re.sub(r'\s+', ' ', v)
                                        if k in meta_tags:
                                            meta_tags[k] += "; " + clean_val
                                        else:
                                            meta_tags[k] = clean_val
                            else:
                                logger.warning(f"Could not retrieve HTML from resolved publisher site (status {pub_response.status_code})")
                    except Exception as html_err:
                        logger.warning(f"Failed to fetch publisher HTML details: {html_err}")
                        
                    return {
                        "final_url": final_url,
                        "page_title": page_title,
                        "meta_tags": meta_tags
                    }
                else:
                    logger.warning("Could not resolve DOI URL to any redirect destination")
            except Exception as e:
                logger.error(f"Failed to resolve DOI redirect: {e}")
        return None
