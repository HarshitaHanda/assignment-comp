from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=True)

CONFIDENCE_THRESHOLD = float(
    os.getenv("RULE_CONFIDENCE_THRESHOLD", "0.72")
)


AUTH_SIGNALS = {
    "OAuth2": [
        r"\boauth\s*2(?:\.0)?\b",
        r"\bauthorization code\b",
        r"\bclient credentials\b",
    ],
    "API key": [
        r"\bapi[- ]?key\b",
        r"\bx-api-key\b",
        r"\bapi_key\b",
        r"\bapi token\b",
    ],
    "Basic": [
        r"\bbasic authentication\b",
        r"\bbasic auth\b",
        r"\bhttp basic\b",
    ],
    "Bearer token": [
        r"\bbearer token\b",
        r"authorization:\s*bearer",
        r"\bpersonal access token\b",
        r"\bprivate app token\b",
    ],
    "JWT": [
        r"\bjwt\b",
        r"\bjson web token\b",
    ],
}


API_SIGNALS = {
    "REST": [
        r"\brest(?:ful)? api\b",
        r"\brest api reference\b",
        r"\brest endpoints?\b",
        r"/v\d+/",
    ],
    "GraphQL": [
        r"\bgraphql\b",
    ],
    "Webhooks": [
        r"\bwebhooks?\b",
    ],
    "Public API": [
        r"\bpublic api\b",
        r"\bapi reference\b",
        r"\bdeveloper api\b",
        r"\bopen apis?\b",
        r"\b\d{2,}\+?\s+apis\b",
    ],
}


MCP_SIGNALS = [
    r"\bmcp server\b",
    r"\bmodel context protocol\b",
]


ACCESS_SIGNALS = {
    "partner-gated": [
        r"partner approval (?:is )?required",
        r"requires? (?:an )?approved partner",
        r"api access (?:is )?(?:limited|restricted) to partners",
        r"available only to (?:approved )?partners",
        r"partnership (?:is )?required (?:for|to access)",
    ],

    "contact-sales": [
        r"(?:api|developer|integration) access.{0,100}contact sales",
        r"contact sales.{0,100}(?:api|developer|integration) access",
        r"(?:api|developer) access.{0,100}request access",
    ],

    "admin-gated": [
        r"admin approval",
        r"administrator approval",
        r"workspace admin.{0,100}(?:api|app|integration)",
        r"organization admin.{0,100}(?:api|app|integration)",
    ],

    "self-serve-trial": [
        r"\bfree trial\b",
        r"\bstart (?:a )?trial\b",
        r"\btrial account\b",
        r"\bdeveloper sandbox\b",
    ],

    "self-serve-free": [
        r"\bfree developer account\b",
        r"developer account.{0,100}(?:free|no cost)",
        r"\bfree developer tier\b",
        r"\bfree api tier\b",
        r"\bfree sandbox\b",
        r"\bfree (?:salesforce )?developer edition\b",
        r"developer edition.{0,100}(?:free|no cost)",
    ],

    "self-serve-paid": [
        r"(?:api|developer) access.{0,100}paid plan",
        r"(?:api|developer) access.{0,100}subscription required",
        r"available on.{0,80}(?:paid|professional|business|enterprise) plan",
    ],

    "self-serve": [
        r"(?:create|generate|obtain|get|manage|issue)\s+(?:an?\s+)?(?:api key|api token|access token|personal access token|developer token)",
        r"(?:create|register|configure)\s+(?:an?\s+)?(?:oauth app|oauth client|developer app|private app|internal integration|application|integration)",
        r"(?:sign up|register)\s+(?:for\s+)?(?:a\s+)?developer account",
        r"(?:developer|api)\s+(?:console|dashboard|portal).{0,120}(?:create|generate|register)",
        r"\bself[- ]serve\b",

        r"(?:api key|api token|access token|personal access token|developer token).{0,100}(?:create|created|generate|generated|obtain|manage|issue)",
        r"(?:oauth app|oauth client|developer app|private app|internal integration|application|integration).{0,100}(?:create|created|register|registered|configure|configured)",
        r"(?:credentials|api credentials).{0,100}(?:create|created|generate|generated|manage)",
    ],
}


