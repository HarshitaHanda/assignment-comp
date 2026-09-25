from __future__ import annotations

import argparse
import json
import random
import re
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from .browser_verifier import render_pages
from .rule_extractor import extract_from_pages


ROOT = Path(__file__).resolve().parents[1]
APPS_PATH = ROOT / "data" / "apps.json"
RESULTS_PATH = ROOT / "data" / "results.json"
VERIFY_PATH = ROOT / "data" / "verification.json"
HUMAN_PATH = ROOT / "data" / "human_checks.json"

FIELDS = [
    "auth_methods",
    "access_model",
    "api_surface",
    "mcp_status",
    "buildability",
    "main_blocker",
]


def _sample(rows: list[dict], n: int) -> list[dict]:
    researched = [
        row
        for row in rows
        if row.get("status") == "researched"
    ]

    seen_categories = set()
    chosen = []

    for row in researched:
        if row["category"] not in seen_categories:
            chosen.append(row)
            seen_categories.add(row["category"])

        if len(chosen) >= n:
            return chosen

    remaining = [
        r
        for r in researched
        if r not in chosen
    ]

    random.Random(42).shuffle(remaining)

    return (chosen + remaining)[:n]


def _norm(value):
    if isinstance(value, list):
        return sorted(
            str(v).strip().lower()
            for v in value
        )

    if value is None:
        return None

    return " ".join(
        str(value).lower().split()
    )


def _surface_tokens(value) -> set[str]:
    """
    Turn API surface text such as:

    REST, Webhooks, Public API; MCP

    into comparable tokens.
    """
    if not value:
        return set()

    text = str(value).lower()

    tokens = set()

    if "rest" in text:
        tokens.add("rest")

    if "graphql" in text:
        tokens.add("graphql")

    if "webhook" in text:
        tokens.add("webhooks")

    if "public api" in text:
        tokens.add("public api")

    if re.search(r"\bmcp\b|model context protocol", text):
        tokens.add("mcp")

    return tokens


def _comparison_status(
    field: str,
    first,
    second,
) -> str:
    """
    Returns:
        support       -> browser pass agrees
        inconclusive  -> browser pass found less evidence,
                         but did not contradict first pass
        contradiction -> browser pass produced conflicting evidence
    """

    if _norm(first) == _norm(second):
        return "support"

    # Missing/unknown evidence is not a contradiction.
    if second in (None, "unknown", [], ""):
        return "inconclusive"

    # "none-found" means the second retrieval didn't locate MCP.
    # It does NOT prove MCP does not exist.
    if (
        field == "mcp_status"
        and first == "official"
        and second == "none-found"
    ):
        return "inconclusive"

    # If the browser pass finds only a subset of the first API surface,
    # treat it as incomplete retrieval rather than contradiction.
    if field == "api_surface":
        first_tokens = _surface_tokens(first)
        second_tokens = _surface_tokens(second)

        if (
            second_tokens
            and second_tokens.issubset(first_tokens)
        ):
            return "inconclusive"

    # Same logic for auth: finding fewer auth methods on the
    # second pass is not evidence that the others are false.
    if field == "auth_methods":
        first_set = set(_norm(first) or [])
        second_set = set(_norm(second) or [])

        if second_set and second_set.issubset(first_set):
            return "inconclusive"

    # A downgrade from yes -> partial/unknown caused by the
    # second crawl finding less evidence is not a contradiction.
    if field == "buildability":
        if first == "yes" and second in ("partial", "unknown"):
            return "inconclusive"

        if first == "partial" and second == "unknown":
            return "inconclusive"

    # Generic "missing evidence" blockers from the second crawl
    # do not contradict a first-pass None blocker.
    if field == "main_blocker" and first in (None, ""):
        missing_evidence_messages = [
            "A programmable surface was found, but auth or developer-access evidence is incomplete.",
            "No sufficiently explicit public API surface was found in the retrieved official pages.",
            "Official documentation could not be retrieved automatically.",
        ]

        if second in missing_evidence_messages:
            return "inconclusive"

    return "contradiction"


