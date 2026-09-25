from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv

from .models import ResearchFinding


ROOT = Path(
    __file__
).resolve().parents[1]


load_dotenv(
    ROOT / ".env",
    override=True,
)


RESEARCH_SYSTEM = """
You are a skeptical API integration researcher.

Use ONLY the official source text supplied by the caller.
Do not use outside knowledge.

Your job is to resolve missing or ambiguous integration-research
fields, not to make the app look buildable.

Rules:

- Treat generic marketing phrases such as "contact sales",
  "partner program", or product pricing as irrelevant unless
  the supplied text explicitly ties them to API/developer access.

- buildability="yes" requires:
    1. a documented programmable API surface,
    2. a realistic authentication path,
    3. developer access that is not clearly gated.

- MCP by itself is NOT enough to claim API buildability.

- If auth, developer access, or API surface is not directly
  supported, use unknown/empty rather than guessing.

- access_model must describe API/developer access, not whether
  an SDK/library is open source.

- "self-serve" means a developer can provision credentials,
  register an app/integration, or create an OAuth client without
  sales, partner, or admin approval.

- The exact pricing tier does not need to be known for generic
  "self-serve".

- For access_model, classify "self-serve" when official docs
  explicitly show that a developer can create or generate API
  credentials, tokens, OAuth apps, private apps, internal
  integrations, or developer applications through settings,
  a dashboard, console, or developer portal without requiring
  sales, partner, or admin approval.

- Do NOT infer self-serve merely because an API exists.

- Evidence URLs MUST be among the supplied source URLs.

- Evidence should directly support the integration claim.

- "none-found" means no official MCP reference was found in the
  supplied pages. It does not prove that MCP does not exist elsewhere.

Return concise findings suitable for audit and human review.
""".strip()


RELEVANT_TERMS = re.compile(
    r"oauth|"
    r"api[- ]?key|"
    r"api token|"
    r"access token|"
    r"bearer|"
    r"basic auth|"
    r"jwt|"
    r"rest|"
    r"graphql|"
    r"webhook|"
    r"mcp|"
    r"model context protocol|"
    r"developer|"
    r"partner|"
    r"admin|"
    r"contact sales|"
    r"sandbox|"
    r"trial|"
    r"free plan|"
    r"paid plan|"
    r"public api|"
    r"api reference|"
    r"developer account|"
    r"developer app|"
    r"oauth app|"
    r"oauth client|"
    r"create|"
    r"generate|"
    r"register|"
    r"configure|"
    r"credentials|"
    r"settings|"
    r"dashboard|"
    r"console|"
    r"developer portal|"
    r"api portal|"
    r"personal access token|"
    r"private app|"
    r"internal integration",
    re.I,
)


def llm_fallback_enabled() -> bool:

    return (
        os.getenv(
            "USE_LLM_FALLBACK",
            "false",
        )
        .strip()
        .lower()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def _provider_order() -> list[str]:

    raw = os.getenv(
        "LLM_FALLBACK_ORDER",
        "bazaar,groq,gemini",
    )

    order = [
        item.strip().lower()
        for item
        in raw.split(",")
        if item.strip()
    ]

    allowed = {
        "bazaar",
        "groq",
        "gemini",
    }

    return [
        item
        for item
        in order
        if item
        in allowed
    ]


def _compact_source_context(
    source_context: str,
    max_chars: int = 24_000,
) -> str:

    blocks = re.split(
        r"\n\n---\n\n",
        source_context,
    )

    compact: list[
        str
    ] = []

    per_block = max(
        2_500,

        max_chars
        // max(
            len(
                blocks
            ),
            1,
        ),
    )

    for block in blocks:

        if (
            len(block)
            <= per_block
        ):

            compact.append(
                block
            )

            continue

        header = (
            block[
                :1_200
            ]
        )

        windows: list[
            str
        ] = []

        used = 0

        for match in (
            RELEVANT_TERMS
            .finditer(
                block
            )
        ):

            start = max(
                0,

                match.start()
                - 420,
            )

            end = min(
                len(
                    block
                ),

                match.end()
                + 900,
            )

            snippet = (
                block[
                    start:end
                ]
            )

            if (
                snippet
                not in windows
            ):

                windows.append(
                    snippet
                )

                used += len(
                    snippet
                )

            if (
                used
                >= per_block
                - len(
                    header
                )
            ):

                break

        body = (
            "\n...\n"
            .join(
                windows
            )
        )

        compact.append(
            (
                header
                + "\n...\n"
                + body
            )[
                :per_block
            ]
        )

    return (
        "\n\n---\n\n"
        .join(
            compact
        )
    )[
        :max_chars
    ]


