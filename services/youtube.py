"""wrapper around the YouTube Data API v3 for fetching educational
video metadata. Designed to be called by /recommend_videos.

Public function:
    search_videos(query: str, max_results: int = 5) -> list[dict]
        Returns a list of { video_id, title, channel, thumbnail }.
"""
from __future__ import annotations

import logging
from typing import List, Dict

import requests

logger = logging.getLogger(__name__)

_API_KEY = "AIzaSyArXgygP12FK7W9bN4JJagnEIeRTMZ0sxk"
_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"

if not _API_KEY:
    logger.warning("YOUTUBE_API_KEY is not set – YouTube searches will fail.")


def _build_params(query: str, max_results: int) -> dict:
    """Build query parameters for the search endpoint."""
    return {
        "part"       : "snippet",
        "q"          : query,
        "type"       : "video",
        "maxResults" : max_results,
        "safeSearch" : "moderate",   # ← relaxed from "strict"
        "key"        : _API_KEY,
    }


def search_videos(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Search YouTube for *query* and return a simplified list of results.

    If the API key is missing or an HTTP error occurs, an empty list is
    returned and the issue is logged (so /recommend_videos can degrade
    gracefully rather than crashing).
    """
    if not _API_KEY:
        return []

    try:
        resp = requests.get(
            _SEARCH_URL,
            params=_build_params(query, max_results),
            timeout=8,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network / JSON / HTTP errors
        logger.error("YouTube API call failed: %s", exc)
        return []

    results: List[Dict[str, str]] = []
    for item in data.get("items", []):
        vid = item.get("id", {}).get("videoId")
        if not vid:
            continue
        snippet = item.get("snippet", {})
        results.append(
            {
                "video_id" : vid,
                "title"    : snippet.get("title", "(no title)")[:120],
                "channel"  : snippet.get("channelTitle", ""),
                "thumbnail": (
                    snippet.get("thumbnails", {})
                           .get("high", {})
                           .get("url")
                    or snippet.get("thumbnails", {})
                              .get("default", {})
                              .get("url", "")
                ),
            }
        )

    return results
