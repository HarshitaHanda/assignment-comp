from __future__ import annotations

import re
from typing import Any

from composio import Composio


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    return vars(value)


def _items_and_cursor(response: Any) -> tuple[list[dict], str | None]:
    data = _as_dict(response)
    raw_items = data.get("items") or data.get("toolkits") or data.get("data") or []
    items = [_as_dict(item) for item in raw_items]
    cursor = data.get("next_cursor") or data.get("nextCursor") or data.get("cursor")
    return items, cursor


def load_composio_catalog() -> list[dict]:
    """Load the project's visible Composio toolkit catalog using the official SDK."""
    composio = Composio()
    catalog: list[dict] = []
    cursor = None

    for _ in range(20):
        response = composio.toolkits.list(
            limit=1000,
            cursor=cursor,
            sort_by="alphabetically",
            managed_by="all",
        )
        items, next_cursor = _items_and_cursor(response)
        catalog.extend(items)
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor

    return catalog


def match_toolkit(app_name: str, catalog: list[dict]) -> dict | None:
    """Match conservatively: exact normalized name/slug or explicit safe alias only."""
    target = _norm(app_name)
    aliases = {
        "larklarksuite": ["lark", "larksuite"],
        "whatsappbusiness": ["whatsapp", "whatsappbusiness"],
        "salesforcecommercecloud": ["salesforcecommercecloud"],
        "amazonsellingpartner": ["amazonsellingpartner", "amazonspapi"],
        "mondaycom": ["monday", "mondaycom"],
        "mongodbatlas": ["mongodbatlas"],
        "youtubetranscript": ["youtubetranscript"],
        "zohocrm": ["zohocrm"],
        "zohocliq": ["zohocliq"],
    }
    candidates = {target, *aliases.get(target, [])}

    best = None
    for toolkit in catalog:
        name = _norm(str(toolkit.get("name") or ""))
        slug = _norm(str(toolkit.get("slug") or toolkit.get("id") or ""))
        if name in candidates or slug in candidates:
            best = toolkit
            break

    if best is None:
        return None

    meta = _as_dict(best.get("meta") or {})
    categories = meta.get("categories") or best.get("categories") or best.get("category")
    return {
        "name": best.get("name"),
        "slug": best.get("slug") or best.get("id"),
        "categories": categories,
        "tools_count": meta.get("tools_count") or meta.get("toolsCount"),
        "triggers_count": meta.get("triggers_count") or meta.get("triggersCount"),
    }
