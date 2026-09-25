from __future__ import annotations

from dataclasses import dataclass

from playwright.sync_api import sync_playwright

from .crawler import candidate_seed_urls


@dataclass
class BrowserPage:
    url: str
    title: str
    text: str


def render_pages(urls: list[str], max_pages: int = 8) -> list[BrowserPage]:
    """Render candidate/evidence pages in Chromium using a separate retrieval path."""
    expanded: list[str] = []
    for url in urls:
        if not url:
            continue
        expanded.append(url)
        for candidate in candidate_seed_urls(url)[:5]:
            expanded.append(candidate)

    unique_urls = list(dict.fromkeys(expanded))[:max_pages]
    pages: list[BrowserPage] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (compatible; ComposioProductOpsResearch/1.0; "
                "+https://github.com/HarshitaHanda/comp-prod-assignment)"
            )
        )
        for url in unique_urls:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(500)
                text = page.locator("body").inner_text(timeout=8_000)
                if text.strip():
                    pages.append(BrowserPage(url=page.url, title=page.title(), text=text[:50_000]))
            except Exception:
                continue
        browser.close()

    return pages


def browser_pages_as_context(pages: list[BrowserPage]) -> str:
    return "\n\n---\n\n".join(
        f"SOURCE {i}\nURL: {page.url}\nTITLE: {page.title}\nTEXT:\n{page.text}"
        for i, page in enumerate(pages, start=1)
    )
