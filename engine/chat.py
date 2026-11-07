from engine.ollama_client import OllamaClient
from engine.prompts import (
    SYSTEM_CHAT, PARA_BLOCK_TEMPLATE,
    MEMO_BLOCK_TEMPLATE, GLOSSARY_BLOCK_TEMPLATE,
    SELECTED_BLOCK_TEMPLATE,
)


class ChatEngine:
    def __init__(self, client: OllamaClient):
        self.client = client

    def _build_context(self, book: dict, paragraph: dict) -> str:
        parts = []
        if book.get("memo"):
            parts.append(MEMO_BLOCK_TEMPLATE.format(memo=book["memo"]))

        chunk = paragraph.get("chunk") or paragraph.get("original") or ""
        glossary = {k: v for k, v in book.get("glossary", {}).items()
                    if k.lower() in chunk.lower()}
        if glossary:
            lines = "\n".join(f"- {k} → {v}" for k, v in glossary.items())
            parts.append(GLOSSARY_BLOCK_TEMPLATE.format(glossary=lines))

        comment_line = f"Комментарий: {paragraph['comment']}" if paragraph.get("comment") else ""
        parts.append(PARA_BLOCK_TEMPLATE.format(
            original=paragraph.get("original") or chunk,
            translation=paragraph.get("translation") or "(перевод ещё не готов)",
            comment_line=comment_line,
        ))
        return "\n".join(parts)

    def _build_messages(self, book, paragraph, history, question, selected_text=None):
        system = SYSTEM_CHAT + "\n\n" + self._build_context(book, paragraph)
        if selected_text:
            system += "\n\n" + SELECTED_BLOCK_TEMPLATE.format(selected=selected_text)
        messages = [{"role": "system", "content": system}]
        for m in history[-10:]:
            if m.get("role") in ("user", "assistant") and m.get("content"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": question})
        return messages

    def chat_stream(self, book, paragraph, history, question, selected_text=None):
        messages = self._build_messages(book, paragraph, history, question, selected_text)
        yield from self.client.chat_stream(messages, max_tokens=800)