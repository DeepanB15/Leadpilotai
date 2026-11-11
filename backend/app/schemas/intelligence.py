"""Versioned Pydantic schemas for LLM output (company profile and insights).

Models see documents by short labels (D1, D2, ...). Labels are mapped back to real
document ids by the evidence validator; unknown labels are rejected.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field

SCHEMA_VERSION = "1.0"

Classification = Literal["observed_fact", "inference", "unknown"]
FindingType = Literal[
    "characteristic", "strength", "digital_presence", "content_theme", "announcement", "opportunity", "unknown_item"
]


def _norm_class(v):
    if not isinstance(v, str):
        return "unknown"
    s = v.strip().lower().replace(" ", "_").replace("-", "_")
    if s in ("observed_fact", "inference", "unknown"):
        return s
    if s in ("fact", "observed", "observation", "observed_facts"):
        return "observed_fact"
    if s in ("inferred", "inferences"):
        return "inference"
    return "unknown"


def _norm_type(v):
    if not isinstance(v, str):
        return "characteristic"
    s = v.strip().lower().replace(" ", "_").replace("-", "_")
    allowed = {
        "characteristic", "strength", "digital_presence", "content_theme", "announcement", "opportunity",
        "unknown_item",
    }  # fmt: skip
    return s if s in allowed else "characteristic"


Cls = Annotated[Classification, BeforeValidator(_norm_class)]
FType = Annotated[FindingType, BeforeValidator(_norm_type)]


class EvidenceRef(BaseModel):
    doc: str = ""
    excerpt: str = ""


class FactStr(BaseModel):
    value: str = "unknown"
    classification: Cls = "unknown"
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ItemStr(BaseModel):
    name: str = ""
    description: str = ""
    classification: Cls = "unknown"
    evidence: list[EvidenceRef] = Field(default_factory=list)


def _cap(max_items: int):
    def inner(v):
        return v[:max_items] if isinstance(v, list) else v

    return inner


class LLMProfile(BaseModel):
    description: FactStr = Field(default_factory=FactStr)
    industry: FactStr = Field(default_factory=FactStr)
    business_model: FactStr = Field(default_factory=FactStr)
    target_audience: Annotated[list[FactStr], BeforeValidator(_cap(8))] = Field(default_factory=list)
    products: Annotated[list[ItemStr], BeforeValidator(_cap(12))] = Field(default_factory=list)
    services: Annotated[list[ItemStr], BeforeValidator(_cap(12))] = Field(default_factory=list)
    market_positioning: FactStr = Field(default_factory=FactStr)
    digital_presence_website: FactStr = Field(default_factory=FactStr)
    digital_presence_social: FactStr = Field(default_factory=FactStr)
    content_themes: Annotated[list[FactStr], BeforeValidator(_cap(8))] = Field(default_factory=list)


class LLMFinding(BaseModel):
    type: FType = "characteristic"
    classification: Cls = "unknown"
    title: str = Field(default="", max_length=300)
    description: str = Field(default="", max_length=1500)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    contradicted: bool = False


class LLMSalesItem(BaseModel):
    text: str = ""
    based_on: list[int] = Field(default_factory=list)


class LLMInsights(BaseModel):
    findings: Annotated[list[LLMFinding], BeforeValidator(_cap(15))] = Field(default_factory=list)
    talking_points: Annotated[list[LLMSalesItem], BeforeValidator(_cap(6))] = Field(default_factory=list)
    prospect_questions: Annotated[list[LLMSalesItem], BeforeValidator(_cap(6))] = Field(default_factory=list)
    value_proposition: LLMSalesItem | None = None
    suggested_next_action: LLMSalesItem | None = None
