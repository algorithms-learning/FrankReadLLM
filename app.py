import os
from datetime import datetime, timezone

import requests
from flask import Flask, Response, jsonify, render_template, request

from config import MODEL, OLLAMA_URL
from engine.anki import AnkiEngine
from engine.chat import ChatEngine
from engine.chunker import chunk_text
from engine.ollama_client import OllamaClient
from jobs import (cancel_job_for_book, get_job, get_running_job, start_job)
from storage import (
    delete_version, list_books, load_book, load_upload_text,
    reset_active_version, save_book, save_upload, set_active_version,
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/config")
def api_config():
    return jsonify({"model": MODEL})


@app.route("/api/models")
def api_models():
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        r.raise_for_status()
        data = r.json()
        names = []
        for m in data.get("models", []):
            name = m.get("name") or m.get("model")
            if name:
                names.append(name)
        names.sort()
        return jsonify({"models": names, "default": MODEL})
    except Exception as e:
        return jsonify({"error": str(e), "models": [], "default": MODEL}), 502


@app.route("/api/books")
def api_books():
    return jsonify(list_books())


@app.route("/api/upload", methods=["POST"])
def api_upload():
    f = request.files.get("file")
    if not f or not f.filename.lower().endswith(".txt"):
        return jsonify({"error": "Нужен файл .txt"}), 400

    data = f.read()
    book_id = save_upload(f.filename, data)

    existing = load_book(book_id)
    if existing:
        return jsonify({
            "book_id": existing["id"],
            "title": existing["title"],
            "total_chunks": existing["total_chunks"],
            "resumed": True,
        })

    try:
        text = load_upload_text(book_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    chunks = chunk_text(text)
    if not chunks:
        return jsonify({"error": "Пустой файл"}), 400

    now = datetime.now(timezone.utc).isoformat()
    book = {
        "id": book_id,
        "title": os.path.splitext(f.filename)[0],
        "created_at": now,
        "total_chunks": len(chunks),
        "glossary": {},
        "active_model": MODEL,
        "versions": {
            MODEL: {
                "created_at": now,
                "memo": "",
                "paragraphs": [
                    {"index": i, "chunk": c, "original": None,
                     "translation": None, "comment": None,
                     "error": None, "model": None}
                    for i, c in enumerate(chunks)
                ],
            }
        },
    }
    save_book(book)
    return jsonify({
        "book_id": book_id,
        "title": book["title"],
        "total_chunks": len(chunks),
        "resumed": False,
    })


@app.route("/api/book/<book_id>/version", methods=["POST"])
def api_book_version(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    new_model = (data.get("model") or "").strip()
    if not new_model:
        return jsonify({"error": "empty model"}), 400

    # Отменяем running job — иначе он продолжит писать в старую версию
    cancel_job_for_book(book_id, reason=f"version switched to {new_model}")

    set_active_version(book, new_model)
    save_book(book)
    return jsonify({
        "ok": True,
        "model": new_model,
        "available_versions": book["available_versions"],
    })


@app.route("/api/book/<book_id>/version/<path:model>", methods=["DELETE"])
def api_book_version_delete(book_id, model):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404
    try:
        delete_version(book, model)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    save_book(book)
    return jsonify({"ok": True, "available_versions": book["available_versions"]})


@app.route("/api/book/<book_id>/reset", methods=["POST"])
def api_book_reset(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404
    cancel_job_for_book(book_id, reason="reset")
    reset_active_version(book)
    save_book(book)
    return jsonify({"ok": True, "total": len(book["paragraphs"])})


@app.route("/api/book/<book_id>/job")
def api_book_job(book_id):
    """Текущий running job для книги (или null)."""
    job = get_running_job(book_id)
    return jsonify({"job": job})


@app.route("/api/process/<book_id>", methods=["POST"])
def api_process(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}
    new_model = (data.get("model") or "").strip()
    if new_model and new_model != book.get("active_model"):
        cancel_job_for_book(book_id, reason=f"model changed to {new_model}")
        set_active_version(book, new_model)
        save_book(book)
        print(f"[api] активная версия {book_id} → {new_model}", flush=True)

    try:
        job_id = start_job(book_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"job_id": job_id})


@app.route("/api/status/<job_id>")
def api_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(job)


@app.route("/api/book/<book_id>")
def api_book(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404
    return jsonify(book)


@app.route("/api/retry/<book_id>/<int:index>", methods=["POST"])
def api_retry(book_id, index):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404
    if index < 0 or index >= len(book["paragraphs"]):
        return jsonify({"error": "bad index"}), 400
    p = book["paragraphs"][index]
    p["translation"] = None
    p["error"] = None
    p["model"] = None
    save_book(book)
    job_id = start_job(book_id)
    return jsonify({"job_id": job_id})


@app.route("/api/chat/<book_id>", methods=["POST"])
def api_chat(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}
    question = (data.get("message") or "").strip()
    if not question:
        return jsonify({"error": "empty message"}), 400

    context_index = data.get("context_index", 0)
    history = data.get("history", []) or []
    selected_text = (data.get("selected_text") or "").strip() or None

    if not isinstance(context_index, int) or not (0 <= context_index < len(book["paragraphs"])):
        context_index = 0
    paragraph = book["paragraphs"][context_index]

    model = book.get("model") or MODEL
    engine = ChatEngine(OllamaClient(model=model))

    def generate():
        try:
            for piece in engine.chat_stream(book, paragraph, history, question, selected_text):
                yield piece
        except GeneratorExit:
            print("[chat] клиент отключился, генерация остановлена", flush=True)
            raise
        except Exception as e:
            yield f"\n[ОШИБКА: {e}]"

    return Response(generate(), mimetype="text/plain; charset=utf-8")


@app.route("/api/anki/<book_id>", methods=["POST"])
def api_anki(book_id):
    book = load_book(book_id)
    if not book:
        return jsonify({"error": "not found"}), 404

    data = request.get_json(silent=True) or {}
    words = data.get("words", [])
    if not isinstance(words, list) or not words:
        return jsonify({"error": "пустой список слов"}), 400

    tag = (data.get("tag") or book["title"] or "frank_reader").strip()
    tag = "".join(c if (c.isalnum() or c in "_-") else "_" for c in tag)
    tag = tag.strip("_")[:40] or "frank_reader"

    model = book.get("model") or MODEL
    engine = AnkiEngine(OllamaClient(model=model), tag=tag)
    result = engine.generate_csv(words)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)