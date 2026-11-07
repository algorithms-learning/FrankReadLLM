from engine.ollama_client import OllamaClient
from engine.prompts import SYSTEM_ANKI, USER_ANKI_TEMPLATE


class AnkiEngine:
    BATCH_SIZE = 5

    def __init__(self, client: OllamaClient, tag: str = "frank_reader"):
        self.client = client
        self.tag = tag

    @staticmethod
    def _clean_field(s: str) -> str:
        # внутри поля запятая безопаснее точки с запятой
        return s.replace(";", ",").replace("\n", " ").strip()

    def _parse_line(self, line: str):
        line = line.strip()
        if not line or line.count(";") < 1:
            return None
        parts = [p.strip() for p in line.split(";")]
        word = parts[0].strip(" .,!?\"'«»()[]{}—–-:")
        if not word:
            return None
        translation = parts[1] if len(parts) > 1 else ""
        example = parts[2] if len(parts) > 2 else ""
        return word, translation, example

    def generate_csv(self, words: list[str]) -> dict:
        """Возвращает {"csv": str, "rows": int, "errors": [str]}"""
        rows = []
        errors = []

        for i in range(0, len(words), self.BATCH_SIZE):
            batch = words[i:i + self.BATCH_SIZE]
            prompt = USER_ANKI_TEMPLATE.format(words="\n".join(batch))
            messages = [
                {"role": "system", "content": SYSTEM_ANKI},
                {"role": "user", "content": prompt},
            ]
            try:
                raw = self.client.chat(messages, max_tokens=400, debug=False)
            except Exception as e:
                errors.append(f"батч {i // self.BATCH_SIZE + 1}: {e}")
                for w in batch:
                    rows.append((w, "", ""))
                continue

            parsed = []
            for line in raw.strip().split("\n"):
                r = self._parse_line(line)
                if r:
                    parsed.append(r)

            if not parsed:
                errors.append(f"батч {i // self.BATCH_SIZE + 1}: пустой ответ")
                for w in batch:
                    rows.append((w, "", ""))
            else:
                rows.extend(parsed[:len(batch)])

        lines = []
        for word, translation, example in rows:
            w = self._clean_field(word)
            t = self._clean_field(translation)
            e = self._clean_field(example)
            lines.append(f"{w};{t};{e};{self.tag}")

        return {
            "csv": "\n".join(lines),
            "rows": len(lines),
            "errors": errors,
        }