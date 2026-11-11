"""Evidence validation: model claims are kept only when they cite a real, visible
document and quote text that genuinely appears in it."""

import re
from dataclasses import dataclass

from app.intelligence.docs import ContextItem, DocIndex
from app.schemas.intelligence import EvidenceRef, FactStr
from app.utils.text import norm_for_match

UNKNOWN_VALUES = {"", "unknown", "n/a", "na", "none", "not specified", "not available", "unspecified", "null"}
MIN_EXCERPT = 10
MAX_EXCERPT = 400


def is_unknown_value(v: str | None) -> bool:
    return (v or "").strip().strip(".").lower() in UNKNOWN_VALUES


def excerpt_in_content(excerpt: str, content: str) -> bool:
    parts = [norm_for_match(p) for p in re.split(r"\.\.\.|…", excerpt)]
    parts = [p for p in parts if len(p) >= MIN_EXCERPT]
    if not parts:
        return False
    hay = norm_for_match(content)
    return all(p in hay for p in parts)


def _label(raw: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", raw or "").upper()


@dataclass
class EvidenceResult:
    evidence: list[dict]
    rejected: int


def validate_evidence(refs: list[EvidenceRef], index: DocIndex, visible: set[str]) -> EvidenceResult:
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    rejected = 0
    for r in refs:
        label = _label(r.doc)
        excerpt = (r.excerpt or "").strip()[:MAX_EXCERPT]
        doc = index.labels.get(label) if label in visible else None
        if doc is None or len(norm_for_match(excerpt)) < MIN_EXCERPT or not excerpt_in_content(excerpt, doc.content):
            rejected += 1
            continue
        key = (label, norm_for_match(excerpt))
        if key in seen:
            continue
        seen.add(key)
        out.append({"document_id": str(doc.id), "source_url": doc.url, "excerpt": excerpt})
    return EvidenceResult(out, rejected)


def visible_labels(ctx: list[ContextItem]) -> set[str]:
    return {c.label for c in ctx}


@dataclass
class FinalFact:
    value: str
    classification: str
    evidence: list[dict]
    rejected: int = 0


def finalize_fact(fact: FactStr, index: DocIndex, visible: set[str]) -> FinalFact:
    """Apply the rule: no verifiable evidence => the field is `unknown`."""
    if is_unknown_value(fact.value) or fact.classification == "unknown":
        return FinalFact("unknown", "unknown", [], 0)
    res = validate_evidence(fact.evidence, index, visible)
    if not res.evidence:
        return FinalFact("unknown", "unknown", [], res.rejected + 1)
    return FinalFact(fact.value.strip()[:1200], fact.classification, res.evidence, res.rejected)
