import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from config import STORAGE_DIR

UPLOADS = Path(STORAGE_DIR) / "uploads"
BOOKS = Path(STORAGE_DIR) / "books"


def ensure_dirs():
    UPLOADS.mkdir(parents=True, exist_ok=True)
    BOOKS.mkdir(parents=True, exist_ok=True)


def save_upload(filename: str, data: bytes) -> str:
    ensure_dirs()
    book_id = hashlib.sha256(data).hexdigest()[:16]
    (UPLOADS / f"{book_id}.txt").write_bytes(data)
    return book_id


def load_upload_text(book_id: str) -> str:
    data = (UPLOADS / f"{book_id}.txt").read_bytes()
    for enc in ("utf-8", "utf-8-sig", "cp1251", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Не удалось определить кодировку")


def _book_path(book_id: str) -> Path:
    return BOOKS / f"{book_id}.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(raw: dict) -> dict:
    """Старый формат (paragraphs+memo на корне) → новый (versions)."""
    if "versions" in raw:
        return raw
    model = raw.get("model") or "unknown"
    raw["versions"] = {
        model: {
            "created_at": raw.get("created_at", _now()),
            "memo": raw.get("memo", ""),
            "paragraphs": raw.get("paragraphs", []),
        }
    }
    raw["active_model"] = model
    raw.pop("paragraphs", None)
    raw.pop("memo", None)
    raw.pop("model", None)
    return raw


def _versions_summary(versions: dict) -> list[dict]:
    out = []
    for k, vv in versions.items():
        paragraphs = vv.get("paragraphs", [])
        translated = sum(1 for p in paragraphs
                         if p.get("translation") and not p.get("error"))
        out.append({
            "model": k,
            "translated": translated,
            "total": len(paragraphs),
            "created_at": vv.get("created_at"),
        })
    out.sort(key=lambda x: x["model"])
    return out


def _to_view(raw: dict) -> dict:
    active = raw.get("active_model") or next(iter(raw.get("versions", {})), "unknown")
    v = raw.get("versions", {}).get(active, {})
    return {
        "id": raw["id"],
        "title": raw["title"],
        "total_chunks": raw.get("total_chunks", len(v.get("paragraphs", []))),
        "created_at": raw.get("created_at"),
        "glossary": raw.get("glossary", {}),
        "active_model": active,
        "model": active,
        "memo": v.get("memo", ""),
        "paragraphs": v.get("paragraphs", []),
        "available_versions": _versions_summary(raw.get("versions", {})),
        "_versions": raw.get("versions", {}),
        "_is_view": True,
    }


def load_book(book_id: str) -> dict | None:
    path = _book_path(book_id)
    if not path.exists():
        return None
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw = _migrate(raw)
    return _to_view(raw)


def save_book(book: dict) -> None:
    ensure_dirs()
    if book.get("_is_view"):
        versions = book.get("_versions") or {}
        active = book.get("active_model") or next(iter(versions), None)
        if not active:
            raise ValueError("book has no active_model")

        if active not in versions:
            versions[active] = {"created_at": _now(), "memo": "", "paragraphs": []}
        versions[active]["paragraphs"] = book.get("paragraphs", [])
        versions[active]["memo"] = book.get("memo", "")

        to_save = {
            "id": book["id"],
            "title": book["title"],
            "total_chunks": book.get("total_chunks", 0),
            "created_at": book.get("created_at"),
            "glossary": book.get("glossary", {}),
            "active_model": active,
            "versions": versions,
        }
    else:
        to_save = {k: v for k, v in book.items() if not k.startswith("_")}

    path = _book_path(to_save["id"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(to_save, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def set_active_version(book: dict, new_model: str) -> dict:
    versions = book.setdefault("_versions", {})
    old_model = book.get("active_model")

    if old_model:
        if old_model not in versions:
            versions[old_model] = {"created_at": _now(), "memo": "", "paragraphs": []}
        versions[old_model]["paragraphs"] = book.get("paragraphs", [])
        versions[old_model]["memo"] = book.get("memo", "")

    if new_model not in versions:
        sample = next(iter(versions.values()), None)
        base = sample.get("paragraphs", []) if sample else []
        versions[new_model] = {
            "created_at": _now(),
            "memo": "",
            "paragraphs": [
                {"index": p["index"], "chunk": p["chunk"],
                 "original": None, "translation": None,
                 "comment": None, "error": None, "model": None}
                for p in base
            ],
        }

    v = versions[new_model]
    book["active_model"] = new_model
    book["model"] = new_model
    book["paragraphs"] = v.get("paragraphs", [])
    book["memo"] = v.get("memo", "")
    book["available_versions"] = _versions_summary(versions)
    return book


def delete_version(book: dict, model: str) -> dict:
    versions = book.setdefault("_versions", {})
    if model not in versions:
        return book
    if model == book.get("active_model"):
        raise ValueError("cannot delete active version")
    if len(versions) <= 1:
        raise ValueError("cannot delete the only version")
    del versions[model]
    book["available_versions"] = _versions_summary(versions)
    return book


def reset_active_version(book: dict) -> dict:
    for p in book.get("paragraphs", []):
        p["original"] = None
        p["translation"] = None
        p["comment"] = None
        p["error"] = None
        p["model"] = None
    book["memo"] = ""
    return book


def list_books() -> list[dict]:
    ensure_dirs()
    out = []
    for p in BOOKS.glob("*.json"):
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            raw = _migrate(raw)
            active = raw.get("active_model") or next(iter(raw.get("versions", {})), "")
            v = raw.get("versions", {}).get(active, {})
            paragraphs = v.get("paragraphs", [])
            total = raw.get("total_chunks", len(paragraphs))
            done = sum(1 for x in paragraphs
                       if x.get("translation") and not x.get("error"))
            out.append({
                "id": raw["id"],
                "title": raw["title"],
                "total_chunks": total,
                "done": done,
                "active_model": active,
                "versions_count": len(raw.get("versions", {})),
            })
        except Exception:
            continue
    return sorted(out, key=lambda x: x["title"])