SELF_SERVE_PROCEDURE_SIGNALS = [
    r"\b(?:create|generate|regenerate|issue|obtain|manage)\b.{0,100}\b(?:api key|api token|access token|personal access token|developer token|client secret|credentials)\b",

    r"\b(?:api key|api token|access token|personal access token|developer token|client secret|credentials)\b.{0,100}\b(?:create|created|generate|generated|regenerate|manage|managed|issue|issued)\b",

    r"\b(?:create|register|configure|add)\b.{0,100}\b(?:oauth app|oauth client|developer app|private app|internal integration|integration|application)\b",

    r"\b(?:oauth app|oauth client|developer app|private app|internal integration|application)\b.{0,100}\b(?:create|created|register|registered|configure|configured)\b",

    r"\b(?:settings|dashboard|console|developer portal|api portal)\b.{0,140}\b(?:api key|token|credentials|oauth app|developer app|integration)\b",

    r"\b(?:api key|token|credentials|oauth app|developer app|integration)\b.{0,140}\b(?:settings|dashboard|console|developer portal|api portal)\b",

    r"\bclick\b.{0,50}\b(?:create|generate|new)\b.{0,80}\b(?:key|token|app|integration|credentials)\b",

    r"\bnavigate to\b.{0,100}\b(?:api|developer|integration|token|credential).{0,100}\b(?:settings|dashboard|console)\b",

    r"\bpersonal access token\b.{0,120}\b(?:profile|account|settings|create|generate)\b",

    r"\bprivate app\b.{0,120}\b(?:create|configure|token)\b",

    r"\binternal integration\b.{0,120}\b(?:create|configure|token|secret)\b",
]


DEVELOPER_PAGE_HINTS = [
    r"\bapi\b",
    r"\bdeveloper",
    r"\bdocs?\b",
    r"\bauth(?:entication)?\b",
    r"\boauth\b",
    r"\btoken\b",
    r"\bintegration",
]


NO_API_SIGNALS = [
    r"\bno public api\b",
    r"does not (?:currently )?offer (?:a )?public api",
    r"api (?:is )?not available",
]


def _clean(value: str) -> str:
    return re.sub(
        r"\s+",
        " ",
        value or " ",
    ).strip()


def _clip(
    value: str,
    limit: int = 210,
) -> str:
    value = _clean(value)

    return (
        value
        if len(value) <= limit
        else value[: limit - 1].rstrip() + "…"
    )


def _first_description(
    app: dict,
    pages: Iterable[Any],
) -> str:
    for page in pages:
        desc = (
            getattr(
                page,
                "meta_description",
                "",
            )
            or ""
        )

        if len(_clean(desc)) >= 35:
            return _clip(desc)

    return (
        f"{app['name']} — {app['category']} product assessed "
        "for agent-tool integration readiness."
    )


def _matches(
    text: str,
    patterns: list[str],
) -> bool:
    return any(
        re.search(
            pattern,
            text,
            re.I | re.S,
        )
        for pattern in patterns
    )


def _supporting_urls(
    pages: Iterable[Any],
    patterns: list[str],
    limit: int = 3,
) -> list[str]:
    urls: list[str] = []

    for page in pages:
        haystack = (
            f"{getattr(page, 'url', '')} "
            f"{getattr(page, 'title', '')} "
            f"{getattr(page, 'text', '')}"
        )

        if _matches(
            haystack,
            patterns,
        ):
            url = getattr(
                page,
                "url",
                "",
            )

            if (
                url
                and url not in urls
            ):
                urls.append(url)

        if len(urls) >= limit:
            break

    return urls


