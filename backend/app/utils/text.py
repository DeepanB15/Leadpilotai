import hashlib
import re
import unicodedata

_TRANS = str.maketrans(
    {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


def normalize_whitespace(s: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def norm_for_match(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).translate(_TRANS).lower()
    return re.sub(r"\s+", " ", s).strip()


def content_hash(s: str) -> str:
    return hashlib.sha256(norm_for_match(s).encode("utf-8")).hexdigest()


def truncate(s: str, limit: int) -> tuple[str, bool]:
    if len(s) <= limit:
        return s, False
    cut = s[:limit]
    # avoid cutting mid-word where possible
    sp = cut.rfind(" ")
    if sp > limit * 0.8:
        cut = cut[:sp]
    return cut, True