def run(sample_size: int = 15) -> dict:
    load_dotenv(ROOT / ".env")

    apps = {
        a["id"]: a
        for a in json.loads(
            APPS_PATH.read_text(
                encoding="utf-8"
            )
        )
    }

    rows = json.loads(
        RESULTS_PATH.read_text(
            encoding="utf-8"
        )
    )

    checks = []

    claim_total = 0
    claim_supported = 0
    claim_inconclusive = 0
    claim_contradicted = 0

    contradictions = []

    for row in _sample(
        rows,
        sample_size,
    ):
        urls = [
            e.get("url")
            for e in row.get(
                "evidence",
                [],
            )
            if e.get("url")
        ]

        if row.get("hint_url"):
            urls.append(
                row["hint_url"]
            )

        rendered = render_pages(urls)

        if not rendered:
            continue

        fresh = extract_from_pages(
            apps[row["id"]],
            rendered,
        )

        statuses = {}
        row_contradictions = {}
        row_inconclusive = {}

        for field in FIELDS:
            first = row.get(field)
            second = fresh.get(field)

            status = _comparison_status(
                field,
                first,
                second,
            )

            statuses[field] = status
            claim_total += 1

            if status == "support":
                claim_supported += 1

            elif status == "inconclusive":
                claim_inconclusive += 1

                row_inconclusive[field] = {
                    "first_pass": first,
                    "browser_pass": second,
                }

            else:
                claim_contradicted += 1

                row_contradictions[field] = second

                contradictions.append(
                    {
                        "app_id": row["id"],
                        "app_name": row["name"],
                        "field": field,
                        "before": first,
                        "after": second,
                        "reason": (
                            "Browser-rendered official evidence "
                            "produced a conflicting classification; "
                            "flagged for human review."
                        ),
                        "evidence": fresh.get(
                            "evidence",
                            [],
                        ),
                    }
                )

        if row_contradictions:
            row["needs_human_review"] = True

        checks.append(
            {
                "app_id": row["id"],
                "app_name": row["name"],
                "fields_checked": FIELDS,
                "statuses": statuses,
                "contradictions": row_contradictions,
                "inconclusive": row_inconclusive,
                "browser_confidence": fresh.get(
                    "confidence"
                ),
                "evidence": fresh.get(
                    "evidence",
                    [],
                ),
            }
        )

    RESULTS_PATH.write_text(
        json.dumps(
            rows,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    human_payload = json.loads(
        HUMAN_PATH.read_text(
            encoding="utf-8"
        )
    )

    human_checks = human_payload.get(
        "checks",
        [],
    )

    human_claims = sum(
        int(c.get("claims_checked", 0))
        for c in human_checks
    )

    human_correct = sum(
        int(
            c.get(
                "claims_correct_after_verification",
                0,
            )
        )
        for c in human_checks
    )

    conclusive_claims = (
        claim_supported
        + claim_contradicted
    )

    payload = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "sample_size": len(checks),

        "claims_checked": claim_total,

        "claims_supported": claim_supported,

        "claims_inconclusive": claim_inconclusive,

        "claims_contradicted": claim_contradicted,

        # How much of the first pass the browser pass
        # independently re-found.
        "browser_evidence_coverage": (
            round(
                claim_supported
                / claim_total,
                4,
            )
            if claim_total
            else None
        ),

        # Among claims where the browser pass gave a
        # conclusive answer, how often did it agree?
        "browser_agreement_rate": (
            round(
                claim_supported
                / conclusive_claims,
                4,
            )
            if conclusive_claims
            else None
        ),

        "human_validated_accuracy": (
            round(
                human_correct
                / human_claims,
                4,
            )
            if human_claims
            else None
        ),

        "corrections": contradictions,

        "agent_checks": checks,

        "human_checks": human_checks,
    }

    VERIFY_PATH.write_text(
        json.dumps(
            payload,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return payload


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Browser-rendered verification pass."
        )
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=15,
    )

    args = parser.parse_args()

    result = run(
        args.sample_size
    )

    print(
        json.dumps(
            {
                "sample_size": result[
                    "sample_size"
                ],
                "browser_evidence_coverage": result[
                    "browser_evidence_coverage"
                ],
                "browser_agreement_rate": result[
                    "browser_agreement_rate"
                ],
                "human_validated_accuracy": result[
                    "human_validated_accuracy"
                ],
                "inconclusive": result[
                    "claims_inconclusive"
                ],
                "contradictions": result[
                    "claims_contradicted"
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()