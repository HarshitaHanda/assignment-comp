from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]

load_dotenv(
    ROOT / ".env",
    override=True,
)


from .composio_enrichment import (
    load_composio_catalog,
    match_toolkit,
)

from .crawler import (
    crawl_official_docs,
    pages_as_context,
)

from .llm import (
    llm_fallback_enabled,
    research_from_context,
)

from .rule_extractor import (
    CONFIDENCE_THRESHOLD,
    extract_from_pages,
)


APPS_PATH = (
    ROOT
    / "data"
    / "apps.json"
)

RESULTS_PATH = (
    ROOT
    / "data"
    / "results.json"
)


def _checkpoint(
    apps: list[dict],
    existing: dict[int, dict],
) -> None:

    RESULTS_PATH.write_text(
        json.dumps(
            [
                existing[
                    app["id"]
                ]
                for app in apps
                if app["id"]
                in existing
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _has_programmable_surface(
    api_surface: str,
) -> bool:

    text = (
        api_surface
        or ""
    ).strip().lower()

    if (
        not text
        or text == "unknown"
        or text.startswith(
            "no explicit"
        )
        or text.startswith(
            "mcp only"
        )
    ):
        return False

    return any(
        token in text
        for token in (
            "rest",
            "graphql",
            "webhook",
            "public api",
            "api reference",
            "developer api",
        )
    )


def _merge_evidence(
    *groups: list[dict],
) -> list[dict]:

    merged: dict[
        str,
        list[str],
    ] = {}

    for group in groups:

        for item in (
            group
            or []
        ):

            url = (
                item.get(
                    "url"
                )
            )

            support = (
                item.get(
                    "supports"
                )
            )

            if not url:
                continue

            merged.setdefault(
                url,
                [],
            )

            if (
                support
                and support
                not in merged[url]
            ):
                merged[
                    url
                ].append(
                    support
                )

    return [
        {
            "url": url,
            "supports": "; ".join(
                supports
            ),
        }
        for (
            url,
            supports,
        )
        in list(
            merged.items()
        )[:8]
    ]


def _merge_fallback(
    base: dict,
    model: dict,
) -> dict:

    auth = list(
        dict.fromkeys(
            [
                *(
                    base.get(
                        "auth_methods"
                    )
                    or []
                ),
                *(
                    model.get(
                        "auth_methods"
                    )
                    or []
                ),
            ]
        )
    )

    access = (
        base.get(
            "access_model"
        )
        or "unknown"
    )

    if (
        access
        == "unknown"
        and model.get(
            "access_model"
        )
        not in (
            None,
            "unknown",
        )
    ):
        access = (
            model[
                "access_model"
            ]
        )

    api_surface = (
        base.get(
            "api_surface"
        )
        or "unknown"
    )

    if (
        not _has_programmable_surface(
            api_surface
        )
        and _has_programmable_surface(
            model.get(
                "api_surface",
                "",
            )
        )
    ):
        api_surface = (
            model[
                "api_surface"
            ]
        )

    mcp = (
        base.get(
            "mcp_status"
        )
        or "unknown"
    )

    if (
        mcp
        in {
            "unknown",
            "none-found",
        }
        and model.get(
            "mcp_status"
        )
        in {
            "official",
            "third-party",
        }
    ):
        mcp = (
            model[
                "mcp_status"
            ]
        )

    return {
        **base,

        "description": (
            base.get(
                "description"
            )
            or model.get(
                "description",
                "",
            )
        ),

        "auth_methods": auth,

        "access_model": (
            access
        ),

        "api_surface": (
            api_surface
        ),

        "mcp_status": (
            mcp
        ),

        "confidence": max(
            float(
                base.get(
                    "confidence",
                    0,
                )
            ),
            float(
                model.get(
                    "confidence",
                    0,
                )
            ),
        ),

        "evidence": (
            _merge_evidence(
                base.get(
                    "evidence",
                    [],
                ),
                model.get(
                    "evidence",
                    [],
                ),
            )
        ),
    }


def _enforce_consistency(
    finding: dict,
) -> dict:

    auth = (
        finding.get(
            "auth_methods"
        )
        or []
    )

    access = (
        finding.get(
            "access_model"
        )
        or "unknown"
    )

    api = (
        finding.get(
            "api_surface"
        )
        or "unknown"
    )

    has_api = (
        _has_programmable_surface(
            api
        )
    )

    gated = (
        access
        in {
            "admin-gated",
            "partner-gated",
            "contact-sales",
        }
    )

    self_serve = (
        access
        in {
            "self-serve",
            "self-serve-free",
            "self-serve-trial",
            "self-serve-paid",
        }
    )

    if (
        has_api
        and auth
        and self_serve
    ):

        buildability = "yes"
        blocker = None

    elif (
        has_api
        and gated
    ):

        buildability = (
            "partial"
        )

        blocker = (
            "Programmable surface exists, "
            "but developer access appears "
            f"{access.replace('-', ' ')}."
        )

    elif has_api:

        buildability = (
            "partial"
        )

        blocker = (
            "A programmable surface was found, "
            "but auth or developer-access evidence "
            "is incomplete."
        )

    else:

        buildability = (
            "no"
            if finding.get(
                "buildability"
            )
            == "no"
            else "unknown"
        )

        blocker = (
            "Official material explicitly indicates "
            "no public API is available."
            if buildability
            == "no"
            else (
                "No sufficiently explicit public API "
                "surface was found in the retrieved "
                "official pages."
            )
        )

    confidence = float(
        finding.get(
            "confidence",
            0,
        )
    )

    needs_review = (
        confidence
        < CONFIDENCE_THRESHOLD
        or buildability
        == "unknown"
        or access
        == "unknown"
        or not auth
        or not finding.get(
            "evidence"
        )
    )

    if needs_review:

        confidence = min(
            confidence,
            CONFIDENCE_THRESHOLD
            - 0.03,
        )

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

    return {
        **finding,

        "buildability": (
            buildability
        ),

        "main_blocker": (
            blocker
        ),

        "needs_human_review": (
            needs_review
        ),

        "confidence": (
            confidence
        ),
    }


def run(
    limit: int | None = None,
    start: int = 1,
) -> list[dict]:

    load_dotenv(
        ROOT / ".env",
        override=True,
    )

    apps = json.loads(
        APPS_PATH.read_text(
            encoding="utf-8"
        )
    )

    current_rows = (
        json.loads(
            RESULTS_PATH.read_text(
                encoding="utf-8"
            )
        )
    )

    existing = {
        item["id"]: item
        for item in current_rows
    }

    selected = [
        app
        for app in apps
        if app["id"]
        >= start
    ]

    if limit is not None:

        selected = (
            selected[:limit]
        )

    try:

        catalog = (
            load_composio_catalog()
        )

    except Exception as exc:

        print(
            "[warn] Composio catalog "
            "enrichment unavailable: "
            f"{exc}"
        )

        catalog = []

    for (
        idx,
        app,
    ) in enumerate(
        selected,
        start=1,
    ):

        print(
            f"[{idx}/{len(selected)}] "
            f"Researching "
            f"{app['name']}..."
        )

        pages = (
            crawl_official_docs(
                app.get(
                    "hint_url",
                    "",
                )
            )
        )

        if not pages:

            existing[
                app["id"]
            ] = {
                **app,

                "status": (
                    "researched"
                ),

                "retrieval_status": (
                    "failed"
                ),

                "needs_human_review": (
                    True
                ),

                "classification_method": (
                    "retrieval-failed"
                ),

                "fallback_attempts": [],

                "research_note": (
                    "Could not retrieve usable "
                    "official source text."
                ),

                "auth_methods": [],

                "access_model": (
                    "unknown"
                ),

                "api_surface": (
                    "unknown"
                ),

                "mcp_status": (
                    "unknown"
                ),

                "buildability": (
                    "unknown"
                ),

                "main_blocker": (
                    "Official documentation could "
                    "not be retrieved automatically."
                ),

                "confidence": (
                    0.0
                ),

                "evidence": [],

                "composio_toolkit": (
                    match_toolkit(
                        app[
                            "name"
                        ],
                        catalog,
                    )
                    if catalog
                    else None
                ),

                "researched_at": (
                    datetime.now(
                        timezone.utc
                    ).isoformat()
                ),
            }

            _checkpoint(
                apps,
                existing,
            )

            continue

        finding = (
            extract_from_pages(
                app,
                pages,
            )
        )

        attempts: list[
            dict
        ] = []

        if (
            llm_fallback_enabled()
            and finding[
                "needs_human_review"
            ]
        ):

            print(
                "  -> Rules need review "
                f"(confidence="
                f"{finding['confidence']:.2f}); "
                "trying LLM fallback..."
            )

            try:

                (
                    model_finding,
                    provider,
                    attempts,
                ) = (
                    research_from_context(
                        app,

                        pages_as_context(
                            pages
                        ),

                        first_pass=(
                            finding
                        ),

                        confidence_threshold=(
                            CONFIDENCE_THRESHOLD
                        ),
                    )
                )

                model_dict = (
                    model_finding
                    .model_dump()
                )

                finding = (
                    _merge_fallback(
                        finding,
                        model_dict,
                    )
                )

                finding[
                    "classification_method"
                ] = (
                    f"rules+"
                    f"{provider}"
                    f"-fallback"
                )

                print(
                    f"  -> {provider} "
                    "fallback returned "
                    "confidence="
                    f"{model_dict.get('confidence', 0):.2f}"
                )

            except Exception as exc:

                attempts = [
                    {
                        "status": (
                            "failed"
                        ),

                        "reason": (
                            type(
                                exc
                            ).__name__
                        ),
                    }
                ]

                finding[
                    "llm_fallback_note"
                ] = (
                    "Fallback failed: "
                    f"{type(exc).__name__}"
                )

                print(
                    "  -> LLM fallback "
                    "failed: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )

        finding[
            "fallback_attempts"
        ] = attempts

        finding = (
            _enforce_consistency(
                finding
            )
        )

        row = {
            **app,
            **finding,

            "status": (
                "researched"
            ),

            "retrieval_status": (
                "ok"
            ),

            "composio_toolkit": (
                match_toolkit(
                    app["name"],
                    catalog,
                )
                if catalog
                else None
            ),

            "researched_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        }

        existing[
            app["id"]
        ] = row

        _checkpoint(
            apps,
            existing,
        )

    return [
        existing[
            app["id"]
        ]
        for app in apps
        if app["id"]
        in existing
    ]


def main() -> None:

    parser = (
        argparse.ArgumentParser(
            description=(
                "Research the 100-app "
                "integration set."
            )
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--start",
        type=int,
        default=1,
    )

    args = (
        parser.parse_args()
    )

    run(
        limit=args.limit,
        start=args.start,
    )


if __name__ == "__main__":
    main()