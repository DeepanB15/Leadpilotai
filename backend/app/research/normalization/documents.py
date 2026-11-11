from dataclasses import dataclass, field
from datetime import datetime

from app.utils.text import content_hash


@dataclass
class NormalizedDoc:
    document_type: str
    url: str
    content: str
    title: str | None = None
    published_at: datetime | None = None
    metadata: dict = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return content_hash(self.content)
