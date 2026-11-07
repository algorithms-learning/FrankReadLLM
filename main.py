# test_book.py
from pathlib import Path
from engine.chunker import chunk_text
from engine.ollama_client import OllamaClient
from engine.context import ContextCollector
from engine.translator import TranslatorEngine

BOOK_PATH = "/home/user/Desktop/book.txt"
N_CHUNKS = 3

# читаем с фолбэком на кодировку — книги бывают в cp1251
def read_book(path: str) -> str:
    data = Path(path).read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("не смог определить кодировку")

text = read_book(BOOK_PATH)
chunks = chunk_text(text)
print(f"Всего чанков: {len(chunks)}")
print(f"Берём первые {N_CHUNKS}\n")

book = {"memo": "", "glossary": {}, "last_original": None, "last_translation": None}
engine = TranslatorEngine(OllamaClient(), ContextCollector())

for i, chunk in enumerate(chunks[:N_CHUNKS], 1):
    print(f"=== Чанк {i} ===")
    print(f"ОРИГИНАЛ ({len(chunk)} символов):")
    print(chunk[:300] + ("..." if len(chunk) > 300 else ""))
    print()

    result = engine.translate_paragraph(book, chunk)

    if result["error"]:
        print(f"⚠ ОШИБКА: {result['error']}")
    else:
        print(f"ПЕРЕВОД:\n{result['translation']}")
        if result["comment"]:
            print(f"\nКОММЕНТ: {result['comment']}")
    print()