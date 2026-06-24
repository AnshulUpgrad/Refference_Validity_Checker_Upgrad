import os
import sqlite3
import hashlib
import json
import logging
import asyncio
from typing import Optional, Dict, Any, List
import httpx
from dotenv import load_dotenv
from app.verifier.context import crossref_mailto_var

# Load environment variables
load_dotenv()

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("crossref_client")

class SQLiteCache:
    """
    Thread-safe/async-compatible wrapper for SQLite caching of Crossref API responses.
    Saves API results under a SHA-256 hash of the normalized citation string.
    """
    def __init__(self, db_path: str = "cache/citation_cache.db"):
        self.db_path = db_path
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
            
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_connection()
        try:
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS crossref_cache (
                        hash TEXT PRIMARY KEY,
                        query TEXT NOT NULL,
                        response TEXT NOT NULL,
                        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        finally:
            conn.close()

    def get(self, query: str) -> Optional[List[Dict[str, Any]]]:
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
        
        # Run in thread pool to avoid blocking the event loop
        def _read():
            conn = self._get_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT response FROM crossref_cache WHERE hash = ?", 
                    (query_hash,)
                )
                row = cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except json.JSONDecodeError:
                        return None
                return None
            finally:
                conn.close()
                
        return _read()

    def set(self, query: str, response_data: List[Dict[str, Any]]):
        query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()
        response_str = json.dumps(response_data)
        
        # Run in thread pool to avoid blocking the event loop
        def _write():
            conn = self._get_connection()
            try:
                with conn:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO crossref_cache (hash, query, response)
                        VALUES (?, ?, ?)
                        """,
                        (query_hash, query, response_str)
                    )
            finally:
                conn.close()
                
        _write()


class CrossrefClient:
    """
    Asynchronous client for querying the Crossref works API, with Polite Pool support and SQLite caching.
    """
    BASE_URL = "https://api.crossref.org/works"

    def __init__(self, mailto: Optional[str] = None, cache_db_path: str = "cache/citation_cache.db"):
        # Retrieve mailto from parameter or env
        self.mailto = mailto or crossref_mailto_var.get() or os.getenv("CROSSREF_MAILTO") or "anonymous@example.com"
        self.cache = SQLiteCache(cache_db_path)
        
        # Set up headers for the Crossref Polite Pool
        self.headers = {
            "User-Agent": f"LiteratureReviewSourceChecker/1.0 (mailto:{self.mailto}; contact-email-for-troubleshooting)"
        }
        
        # Limit concurrency to 5 queries at a time to be polite and prevent rate limits
        self.semaphore = asyncio.Semaphore(5)
        
    async def query_reference(self, normalized_ref: str) -> List[Dict[str, Any]]:
        """
        Queries Crossref for a given reference string.
        First checks SQLite cache; falls back to HTTP request if not cached.
        Returns a list of matching candidates (up to 3).
        """
        if not normalized_ref:
            return []

        # Check Cache
        cached_result = await asyncio.to_thread(self.cache.get, normalized_ref)
        if cached_result is not None:
            logger.debug(f"Cache hit for: '{normalized_ref[:30]}...'")
            return cached_result

        # Cache miss, fetch from API
        async with self.semaphore:
            results = await self._fetch_from_api(normalized_ref)
            
            # Save to Cache (even empty results are cached to prevent repeating failed lookups)
            await asyncio.to_thread(self.cache.set, normalized_ref, results)
            return results

    async def _fetch_from_api(self, query: str, retries: int = 3, backoff: float = 1.0) -> List[Dict[str, Any]]:
        """
        Executes HTTP GET request to Crossref Works API with retries and exponential backoff.
        """
        params = {
            "query.bibliographic": query,
            "rows": 3  # Retrieve top 3 results to pick the best match
        }

        async with httpx.AsyncClient(timeout=25.0) as client:
            for attempt in range(retries):
                try:
                    logger.info(f"API request for: '{query[:40]}...' (Attempt {attempt+1}/{retries})")
                    response = await client.get(self.BASE_URL, headers=self.headers, params=params)
                    
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("message", {}).get("items", [])
                        return items
                    
                    elif response.status_code == 429:
                        # Rate limited
                        logger.warning(f"Rate limited (429) by Crossref. Backing off for {backoff}s.")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        
                    elif response.status_code >= 500:
                        # Server error
                        logger.warning(f"Crossref server error ({response.status_code}). Retrying in {backoff}s.")
                        await asyncio.sleep(backoff)
                        backoff *= 2
                        
                    else:
                        # Client errors (400, 404, etc.) - do not retry
                        logger.error(f"HTTP error {response.status_code} for query: {query}")
                        return []
                        
                except httpx.RequestError as exc:
                    logger.warning(f"Network request error: {exc}. Retrying in {backoff}s.")
                    await asyncio.sleep(backoff)
                    backoff *= 2

            logger.error(f"Failed to fetch results from Crossref after {retries} attempts.")
            return []