def _allowed_urls(
    source_context: str,
) -> set[str]:

    return set(
        re.findall(
            r"^URL:\s*(https?://\S+)",
            source_context,
            flags=re.M,
        )
    )


def _sanitize_finding(
    finding: ResearchFinding,
    source_context: str,
) -> ResearchFinding:

    allowed = (
        _allowed_urls(
            source_context
        )
    )

    finding.evidence = [
        evidence
        for evidence
        in finding.evidence
        if evidence.url
        in allowed
    ]

    if not finding.evidence:

        finding.confidence = min(
            finding.confidence,
            0.62,
        )

    return finding


def _has_programmable_surface(
    api_surface: str,
) -> bool:

    text = (
        api_surface
        or ""
    ).strip().lower()

    if (
        not text
        or text
        == "unknown"
        or text.startswith(
            "no explicit"
        )
        or text.startswith(
            "mcp only"
        )
    ):

        return False

    return any(
        token
        in text
        for token
        in (
            "rest",
            "graphql",
            "webhook",
            "public api",
            "api reference",
            "developer api",
        )
    )


def _usable_finding(
    finding: ResearchFinding,
    threshold: float,
) -> bool:

    if (
        finding.confidence
        < threshold
    ):

        return False

    if (
        not finding.evidence
    ):

        return False

    if (
        finding.buildability
        == "no"
    ):

        return True

    if (
        finding.access_model
        == "unknown"
    ):

        return False

    if (
        finding.buildability
        == "yes"
    ):

        if (
            not finding.auth_methods
        ):

            return False

        if (
            not _has_programmable_surface(
                finding.api_surface
            )
        ):

            return False

        if (
            finding.access_model
            in {
                "admin-gated",
                "partner-gated",
                "contact-sales",
            }
        ):

            return False

    if (
        finding.buildability
        == "partial"
        and not (
            _has_programmable_surface(
                finding.api_surface
            )
        )
    ):

        return False

    return True


def _prompt(
    app: dict,
    source_context: str,
    first_pass: dict | None = None,
) -> str:

    first = json.dumps(
        first_pass
        or {},
        ensure_ascii=False,
    )

    return f"""
Research this app from the supplied official pages only.

APP:
{json.dumps(app, ensure_ascii=False)}

DETERMINISTIC FIRST PASS:
{first}

OFFICIAL SOURCE MATERIAL:
{_compact_source_context(source_context)}

Resolve missing or ambiguous fields only where the supplied
official source supports them.

Pay special attention to developer-access evidence such as:

- creating/generating API keys or tokens,
- creating an internal/private app,
- registering an OAuth client/application,
- developer-console or dashboard instructions,
- explicit sales/partner/admin approval requirements.

Do not discard correct deterministic findings merely because
one page does not repeat them.

If the evidence is insufficient, prefer unknown.

Return exactly the fields required by the schema.
""".strip()


def _extract_json_text(
    content: str,
) -> str:

    content = (
        content
        or "{}"
    ).strip()

    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.I,
    )

    content = re.sub(
        r"\s*```$",
        "",
        content,
        flags=re.I,
    )

    content = (
        content.strip()
    )

    first_brace = (
        content.find(
            "{"
        )
    )

    last_brace = (
        content.rfind(
            "}"
        )
    )

    if (
        first_brace
        != -1
        and last_brace
        != -1
        and last_brace
        > first_brace
    ):

        content = (
            content[
                first_brace:
                last_brace
                + 1
            ]
        )

    return content


