import re
import logging
import asyncio
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List
import httpx

from app.verifier.crossref_client import SQLiteCache

logger = logging.getLogger("arxiv_client")

# Namespaces for parsing arXiv Atom feed XML
NAMESPACES = {
    'atom': 'http://www.w3.org/2005/Atom',
    'opensearch': 'http://www.opensolaris.org/opensearch/1.0/',
    'arxiv': 'http://arxiv.org/schemas/atom'
}

def extract_arxiv_id(text: str) -> Optional[str]:
    """
    Heuristically extracts an arXiv ID from a citation text.
    Supports:
    - New style (2007-present): YYMM.NNNN or YYMM.NNNNN (e.g., 1607.06450, 1412.3555, 1703.03906)
    - Old style (1991-2007): e.g. hep-th/9711200, quant-ph/9901001
    """
    # 1. New style pattern (e.g. 1607.06450v2, abs/1607.06450, arXiv:1607.06450)
    new_style_match = re.search(r'\b(\d{4}\.\d{4,5})(?:v\d+)?\b', text)
    if new_style_match:
        return new_style_match.group(1)
        
    # 2. Old style pattern (e.g. hep-th/9711200, cond-mat/0410445)
    old_style_match = re.search(r'\b([a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?\b', text)
    if old_style_match:
        return old_style_match.group(1)
        
    return None

class ArxivClient:
    """
    Asynchronous client for querying the arXiv API, with SQLite caching.
    """
    BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, cache_db_path: str = "cache/citation_cache.db"):
        self.cache = SQLiteCache(cache_db_path)
        self.semaphore = asyncio.Semaphore(3)

    async def query_arxiv(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        Queries arXiv for a given paper ID.
        Checks SQLite cache first.
        """
        cache_key = f"arxiv:{arxiv_id}"
        
        # Check Cache
        cached_result = await asyncio.to_thread(self.cache.get, cache_key)
        if cached_result is not None:
            logger.debug(f"ArXiv Cache hit for: '{arxiv_id}'")
            return cached_result[0] if cached_result else None

        # Fetch from API
        async with self.semaphore:
            result = await self._fetch_from_api(arxiv_id)
            
            # Save to Cache (even empty results or failures)
            cache_val = [result] if result else []
            await asyncio.to_thread(self.cache.set, cache_key, cache_val)
            return result

    async def _fetch_from_api(self, arxiv_id: str) -> Optional[Dict[str, Any]]:
        """
        Executes HTTP GET request to export.arxiv.org API.
        """
        params = {"id_list": arxiv_id}
        
        async with httpx.AsyncClient(timeout=25.0) as client:
            try:
                logger.info(f"ArXiv API request for: '{arxiv_id}'")
                response = await client.get(self.BASE_URL, params=params, follow_redirects=True)
                
                if response.status_code == 200:
                    return self._parse_arxiv_xml(response.text)
                else:
                    logger.error(f"ArXiv API returned error {response.status_code}")
            except Exception as e:
                logger.error(f"ArXiv request failed: {e}")
                
        return None

    def _parse_arxiv_xml(self, xml_text: str) -> Optional[Dict[str, Any]]:
        """
        Parses ArXiv Atom XML feed response.
        """
        try:
            root = ET.fromstring(xml_text)
            entry = root.find('atom:entry', NAMESPACES)
            
            if entry is None:
                return None
                
            # Check if entry is empty (arxiv returns an empty entry if ID not found)
            id_elem = entry.find('atom:id', NAMESPACES)
            if id_elem is None or not id_elem.text:
                return None
                
            # Check if there is an error title (e.g. "Error")
            title_elem = entry.find('atom:title', NAMESPACES)
            title = title_elem.text.strip() if title_elem is not None else ""
            if not title or title.lower() == "error":
                return None
                
            # Collapse extra spaces/newlines in title
            title = re.sub(r'\s+', ' ', title)
            
            # Extract authors
            authors_list = []
            for author_node in entry.findall('atom:author', NAMESPACES):
                name_node = author_node.find('atom:name', NAMESPACES)
                if name_node is not None and name_node.text:
                    authors_list.append(name_node.text.strip())
                    
            # Extract year from <published> tag (e.g. 2016-07-21T14:50:00Z)
            pub_elem = entry.find('atom:published', NAMESPACES)
            year = None
            if pub_elem is not None and pub_elem.text:
                match = re.match(r'^(\d{4})', pub_elem.text)
                if match:
                    year = int(match.group(1))
                    
            # Extract PDF link
            pdf_url = ""
            for link_node in entry.findall('atom:link', NAMESPACES):
                if link_node.attrib.get('title') == 'pdf':
                    pdf_url = link_node.attrib.get('href', '')
                elif link_node.attrib.get('type') == 'application/pdf':
                    pdf_url = link_node.attrib.get('href', '')
                    
            return {
                "title": title,
                "authors": ", ".join(authors_list),
                "year": year,
                "doi": None,  # arXiv doesn't always have DOIs in base entry, we can look up, but URL is enough
                "url": pdf_url or f"https://arxiv.org/abs/{extract_arxiv_id(id_elem.text)}",
                "journal": "arXiv Preprint",
                "publisher": "arXiv"
            }
        except Exception as e:
            logger.error(f"Failed to parse arXiv Atom XML: {e}")
            
        return None