def _procedural_self_serve_urls(
    pages: Iterable[Any],
    limit: int = 3,
) -> list[str]:
    """
    Find explicit official instructions showing that a developer can
    provision credentials/apps themselves.

    Broader procedural patterns are accepted only on developer/API/auth
    documentation pages to reduce false positives from marketing copy.
    """

    urls: list[str] = []

    for page in pages:
        url = (
            getattr(
                page,
                "url",
                "",
            )
            or ""
        )

        title = (
            getattr(
                page,
                "title",
                "",
            )
            or ""
        )

        text = (
            getattr(
                page,
                "text",
                "",
            )
            or ""
        )

        page_identity = (
            f"{url} {title}"
        )

        if not _matches(
            page_identity,
            DEVELOPER_PAGE_HINTS,
        ):
            continue

        if _matches(
            text,
            SELF_SERVE_PROCEDURE_SIGNALS,
        ):
            if (
                url
                and url not in urls
            ):
                urls.append(url)

        if len(urls) >= limit:
            break

    return urls


def _resolve_access(
    access_hits: dict[str, list[str]],
) -> tuple[str, bool]:

    gated = [
        model
        for model in (
            "partner-gated",
            "contact-sales",
            "admin-gated",
        )
        if access_hits.get(model)
    ]

    self_serve = [
        model
        for model in (
            "self-serve-free",
            "self-serve-trial",
            "self-serve-paid",
            "self-serve",
        )
        if access_hits.get(model)
    ]

    if (
        gated
        and self_serve
    ):
        return (
            "unknown",
            True,
        )

    if gated:
        return (
            gated[0],
            False,
        )

    if self_serve:
        return (
            self_serve[0],
            False,
        )

    return (
        "unknown",
        False,
    )


