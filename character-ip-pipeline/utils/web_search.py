"""Web search utility — supports multiple search backends."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote


class WebSearcher:
    """Web search abstraction with multiple backend support."""

    def __init__(self, api: str = "tavily", api_key: str = ""):
        self.api = api
        self.api_key = api_key

    def search(self, query: str, max_results: int = 10) -> list[dict]:
        """Search the web and return results."""
        if self.api == "tavily":
            return self._search_tavily(query, max_results)
        elif self.api == "serpapi":
            return self._search_serpapi(query, max_results)
        elif self.api == "duckduckgo":
            return self._search_duckduckgo(query, max_results)
        else:
            raise ValueError(f"Unknown search API: {self.api}")

    def _search_tavily(self, query: str, max_results: int) -> list[dict]:
        """Search using Tavily API."""
        import urllib.request

        url = "https://api.tavily.com/search"
        data = json.dumps({
            "api_key": self.api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "advanced",
        }).encode()
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req) as resp:
                result = json.loads(resp.read())
            return result.get("results", [])
        except Exception as e:
            raise RuntimeError(f"Tavily search failed: {e}")

    def _search_serpapi(self, query: str, max_results: int) -> list[dict]:
        """Search using SerpAPI."""
        import urllib.request

        url = f"https://serpapi.com/search?q={quote(query)}&api_key={self.api_key}&num={max_results}"
        try:
            with urllib.request.urlopen(url) as resp:
                result = json.loads(resp.read())
            organic = result.get("organic_results", [])
            return [
                {"title": r.get("title", ""), "content": r.get("snippet", ""), "url": r.get("link", "")}
                for r in organic
            ]
        except Exception as e:
            raise RuntimeError(f"SerpAPI search failed: {e}")

    def _search_duckduckgo(self, query: str, max_results: int) -> list[dict]:
        """Search using DuckDuckGo (free, no API key needed)."""
        try:
            from duckduckgo_search import DDGS
        except ImportError:
            raise ImportError("Install duckduckgo-search: pip install duckduckgo-search")

        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "content": r.get("body", ""),
                    "url": r.get("href", ""),
                })
        return results
