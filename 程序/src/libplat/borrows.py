"""借阅管理模块：借书、还书、逾期与流水查询。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .audit import write_log

CN_TZ = timezone(timedelta(hours=8))
DEFAULT_LOAN_DAYS = 30


def borrow(card_no: str, isbn: str, days: int = DEFAULT_LOAN_DAYS, db=None) -> dict[str, Any]:
    """办理借阅：库存 -1、借阅次数 +1、写入流水（status=借出）。"""
    db = _db() if db is None else db
    book = db.books.find_one({"isbn": isbn}, {"_id": 0, "title": 1, "stock": 1})
    if not book:
        raise ValueError(f"ISBN 不存在: {isbn}")
    if book.get("stock", 0) <= 0:
        raise ValueError(f"《{book['title']}》无可借库存")
    if not db.readers.find_one({"card_no": card_no}, {"_id": 1}):
        raise ValueError(f"读者不存在: {card_no}")

    now = datetime.now(CN_TZ)
    db.books.update_one({"isbn": isbn}, {"$inc": {"stock": -1, "borrow_count": 1}})
    log = {
        "borrow_date": now,
        "reader_card": card_no,
        "book_isbn": isbn,
        "status": "借出",
        "duration_days": days,
    }
    doc_id = db.borrow_logs.insert_one(log).inserted_id
    write_log("INSERT", "borrow_logs", str(doc_id), {"card": card_no, "isbn": isbn}, db=db)
    return {"inserted_id": str(doc_id), "borrow_date": now.isoformat(), "status": "借出"}


def give_back(card_no: str, isbn: str, db=None) -> dict[str, Any]:
    """办理归还：回填 return_date、改写 status、按实际天数更新 duration_days。"""
    db = _db() if db is None else db
    log = db.borrow_logs.find_one(
        {"reader_card": card_no, "book_isbn": isbn, "status": {"$ne": "已归还"}},
        sort=[("borrow_date", -1)],
    )
    if not log:
        raise ValueError("没有找到该读者对该书的在借记录")
    now = datetime.now(CN_TZ)
    days = max((now - log["borrow_date"].astimezone(CN_TZ)).days, 0)
    db.borrow_logs.update_one(
        {"_id": log["_id"]},
        {"$set": {"return_date": now, "status": "已归还", "duration_days": days}},
    )
    db.books.update_one({"isbn": isbn}, {"$inc": {"stock": 1}})
    write_log("UPDATE", "borrow_logs", str(log["_id"]),
              {"return_date": now.isoformat(), "duration_days": days}, db=db)
    return {"days": days, "status": "已归还"}


def overdue(db=None) -> list[dict]:
    """逾期判定：未归还且借出天数超过 duration_days。"""
    db = _db() if db is None else db
    pipeline = [
        {"$match": {"return_date": {"$exists": False}, "status": {"$ne": "已归还"}}},
        {"$addFields": {
            "elapsed": {"$dateDiff": {"startDate": "$borrow_date", "endDate": "$$NOW", "unit": "day"}},
        }},
        {"$match": {"$expr": {"$gt": ["$elapsed", "$duration_days"]}}},
        {"$project": {"_id": 0, "reader_card": 1, "book_isbn": 1,
                      "borrow_date": 1, "elapsed": 1, "duration_days": 1}},
        {"$sort": {"elapsed": -1}},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def history_by_reader(card_no: str, limit: int = 20, db=None) -> list[dict]:
    db = _db() if db is None else db
    return list(db.borrow_logs.find({"reader_card": card_no}, {"_id": 0})
                .sort("borrow_date", -1).limit(limit))


def history_by_book(isbn: str, limit: int = 20, db=None) -> list[dict]:
    db = _db() if db is None else db
    return list(db.borrow_logs.find({"book_isbn": isbn}, {"_id": 0})
                .sort("borrow_date", -1).limit(limit))


def active_by_reader(card_no: str, db=None) -> list[dict]:
    db = _db() if db is None else db
    return list(db.borrow_logs.find(
        {"reader_card": card_no, "status": {"$ne": "已归还"}}, {"_id": 0}
    ).sort("borrow_date", -1))


def _db():
    from .db import get_db
    return get_db()