def _bazaar_fallback(
    app: dict,
    source_context: str,
    first_pass: dict | None = None,
) -> ResearchFinding:

    if not os.getenv(
        "BAZAARLINK_API_KEY"
    ):

        raise RuntimeError(
            "BAZAARLINK_API_KEY "
            "is not set"
        )

    try:

        from openai import OpenAI

    except ImportError as exc:

        raise RuntimeError(
            "Install OpenAI SDK: "
            "pip install openai"
        ) from exc

    client = OpenAI(
        api_key=(
            os.environ[
                "BAZAARLINK_API_KEY"
            ]
        ),

        base_url=(
            "https://api.bazaarlink.ai/v1"
        ),

        timeout=40.0,
    )

    model = os.getenv(
        "BAZAARLINK_MODEL",
        "auto:free",
    )

    schema = (
        ResearchFinding
        .model_json_schema()
    )

    user_prompt = f"""
{_prompt(app, source_context, first_pass)}

Return ONLY valid JSON.

Do not include markdown fences.

Do not include explanations outside the JSON.

The JSON must conform to this schema:

{json.dumps(schema, ensure_ascii=False)}
""".strip()

    response = (
        client.chat.completions.create(
            model=model,

            messages=[
                {
                    "role": "system",

                    "content": (
                        RESEARCH_SYSTEM
                    ),
                },

                {
                    "role": "user",

                    "content": (
                        user_prompt
                    ),
                },
            ],

            temperature=0,

            extra_headers={
                "X-Free-Fallback": (
                    "false"
                ),
            },
        )
    )

    content = (
        response
        .choices[0]
        .message
        .content
        or "{}"
    )

    content = (
        _extract_json_text(
            content
        )
    )

    finding = (
        ResearchFinding
        .model_validate_json(
            content
        )
    )

    return (
        _sanitize_finding(
            finding,
            source_context,
        )
    )


def _groq_fallback(
    app: dict,
    source_context: str,
    first_pass: dict | None = None,
) -> ResearchFinding:

    if not os.getenv(
        "GROQ_API_KEY"
    ):

        raise RuntimeError(
            "GROQ_API_KEY "
            "is not set"
        )

    try:

        from groq import Groq

    except ImportError as exc:

        raise RuntimeError(
            "Install fallback dependencies: "
            "pip install -r "
            "requirements-llm.txt"
        ) from exc

    client = Groq(
        api_key=(
            os.environ[
                "GROQ_API_KEY"
            ]
        )
    )

    model = os.getenv(
        "GROQ_MODEL",
        "openai/gpt-oss-20b",
    )

    schema = (
        ResearchFinding
        .model_json_schema()
    )

    response = (
        client.chat.completions.create(
            model=model,

            messages=[
                {
                    "role": "system",

                    "content": (
                        RESEARCH_SYSTEM
                    ),
                },

                {
                    "role": "user",

                    "content": (
                        _prompt(
                            app,
                            source_context,
                            first_pass,
                        )
                    ),
                },
            ],

            response_format={
                "type": (
                    "json_schema"
                ),

                "json_schema": {
                    "name": (
                        "research_finding"
                    ),

                    "strict": (
                        False
                    ),

                    "schema": (
                        schema
                    ),
                },
            },

            temperature=0,
        )
    )

    content = (
        response
        .choices[0]
        .message
        .content
        or "{}"
    )

    content = (
        _extract_json_text(
            content
        )
    )

    finding = (
        ResearchFinding
        .model_validate_json(
            content
        )
    )

    return (
        _sanitize_finding(
            finding,
            source_context,
        )
    )


