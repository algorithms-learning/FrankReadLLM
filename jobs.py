import threading
import time
import traceback
import uuid

from config import COMPACT_EVERY_N, MODEL
from engine.context import ContextCollector
from engine.ollama_client import OllamaClient
from engine.translator import TranslatorEngine
from storage import load_book, save_book

_jobs: dict[str, dict] = {}
_book_jobs: dict[str, str] = {}
_lock = threading.Lock()


def _set(job_id: str, **kw):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(kw)


def get_job(job_id: str) -> dict | None:
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def get_running_job(book_id: str) -> dict | None:
    with _lock:
        jid = _book_jobs.get(book_id)
        if jid and _jobs.get(jid, {}).get("state") == "running":
            return dict(_jobs[jid])
    return None


def cancel_job_for_book(book_id: str, reason: str = "cancelled") -> None:
    """Помечает running job как cancelled. _run сам выйдет на следующей итерации."""
    with _lock:
        jid = _book_jobs.get(book_id)
        if jid and _jobs.get(jid, {}).get("state") == "running":
            _jobs[jid]["state"] = "cancelled"
            _jobs[jid]["error"] = reason
            _book_jobs.pop(book_id, None)


def _pending_indices(book: dict) -> list[int]:
    return [p["index"] for p in book["paragraphs"]
            if not p.get("translation") or p.get("error")]


def start_job(book_id: str) -> str:
    book = load_book(book_id)
    if not book:
        raise ValueError("book not found")

    model = book.get("active_model") or MODEL

    with _lock:
        jid = _book_jobs.get(book_id)
        if jid and _jobs.get(jid, {}).get("state") == "running":
            old_model = _jobs[jid].get("model")
            if old_model == model:
                return jid
            # модель изменилась — старый job отменяем, создаём новый
            _jobs[jid]["state"] = "cancelled"
            _jobs[jid]["error"] = f"model changed: {old_model} → {model}"
            _book_jobs.pop(book_id, None)

    job_id = uuid.uuid4().hex[:12]
    pending = _pending_indices(book)

    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "book_id": book_id,
            "state": "running",
            "done": book["total_chunks"] - len(pending),
            "total": book["total_chunks"],
            "current": "",
            "error": None,
            "started_at": time.time(),
            "model": model,
        }
        _book_jobs[book_id] = job_id

    t = threading.Thread(target=_run, args=(job_id, book_id, model), daemon=True)
    t.start()
    return job_id


def _run(job_id: str, book_id: str, model: str):
    try:
        book = load_book(book_id)
        if not book:
            _set(job_id, state="error", error="book not found")
            return
        if book.get("active_model") != model:
            _set(job_id, state="cancelled",
                 error=f"active_model changed to {book.get('active_model')}")
            return

        client = OllamaClient(model=model)
        engine = TranslatorEngine(client, ContextCollector())
        print(f"[job {job_id}] старт: модель={model}", flush=True)

        pending = set(_pending_indices(book))
        for p in list(book["paragraphs"]):
            if p["index"] not in pending:
                continue

            # Перечитываем книгу — могла смениться активная версия
            book = load_book(book_id)
            if not book or book.get("active_model") != model:
                _set(job_id, state="cancelled",
                     error=f"active_model changed to "
                           f"{book.get('active_model') if book else '?'}")
                print(f"[job {job_id}] отменён: сменилась активная версия", flush=True)
                return

            # Проверяем, не пометили ли нас снаружи как cancelled
            with _lock:
                current_state = _jobs.get(job_id, {}).get("state")
            if current_state == "cancelled":
                print(f"[job {job_id}] отменён извне", flush=True)
                return

            p_idx = p["index"]
            target = next((x for x in book["paragraphs"] if x["index"] == p_idx), None)
            if target is None:
                continue

            _set(job_id, current=(target["chunk"][:100]))

            result = engine.translate_paragraph(book, target["chunk"],
                                                model=model, debug=False)

            target["original"] = result.get("original") or target["chunk"]
            target["translation"] = result.get("translation")
            target["comment"] = result.get("comment")
            target["error"] = result.get("error")
            target["model"] = result.get("model") or model

            save_book(book)

            done_now = sum(1 for x in book["paragraphs"]
                           if x.get("translation") and not x.get("error"))
            _set(job_id, done=done_now)

            if done_now > 0 and done_now % COMPACT_EVERY_N == 0:
                recent = [x for x in book["paragraphs"]
                          if x.get("translation") and not x.get("error")][-COMPACT_EVERY_N:]
                book["memo"] = engine.compact(book, recent)
                save_book(book)

        _set(job_id, state="done", current="")
        print(f"[job {job_id}] готово", flush=True)
    except Exception as e:
        _set(job_id, state="error", error=f"{e}\n{traceback.format_exc()[:800]}")
        print(f"[job {job_id}] ошибка: {e}", flush=True)