def extract_from_pages(
    app: dict,
    pages: list[Any],
) -> dict:

    joined = "\n".join(
        (
            f"{getattr(page, 'url', '')}\n"
            f"{getattr(page, 'title', '')}\n"
            f"{getattr(page, 'text', '')}"
        )
        for page in pages
    )

    evidence_by_url: dict[
        str,
        list[str],
    ] = defaultdict(list)

    auth_methods: list[str] = []

    for (
        method,
        patterns,
    ) in AUTH_SIGNALS.items():

        urls = _supporting_urls(
            pages,
            patterns,
        )

        if urls:
            auth_methods.append(
                method
            )

            for url in urls:
                evidence_by_url[
                    url
                ].append(
                    f"Authentication evidence: {method}"
                )

    surfaces: list[str] = []

    for (
        surface,
        patterns,
    ) in API_SIGNALS.items():

        urls = _supporting_urls(
            pages,
            patterns,
        )

        if urls:
            surfaces.append(
                surface
            )

            for url in urls:
                evidence_by_url[
                    url
                ].append(
                    f"Documented programmable surface: {surface}"
                )

    mcp_urls = _supporting_urls(
        pages,
        MCP_SIGNALS,
    )

    mcp_status = (
        "official"
        if mcp_urls
        else "none-found"
    )

    for url in mcp_urls:
        evidence_by_url[
            url
        ].append(
            "Official-page reference to MCP / Model Context Protocol"
        )

    access_hits: dict[
        str,
        list[str],
    ] = {}

    for model in (
        "partner-gated",
        "contact-sales",
        "admin-gated",
        "self-serve-trial",
        "self-serve-free",
        "self-serve-paid",
        "self-serve",
    ):
        patterns = (
            ACCESS_SIGNALS[
                model
            ]
        )

        urls = _supporting_urls(
            pages,
            patterns,
        )

        access_hits[
            model
        ] = urls

        for url in urls:
            evidence_by_url[
                url
            ].append(
                f"Developer access evidence: {model}"
            )

    explicit_gate_found = any(
        access_hits.get(model)
        for model in (
            "partner-gated",
            "contact-sales",
            "admin-gated",
        )
    )

    if not explicit_gate_found:
        procedural_urls = (
            _procedural_self_serve_urls(
                pages
            )
        )

        if procedural_urls:

            existing_urls = (
                access_hits.get(
                    "self-serve",
                    [],
                )
            )

            access_hits[
                "self-serve"
            ] = list(
                dict.fromkeys(
                    existing_urls
                    + procedural_urls
                )
            )

            for url in procedural_urls:
                evidence_by_url[
                    url
                ].append(
                    "Developer access evidence: "
                    "self-serve credential/app provisioning"
                )

    (
        access_model,
        access_conflict,
    ) = _resolve_access(
        access_hits
    )

    explicit_no_api = _matches(
        joined,
        NO_API_SIGNALS,
    )

    has_api = bool(
        surfaces
    )

    has_auth = bool(
        auth_methods
    )

    gated = access_model in {
        "admin-gated",
        "partner-gated",
        "contact-sales",
    }

    self_serve = access_model in {
        "self-serve",
        "self-serve-free",
        "self-serve-trial",
        "self-serve-paid",
    }

    if explicit_no_api:

        buildability = "no"

        blocker = (
            "Official material indicates no public API is available."
        )

    elif (
        has_api
        and has_auth
        and self_serve
    ):

        buildability = "yes"
        blocker = None

    elif (
        has_api
        and has_auth
        and gated
    ):

        buildability = "partial"

        blocker = (
            "Programmable surface exists, but developer access is "
            f"{access_model.replace('-', ' ')}."
        )

    elif (
        has_api
        and has_auth
    ):

        buildability = "partial"

        blocker = (
            "A programmable surface and authentication were found, "
            "but developer access could not be classified conclusively."
        )

    elif has_api:

        buildability = "partial"

        blocker = (
            "API surface found, but the authentication path was not "
            "explicit in retrieved official pages."
        )

    else:

        buildability = "unknown"

        blocker = (
            "No sufficiently explicit public API surface was found "
            "in the retrieved official pages."
        )

    confidence = 0.25

    if has_api:
        confidence += 0.22

    if has_auth:
        confidence += 0.20

    if (
        access_model
        != "unknown"
    ):
        confidence += 0.15

    if mcp_urls:
        confidence += 0.05

    if (
        len(
            evidence_by_url
        )
        >= 2
    ):
        confidence += 0.06

    if explicit_no_api:
        confidence = max(
            confidence,
            0.82,
        )

    if access_conflict:
        confidence -= 0.12

    confidence = min(
        max(
            round(
                confidence,
                2,
            ),
            0.0,
        ),
        0.95,
    )

    needs_human_review = (
        confidence
        < CONFIDENCE_THRESHOLD
        or buildability
        == "unknown"
        or access_model
        == "unknown"
        or not auth_methods
        or access_conflict
    )

    evidence = [
        {
            "url": url,
            "supports": "; ".join(
                dict.fromkeys(
                    supports
                )
            ),
        }
        for (
            url,
            supports,
        )
        in list(
            evidence_by_url.items()
        )[:8]
    ]

    api_surface = (
        ", ".join(
            surfaces
        )
        if surfaces
        else "unknown"
    )

    if (
        mcp_status
        == "official"
    ):
        api_surface = (
            f"{api_surface}; MCP"
            if api_surface
            != "unknown"
            else "MCP only found"
        )

    return {
        "description": (
            _first_description(
                app,
                pages,
            )
        ),
        "auth_methods": auth_methods,
        "access_model": access_model,
        "api_surface": api_surface,
        "mcp_status": mcp_status,
        "buildability": buildability,
        "main_blocker": blocker,
        "confidence": confidence,
        "evidence": evidence,
        "needs_human_review": (
            needs_human_review
        ),
        "classification_method": (
            "deterministic-rules"
        ),
    }