import re
from config import MAX_CHUNK_CHARS

SENT_SPLIT = re.compile(r"(?<=[.!?…])\s+")

def chunk_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []

    for p in paragraphs:
        if len(p) <= max_chars:
            chunks.append(p)
            continue

        # абзац слишком длинный — режем по границам предложений
        current = ""
        for sent in SENT_SPLIT.split(p):
            if current and len(current) + len(sent) + 1 > max_chars:
                chunks.append(current.strip())
                current = sent
            else:
                current = f"{current} {sent}".strip()
        if current:
            chunks.append(current.strip())

    return chunks