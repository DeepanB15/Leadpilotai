"""Company understanding: LLM profile extraction with strict validation and bounded retries."""

import json
import logging
import re
from dataclasses import dataclass

from pydantic import ValidationError

from app.core.config import Settings
from app.intelligence.docs import DocIndex, select_context
from app.intelligence.evidence_validator import FinalFact, finalize_fact, visible_labels
from app.intelligence.model_client import LLMClient, LLMError
from app.intelligence.prompt_builder import build_profile_prompt
from app.schemas.intelligence import FactStr, LLMProfile

log = logging.getLogger(__name__)


class AnalysisError(Exception):
    pass


@dataclass
class ProfileResult:
    profile_data: dict
    fields: list[dict]
    model_id: str
    rejected_claims: int
    attempts: int


def extract_json(raw: str) -> dict:
    s = raw.strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s, flags=re.I)
    start, end = s.find("{"), s.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in model output")
    data = json.loads(s[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Model output is not a JSON object")
    return data


def _field(name: str, f: FinalFact, extra: dict | None = None) -> dict:
    return {"field": name, "value": f.value, "classification": f.classification, "evidence": f.evidence, **(extra or {})}


def build_profile(llm_profile: LLMProfile, index: DocIndex, visible: set[str]) -> tuple[dict, list[dict], int]:
    fields: list[dict] = []
    rejected = 0

    def fact(name: str, f) -> FinalFact:
        nonlocal rejected
        ff = finalize_fact(f, index, visible)
        rejected += ff.rejected
        fields.append(_field(name, ff))
        return ff

    def facts(name: str, items) -> list[str]:
        nonlocal rejected
        out = []
        for it in items:
            ff = finalize_fact(it, index, visible)
            rejected += ff.rejected
            if ff.classification != "unknown":
                fields.append(_field(name, ff))
                out.append(ff.value)
        return out

    def items(name: str, lst) -> list[dict]:
        nonlocal rejected
        out = []
        for it in lst:
            if not it.name.strip():
                continue
            ff = finalize_fact(
                FactStr(value=it.name, classification=it.classification, evidence=it.evidence), index, visible
            )
            rejected += ff.rejected
            if ff.classification == "unknown":
                continue
            fields.append(_field(name, ff, {"description": it.description.strip()[:600]}))
            out.append({"name": it.name.strip()[:200], "description": it.description.strip()[:600]})
        return out

    description = fact("description", llm_profile.description)
    industry = fact("industry", llm_profile.industry)
    model = fact("business_model", llm_profile.business_model)
    audience = facts("target_audience", llm_profile.target_audience)
    products = items("product", llm_profile.products)
    services = items("service", llm_profile.services)
    positioning = fact("market_positioning", llm_profile.market_positioning)
    dp_web = fact("digital_presence.website", llm_profile.digital_presence_website)
    dp_social = fact("digital_presence.social", llm_profile.digital_presence_social)
    themes = facts("content_theme", llm_profile.content_themes)

    profile_data = {
        "company_overview": {
            "description": description.value,
            "industry": industry.value,
            "business_model": model.value,
            "target_audience": audience,
        },
        "products": products,
        "services": services,
        "market_positioning": positioning.value,
        "digital_presence": {"website": dp_web.value, "social": dp_social.value},
        "content_themes": themes,
    }
    return profile_data, fields, rejected


async def analyze_company(
    llm: LLMClient, company_name: str, domain: str, index: DocIndex, settings: Settings
) -> ProfileResult:
    ctx = select_context(index, settings.llm_context_chars, settings.llm_doc_chars)
    if not ctx:
        raise AnalysisError("No documents available for analysis")
    visible = visible_labels(ctx)
    system, user = build_profile_prompt(company_name, domain, ctx)

    feedback = ""
    last_error = ""
    for attempt in range(1, settings.llm_max_attempts + 1):
        try:
            raw = await llm.chat_json(system, user + feedback)
        except LLMError as exc:
            raise AnalysisError(str(exc)) from exc
        try:
            parsed = LLMProfile.model_validate(extract_json(raw))
            profile_data, fields, rejected = build_profile(parsed, index, visible)
            return ProfileResult(profile_data, fields, llm.model_id, rejected, attempt)
        except (ValueError, ValidationError) as exc:
            last_error = str(exc)[:300]
            log.warning("profile output invalid (attempt %s): %s", attempt, last_error)
            feedback = (
                f"\n\nYour previous output was invalid ({last_error}). "
                "Return ONLY a corrected JSON object matching the schema."
            )
    raise AnalysisError(f"Model produced invalid output after {settings.llm_max_attempts} attempts: {last_error}")
