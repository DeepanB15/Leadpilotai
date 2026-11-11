"""Document references, labelling (D1, D2...) and controlled context selection for the LLM."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

DOC_PRIORITY = {
    "homepage": 0,
    "about_page": 1,
    "product_page": 2,
    "services_page": 3,
    "solutions_page": 4,
    "pricing_page": 5,
    "social_profile": 6,
    "video": 7,
    "post": 7,
    "contact_page": 8,
    "blog_post": 9,
    "other_page": 10,
}


@dataclass
class DocRef:
    id: uuid.UUID
    source_id: uuid.UUID
    platform: str
    url: str
    document_type: str
    title: str | None
    content: str
    collected_at: datetime
    published_at: datetime | None = None
    verification_status: str = "verified"
    source_access_status: str = "completed"
    metadata: dict = field(default_factory=dict)


@dataclass
class DocIndex:
    labels: dict[str, DocRef]
    order: list[str]

    def by_id(self) -> dict[uuid.UUID, DocRef]:
        return {d.id: d for d in self.labels.values()}


@dataclass
class ContextItem:
    label: str
    doc: DocRef
    text: str


def build_index(docs: list[DocRef]) -> DocIndex:
    def key(d: DocRef):
        pub = d.published_at.timestamp() if d.published_at else 0.0
        return (DOC_PRIORITY.get(d.document_type, 10), -pub, d.url)

    ordered = sorted(docs, key=key)
    labels = {f"D{i + 1}": d for i, d in enumerate(ordered)}
    return DocIndex(labels=labels, order=list(labels))


def select_context(index: DocIndex, budget_chars: int, per_doc_chars: int) -> list[ContextItem]:
    items: list[ContextItem] = []
    used = 0
    for label in index.order:
        doc = index.labels[label]
        text = doc.content[:per_doc_chars]
        if used + len(text) > budget_chars:
            remaining = budget_chars - used
            if remaining < 400:
                break
            text = text[:remaining]
        items.append(ContextItem(label, doc, text))
        used += len(text)
    return items
