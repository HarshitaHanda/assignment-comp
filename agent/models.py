from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


AccessModel = Literal[
    "self-serve",
    "self-serve-free",
    "self-serve-trial",
    "self-serve-paid",
    "admin-gated",
    "partner-gated",
    "contact-sales",
    "unknown",
]

Buildability = Literal["yes", "partial", "no", "unknown"]
MCPStatus = Literal["official", "third-party", "none-found", "unknown"]


class Evidence(BaseModel):
    url: str
    supports: str


class ResearchFinding(BaseModel):
    description: str
    auth_methods: list[str] = Field(default_factory=list)
    access_model: AccessModel
    api_surface: str
    mcp_status: MCPStatus
    buildability: Buildability
    main_blocker: str | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)


class VerificationFinding(BaseModel):
    app_id: int
    app_name: str
    fields_checked: list[str]
    matches: dict[str, bool]
    corrections: dict[str, object]
    notes: str
    evidence: list[Evidence] = Field(default_factory=list)
