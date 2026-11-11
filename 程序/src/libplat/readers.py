"""读者管理模块。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from .audit import write_log


def get_reader(card_no: str, db=None) -> dict | None:
    db = _db() if db is None else db
    return db.readers.find_one({"card_no": card_no}, {"_id": 0})


def add_reader(reader: dict, db=None) -> str:
    db = _db() if db is None else db
    if isinstance(reader.get("register_date"), str):
        reader["register_date"] = datetime.fromisoformat(reader["register_date"])
    reader.setdefault("email", None)
    db.readers.insert_one(dict(reader))
    write_log("INSERT", "readers", reader["card_no"], {"name": reader.get("name")}, db=db)
    return reader["card_no"]


def update_reader(card_no: str, patch: dict, db=None) -> int:
    db = _db() if db is None else db
    before = db.readers.find_one({"card_no": card_no}, {"_id": 0, "name": 1, "level": 1, "email": 1})
    res = db.readers.update_one({"card_no": card_no}, {"$set": patch})
    write_log("UPDATE", "readers", card_no, {"before": before, "after": patch}, db=db)
    return res.modified_count


def delete_reader(card_no: str, db=None) -> int:
    db = _db() if db is None else db
    res = db.readers.delete_one({"card_no": card_no})
    write_log("DELETE", "readers", card_no, {"deleted": res.deleted_count}, db=db)
    return res.deleted_count


def by_college(college: str, db=None) -> list[dict]:
    db = _db() if db is None else db
    return list(db.readers.find({"college": college}, {"_id": 0})
                .sort("register_date", -1))


def by_level(level: str, db=None) -> list[dict]:
    db = _db() if db is None else db
    return list(db.readers.find({"level": level}, {"_id": 0}).sort("name", 1))


def missing_email(db=None) -> list[dict]:
    """邮箱为空或缺失的读者（数据质量核查）。"""
    db = _db() if db is None else db
    return list(db.readers.find(
        {"$or": [{"email": None}, {"email": {"$exists": False}}, {"email": ""}]},
        {"_id": 0, "card_no": 1, "name": 1},
    ))


def like_category(category: str, db=None) -> list[dict]:
    """偏好包含某类别的读者。"""
    db = _db() if db is None else db
    return list(db.readers.find(
        {"fav_categories": category}, {"_id": 0, "card_no": 1, "name": 1, "fav_categories": 1}
    ))


def list_readers(page: int = 1, page_size: int = 10, db=None) -> dict[str, Any]:
    db = _db() if db is None else db
    total = db.readers.count_documents({})
    cursor = (db.readers.find({}, {"_id": 0})
              .sort("card_no", 1)
              .skip((page - 1) * page_size)
              .limit(page_size))
    return {"page": page, "page_size": page_size, "total": total,
            "pages": (total + page_size - 1) // page_size, "items": list(cursor)}


def _db():
    from .db import get_db
    return get_db()
