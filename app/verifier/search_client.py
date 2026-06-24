import logging
import asyncio
from typing import List, Dict, Any, Optional
from duckduckgo_search import DDGS

from app.verifier.crossref_client import SQLiteCache

logger = logging.getLogger("search_client")

class WebSearchClient:
    """
    Asynchronous client for searching the web using DuckDuckGo, with SQLite caching.
    """
    def __init__(self, cache_db_path: str = "cache/citation_cache.db"):
        self.cache = SQLiteCache(cache_db_path)
        self.semaphore = asyncio.Semaphore(2)  # Limit concurrent searches to avoid DDG blocks

    async def search_citation(self, query: str) -> List[Dict[str, Any]]:
        """
        Searches DuckDuckGo for the citation string.
        First checks SQLite cache; falls back to live search if not cached.
        Returns a list of search result items:
        [
            {"title": "...", "snippet": "...", "href": "..."},
            ...
        ]
        """
        if not query:
            return []

        cache_key = f"search:{query}"
        
        # Check Cache
        cached_result = await asyncio.to_thread(self.cache.get, cache_key)
        if cached_result is not None:
            logger.debug(f"Search Cache hit for: '{query[:30]}...'")
            return cached_result

        # Live Search
        async with self.semaphore:
            results = await self._fetch_from_api(query)
            
            # Save to Cache
            await asyncio.to_thread(self.cache.set, cache_key, results)
            return results

    async def _fetch_from_api(self, query: str) -> List[Dict[str, Any]]:
        """
        Executes DuckDuckGo search in a thread pool to avoid blocking the asyncio loop.
        """
        def _ddg_search():
            try:
                logger.info(f"Web Search request for: '{query[:40]}...'")
                # Using DDGS as a context manager is standard in duckduckgo_search
                with DDGS() as ddgs:
                    # Query DDG text search (retrieve top 3 results)
                    responses = ddgs.text(query, max_results=3)
                    
                    parsed_results = []
                    if responses:
                        for r in responses:
                            title = r.get("title", "")
                            body = r.get("body", "")  # body contains the snippet text
                            href = r.get("href", "")
                            
                            if title or body:
                                parsed_results.append({
                                    "title": title,
                                    "snippet": body,
                                    "href": href
                                })
                    return parsed_results
            except Exception as e:
                logger.error(f"DuckDuckGo search failed: {e}")
                return []

        # Run the blocking duckduckgo-search call in a separate thread
        try:
            return await asyncio.to_thread(_ddg_search)
        except Exception as e:
            logger.error(f"Async thread execution failed for search: {e}")
            return []
