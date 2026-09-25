from __future__ import annotations

import heapq
import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)
DEFAULT_TIMEOUT = int(os.getenv("RESEARCH_TIMEOUT_SECONDS", "15"))
DEFAULT_MAX_PAGES = int(os.getenv("RESEARCH_MAX_PAGES", "10"))

LIKELY_DOC_WORDS = (
    "api", "developer", "developers", "auth", "authentication", "oauth",
    "token", "webhook", "integration", "mcp", "docs", "reference",
    "graphql", "rest", "sdk",
)

STRONG_DOC_PATHS = (
    "/docs/", "/api/", "/reference/", "/api-reference/", "/oauth",
    "/authentication", "/auth/", "/webhooks", "/developer", "/developers",
)

LOW_VALUE_PATHS = (
    "/blog/", "/careers/", "/customers/", "/events/", "/news/", "/press/",
)

COMMON_TWO_LEVEL_SUFFIXES = {
    "co.uk", "com.au", "co.in", "co.jp", "co.nz", "com.br", "com.sg", "com.mx",
}

USER_AGENT = (
    "Mozilla/5.0 (compatible; ComposioProductOpsResearch/1.0; "
    "+https://github.com/HarshitaHanda/comp-prod-assignment)"
)


@dataclass
class Page:
    url: str
    title: str
    text: str
    meta_description: str = ""


def _registrable_hint(hostname: str) -> str:
    host = (hostname or "").lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    parts = host.split(".")
    if len(parts) < 2:
        return host
    last_two = ".".join(parts[-2:])
    if len(parts) >= 3 and last_two in COMMON_TWO_LEVEL_SUFFIXES:
        return ".".join(parts[-3:])
    return last_two


def _is_official(seed_url: str, candidate_url: str) -> bool:
    seed = _registrable_hint(urlparse(seed_url).hostname or "")
    candidate = _registrable_hint(urlparse(candidate_url).hostname or "")
    return bool(seed and candidate and seed == candidate)


def candidate_seed_urls(seed_url: str) -> list[str]:
    """Likely official documentation entry points for a supplied official URL."""
    if not seed_url:
        return []
    normalized = seed_url.replace("http://", "https://", 1)
    parsed = urlparse(normalized)
    base = _registrable_hint(parsed.hostname or "")
    if not base:
        return [normalized]

    # The brief already provides developer URLs for many apps. Keep that exact URL
    # first, then probe common official documentation subdomains/paths.
    candidates = [
        normalized,
        f"https://developer.{base}/",
        f"https://developers.{base}/",
        f"https://docs.{base}/",
        f"https://api.{base}/",
        f"https://{base}/developers/",
        f"https://{base}/developer/",
        f"https://{base}/docs/",
        f"https://{base}/api/",
    ]

    seen: set[str] = set()
    unique: list[str] = []
    for url in candidates:
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def _clean_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    return re.sub(r"\s+", " ", " ".join(soup.stripped_strings)).strip()


def _meta_description(soup: BeautifulSoup) -> str:
    candidates = [
        soup.find("meta", attrs={"name": re.compile("^description$", re.I)}),
        soup.find("meta", attrs={"property": "og:description"}),
    ]
    for tag in candidates:
        if tag and tag.get("content"):
            return re.sub(r"\s+", " ", tag["content"]).strip()
    return ""


def _score_link(url: str, label: str) -> int:
    haystack = f"{url} {label}".lower()
    score = sum(2 for word in LIKELY_DOC_WORDS if word in haystack)

    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    path = parsed.path.lower()

    if hostname.startswith(("developer.", "developers.", "docs.", "api.")):
        score += 6
    for term in STRONG_DOC_PATHS:
        if term in path:
            score += 4
    if "oauth" in haystack:
        score += 5
    if "authentication" in haystack or "/auth" in path:
        score += 4
    if "api reference" in haystack:
        score += 5
    if "webhook" in haystack:
        score += 3
    if "mcp" in haystack or "model context protocol" in haystack:
        score += 3
    for term in LOW_VALUE_PATHS:
        if term in path:
            score -= 5
    return score


def crawl_official_docs(seed_url: str, max_pages: int | None = None) -> list[Page]:
    if not seed_url:
        return []
    max_pages = max_pages or DEFAULT_MAX_PAGES

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
    })

    queue: list[tuple[int, int, str]] = []
    queued: set[str] = set()
    visited: set[str] = set()
    pages: list[Page] = []
    sequence = 0

    def push(url: str, score: int) -> None:
        nonlocal sequence
        url = (url or "").split("#")[0]
        if not url.startswith(("http://", "https://")):
            return
        if url in queued or url in visited:
            return
        if not _is_official(seed_url, url):
            return
        sequence += 1
        queued.add(url)
        heapq.heappush(queue, (-score, sequence, url))

    for position, url in enumerate(candidate_seed_urls(seed_url)):
        push(url, 100 - position)

    while queue and len(pages) < max_pages:
        _, _, url = heapq.heappop(queue)
        queued.discard(url)
        if url in visited:
            continue
        visited.add(url)

        try:
            response = session.get(
                url,
                timeout=(5, DEFAULT_TIMEOUT),
                allow_redirects=True,
            )
            response.raise_for_status()
        except requests.RequestException:
            continue

        final_url = response.url.split("#")[0]
        if not _is_official(seed_url, final_url):
            continue

        content_type = response.headers.get("content-type", "").lower()
        if "text/html" not in content_type and "text/plain" not in content_type:
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        description = _meta_description(soup)
        text = _clean_text(soup)
        if text:
            pages.append(Page(
                url=final_url,
                title=title,
                text=text[:45_000],
                meta_description=description,
            ))

        for anchor in soup.find_all("a", href=True):
            absolute = urljoin(final_url, anchor["href"]).split("#")[0]
            if not absolute.startswith(("http://", "https://")):
                continue
            if not _is_official(seed_url, absolute):
                continue
            score = _score_link(absolute, anchor.get_text(" ", strip=True))
            if score > 0:
                push(absolute, score)

    return pages


def pages_as_context(pages: list[Page]) -> str:
    return "\n\n---\n\n".join(
        f"SOURCE {i}\nURL: {page.url}\nTITLE: {page.title}\n"
        f"DESCRIPTION: {page.meta_description}\nTEXT:\n{page.text}"
        for i, page in enumerate(pages, start=1)
    )
