from pathlib import Path
from engine.parser import parse
from config import PARSE_RETRY, DEBUG_DIR


class TranslatorEngine:
    def __init__(self, client, collector):
        self.client = client
        self.collector = collector
        Path(DEBUG_DIR).mkdir(parents=True, exist_ok=True)

    def _estimate_max_tokens(self, chunk: str) -> int:
        # Русский длиннее английского, + теги, + комментарий. С запасом.
        return max(1500, len(chunk) + 800)

    def translate_paragraph(self, book: dict, chunk: str, model: str = None,
                            debug: bool = True) -> dict:
        # Если модель не передана — берём из клиента (там дефолт из config)
        if model is None:
            model = getattr(self.client, "model", None)

        messages = self.collector.build_translation_messages(book, chunk)
        max_tokens = self._estimate_max_tokens(chunk)

        if debug:
            print(f"[engine] модель={model} чанк={len(chunk)} симв. "
                  f"лимит={max_tokens} токенов", flush=True)

        for attempt in range(PARSE_RETRY + 1):
            try:
                raw = self.client.chat(messages, max_tokens=max_tokens, debug=debug)
            except Exception as e:
                return {"original": chunk, "translation": None,
                        "comment": None, "error": f"ollama: {e}",
                        "model": model}

            if debug and self.client.last_stats.get("done_reason") == "length":
                print(f"⚠ Обрезано по лимиту ({max_tokens} токенов, "
                      f"{len(raw)} символов)", flush=True)

            parsed = parse(raw)
            if parsed:
                book["last_original"]    = parsed["original"]
                book["last_translation"] = parsed["translation"]
                return {**parsed, "error": None, "model": model}

            dump_path = Path(DEBUG_DIR) / f"raw_attempt_{attempt}.txt"
            dump_path.write_text(raw, encoding="utf-8")
            if debug:
                print(f"⚠ Парсинг не удался. Сырой ответ: {dump_path}", flush=True)

            if attempt < PARSE_RETRY:
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Ты нарушил формат. Повтори строго в тегах "
                               "<original>, <translation>, <comment>. "
                               "Без текста вне тегов.",
                })

        return {"original": chunk, "translation": None,
                "comment": None, "error": "parse_failed", "model": model}

    def compact(self, book: dict, recent_paragraphs: list[dict]) -> str:
        messages = self.collector.build_compaction_messages(book, recent_paragraphs)
        try:
            return self.client.chat(messages, max_tokens=600, debug=False).strip()
        except Exception:
            return book.get("memo") or ""