def _gemini_fallback(
    app: dict,
    source_context: str,
    first_pass: dict | None = None,
) -> ResearchFinding:

    if not os.getenv(
        "GEMINI_API_KEY"
    ):

        raise RuntimeError(
            "GEMINI_API_KEY "
            "is not set"
        )

    try:

        from google import genai
        from google.genai import types

    except ImportError as exc:

        raise RuntimeError(
            "Install fallback dependencies: "
            "pip install -r "
            "requirements-llm.txt"
        ) from exc

    client = genai.Client(
        api_key=(
            os.environ[
                "GEMINI_API_KEY"
            ]
        )
    )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.8-flash",
    )

    response = (
        client.models.generate_content(
            model=model,

            contents=(
                f"{RESEARCH_SYSTEM}\n\n"
                f"{_prompt(app, source_context, first_pass)}"
            ),

            config=(
                types.GenerateContentConfig(
                    response_mime_type=(
                        "application/json"
                    ),

                    response_schema=(
                        ResearchFinding
                    ),

                    temperature=0,
                )
            ),
        )
    )

    content = (
        _extract_json_text(
            response.text
            or "{}"
        )
    )

    finding = (
        ResearchFinding
        .model_validate_json(
            content
        )
    )

    return (
        _sanitize_finding(
            finding,
            source_context,
        )
    )


FallbackCallable = Callable[
    [
        dict,
        str,
        dict | None,
    ],
    ResearchFinding,
]


PROVIDERS: dict[
    str,
    FallbackCallable,
] = {
    "bazaar": (
        _bazaar_fallback
    ),

    "groq": (
        _groq_fallback
    ),

    "gemini": (
        _gemini_fallback
    ),
}


def research_from_context(
    app: dict,
    source_context: str,
    first_pass: dict | None = None,
    confidence_threshold: float = 0.72,
) -> tuple[
    ResearchFinding,
    str,
    list[dict],
]:

    load_dotenv(
        ROOT / ".env",
        override=True,
    )

    if not (
        llm_fallback_enabled()
    ):

        raise RuntimeError(
            "LLM fallback is disabled"
        )

    attempts: list[
        dict
    ] = []

    last_finding: (
        ResearchFinding
        | None
    ) = None

    last_provider: (
        str
        | None
    ) = None

    key_names = {
        "bazaar": (
            "BAZAARLINK_API_KEY"
        ),

        "groq": (
            "GROQ_API_KEY"
        ),

        "gemini": (
            "GEMINI_API_KEY"
        ),
    }

    for provider in (
        _provider_order()
    ):

        key_name = (
            key_names[
                provider
            ]
        )

        if not os.getenv(
            key_name
        ):

            attempts.append(
                {
                    "provider": (
                        provider
                    ),

                    "status": (
                        "skipped"
                    ),

                    "reason": (
                        f"{key_name} "
                        "missing"
                    ),
                }
            )

            print(
                f"  -> {provider} "
                "skipped "
                f"({key_name} missing)"
            )

            continue

        try:

            finding = (
                PROVIDERS[
                    provider
                ](
                    app,
                    source_context,
                    first_pass,
                )
            )

            usable = (
                _usable_finding(
                    finding,
                    confidence_threshold,
                )
            )

            attempts.append(
                {
                    "provider": (
                        provider
                    ),

                    "status": (
                        "success"
                    ),

                    "confidence": (
                        finding.confidence
                    ),

                    "evidence_count": (
                        len(
                            finding.evidence
                        )
                    ),

                    "standalone_usable": (
                        usable
                    ),
                }
            )

            last_finding = (
                finding
            )

            last_provider = (
                provider
            )

            if usable:

                return (
                    finding,
                    provider,
                    attempts,
                )

            print(
                f"  -> {provider} "
                "returned confidence="
                f"{finding.confidence:.2f} "
                "but remained ambiguous; "
                "trying next provider..."
            )

        except Exception as exc:

            attempts.append(
                {
                    "provider": (
                        provider
                    ),

                    "status": (
                        "failed"
                    ),

                    "reason": (
                        type(
                            exc
                        ).__name__
                    ),
                }
            )

            print(
                f"  -> {provider} "
                "failed: "
                f"{type(exc).__name__}; "
                "trying next provider..."
            )

    if (
        last_finding
        is not None
        and last_provider
        is not None
    ):

        return (
            last_finding,
            last_provider,
            attempts,
        )

    raise RuntimeError(
        "No fallback provider "
        "succeeded: "
        f"{attempts}"
    )