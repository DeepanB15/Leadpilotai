"""Research insights: validated findings, deterministic confidence, grounded sales preparation."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from pydantic import ValidationError

from app.core.config import Settings
from app.intelligence.company_analyzer import AnalysisError, extract_json
from app.intelligence.confidence import score_finding
from app.intelligence.docs import DocIndex, select_context
from app.intelligence.evidence_validator import validate_evidence, visible_labels
from app.intelligence.model_client import LLMClient, LLMError
from app.intelligence.prompt_builder import build_insights_prompt
from app.schemas.intelligence import LLMInsights, LLMSalesItem

log = logging.getLogger(__name__)


@dataclass
class FindingDraft:
    id: uuid.UUID
    finding_type: str
    classification: str
    title: str
    description: str
    evidence: list[dict]
    confidence: str
    confidence_factors: dict


@dataclass
class InsightsResult:
    findings: list[FindingDraft] = field(default_factory=list)
    sales_preparation: dict = field(default_factory=dict)
    rejected_claims: int = 0
    attempts: int = 0


def _sales_item(item: LLMSalesItem | None, kept: dict[int, uuid.UUID]) -> dict | None:
    if item is None or not item.text.strip():
        return None
    ids = [str(kept[i]) for i in dict.fromkeys(item.based_on) if i in kept]
    if not ids:
        return None  # ungrounded sales content is dropped
    return {"text": item.text.strip()[:600], "based_on_findings": ids}


def build_insights(
    parsed: LLMInsights, index: DocIndex, visible: set[str], now: datetime
) -> InsightsResult:
    result = InsightsResult()
    by_id = index.by_id()
    kept: dict[int, uuid.UUID] = {}

    for pos, f in enumerate(parsed.findings, start=1):
        title, desc = f.title.strip(), f.description.strip()
        if not title or not desc:
            continue
        classification = f.classification
        ftype = f.type
        if ftype == "opportunity" and classification == "observed_fact":
            classification = "inference"  # opportunities are always hypotheses
        if ftype == "unknown_item":
            classification = "unknown"

        evidence: list[dict] = []
        if classification != "unknown":
            res = validate_evidence(f.evidence, index, visible)
            result.rejected_claims += res.rejected
            evidence = res.evidence
            if not evidence:
                result.rejected_claims += 1
                continue  # unsupported claim rejected, never presented as a finding

        docs = [by_id[uuid.UUID(e["document_id"])] for e in evidence]
        label, factors = score_finding(classification, docs, contradicted=f.contradicted, now=now)
        fid = uuid.uuid4()
        kept[pos] = fid
        result.findings.append(
            FindingDraft(
                id=fid,
                finding_type=ftype,
                classification=classification,
                title=title[:300],
                description=desc[:1500],
                evidence=evidence,
                confidence=label,
                confidence_factors=factors,
            )
        )

    result.sales_preparation = {
        "talking_points": [x for x in (_sales_item(i, kept) for i in parsed.talking_points) if x],
        "prospect_questions": [x for x in (_sales_item(i, kept) for i in parsed.prospect_questions) if x],
        "value_proposition": _sales_item(parsed.value_proposition, kept),
        "suggested_next_action": _sales_item(parsed.suggested_next_action, kept),
    }
    return result


async def generate_insights(
    llm: LLMClient,
    company_name: str,
    domain: str,
    profile_summary: dict,
    index: DocIndex,
    coverage_note: str,
    settings: Settings,
    now: datetime,
) -> InsightsResult:
    ctx = select_context(index, settings.llm_context_chars, settings.llm_doc_chars)
    visible = visible_labels(ctx)
    system, user = build_insights_prompt(company_name, domain, profile_summary, ctx, coverage_note)

    feedback = ""
    last_error = ""
    for attempt in range(1, settings.llm_max_attempts + 1):
        try:
            raw = await llm.chat_json(system, user + feedback)
        except LLMError as exc:
            raise AnalysisError(str(exc)) from exc
        try:
            parsed = LLMInsights.model_validate(extract_json(raw))
            result = build_insights(parsed, index, visible, now)
            result.attempts = attempt
            return result
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:300]
            log.warning("insights output invalid (attempt %s): %s", attempt, last_error)
            feedback = (
                f"\n\nYour previous output was invalid ({last_error}). "
                "Return ONLY a corrected JSON object matching the schema."
            )
    raise AnalysisError(f"Model produced invalid insights after {settings.llm_max_attempts} attempts: {last_error}")
