import re

THINK_RE       = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
ORIGINAL_RE    = re.compile(r"<original>(.*?)</original>", re.DOTALL | re.IGNORECASE)
TRANSLATION_RE = re.compile(r"<translation>(.*?)</translation>", re.DOTALL | re.IGNORECASE)
COMMENT_RE     = re.compile(r"<comment>(.*?)</comment>", re.DOTALL | re.IGNORECASE)


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def parse(raw: str):
    """Возвращает {original, translation, comment} или None, если формат битый."""
    text = strip_think(raw)

    orig  = ORIGINAL_RE.search(text)
    trans = TRANSLATION_RE.search(text)
    if not orig or not trans:
        return None

    comment_match = COMMENT_RE.search(text)
    comment_text  = comment_match.group(1).strip() if comment_match else ""

    return {
        "original":    orig.group(1).strip(),
        "translation": trans.group(1).strip(),
        "comment":     comment_text or None,
    }