from engine.prompts import (
    SYSTEM_TRANSLATE, SYSTEM_COMPACT,
    USER_TRANSLATE_TEMPLATE, USER_COMPACT_TEMPLATE,
    MEMO_BLOCK_TEMPLATE, GLOSSARY_BLOCK_TEMPLATE, PREV_BLOCK_TEMPLATE,
)


class ContextCollector:
    """Собирает промпт для модели, держа контекст в узде.
    book — словарь состояния книги: memo, glossary, last_original, last_translation.
    """

    # --- фильтрация глоссария ---
    @staticmethod
    def filter_glossary(glossary: dict[str, str], chunk: str) -> dict[str, str]:
        low = chunk.lower()
        return {src: dst for src, dst in glossary.items() if src.lower() in low}

    # --- блоки промпта ---
    def _memo_block(self, book: dict) -> str:
        memo = book.get("memo") or ""
        return MEMO_BLOCK_TEMPLATE.format(memo=memo) if memo.strip() else ""

    def _glossary_block(self, book: dict, chunk: str) -> str:
        filtered = self.filter_glossary(book.get("glossary", {}), chunk)
        if not filtered:
            return ""
        lines = "\n".join(f"- {src} → {dst}" for src, dst in filtered.items())
        return GLOSSARY_BLOCK_TEMPLATE.format(glossary=lines)

    def _prev_block(self, book: dict) -> str:
        orig = book.get("last_original")
        trans = book.get("last_translation")
        if not orig or not trans:
            return ""
        return PREV_BLOCK_TEMPLATE.format(prev_original=orig, prev_translation=trans)

    # --- публичные методы ---
    def build_translation_messages(self, book: dict, chunk: str) -> list[dict]:
        user = USER_TRANSLATE_TEMPLATE.format(
            memo_block=self._memo_block(book),
            glossary_block=self._glossary_block(book, chunk),
            prev_block=self._prev_block(book),
            chunk=chunk,
        )
        return [
            {"role": "system", "content": SYSTEM_TRANSLATE},
            {"role": "user", "content": user},
        ]

    def build_compaction_messages(self, book: dict, recent_paragraphs: list[dict]) -> list[dict]:
        # recent_paragraphs: [{"original": ..., "translation": ...}, ...]
        body = "\n\n".join(
            f"<original>{p['original']}</original>\n<translation>{p['translation']}</translation>"
            for p in recent_paragraphs
        )
        user = USER_COMPACT_TEMPLATE.format(paragraphs=body)
        return [
            {"role": "system", "content": SYSTEM_COMPACT},
            {"role": "user", "content": user},
        ]