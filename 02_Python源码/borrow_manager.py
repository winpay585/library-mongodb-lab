# -*- coding: utf-8 -*-
"""借阅管理模块：借阅登记、归还处理、逾期查询。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from pymongo.database import Database

from mongodb_connect import print_table


def borrow_book(db: Database, card_no: str, isbn: str) -> ObjectId | None:
    """借阅登记：校验读者和图书、扣减库存、写入借阅流水、累加借阅次数。

    返回借阅流水的 _id；失败返回 None 并打印原因。
    """
    reader = db.readers.find_one({"card_no": card_no}, {"_id": 1, "name": 1})
    if not reader:
        print(f"借阅失败：不存在借阅证号 {card_no}")
        return None

    book = db.books.find_one({"isbn": isbn}, {"_id": 1, "title": 1, "stock": 1})
    if not book:
        print(f"借阅失败：不存在 ISBN {isbn}")
        return None
    if int(book.get("stock", 0)) <= 0:
        print(f"借阅失败：《{book.get('title')}》库存为 0")
        return None

    now = datetime.now(timezone.utc)
    log_doc = {
        "borrow_date": now,
        "reader_card": card_no,
        "book_isbn": isbn,
        "status": "借出",
    }

    # 先写流水，再改库存；若库存更新失败则回滚流水
    log_result = db.borrow_logs.insert_one(log_doc)
    stock_result = db.books.update_one(
        {"isbn": isbn, "stock": {"$gt": 0}}, {"$inc": {"stock": -1, "borrow_count": 1}}
    )
    if stock_result.modified_count == 0:
        db.borrow_logs.delete_one({"_id": log_result.inserted_id})
        print("借阅失败：库存已被其他操作占用，请重试")
        return None

    print(f"借阅成功：{reader.get('name')} 借出《{book.get('title')}》")
    print(f"借阅流水 _id = {log_result.inserted_id}")
    return log_result.inserted_id


def return_book(db: Database, card_no: str, isbn: str) -> int:
    """归还处理：把最近一条“借出”流水改为“已归还”，库存加 1。

    说明：borrow_logs 是时间序列集合，MongoDB 7.0 只允许按 metaField 更新，
    因此这里采用“删除原流水 + 插入一条同借阅日期的新流水”的等价做法，
    既保留借阅时间，又能正确写入归还日期。
    """
    log = db.borrow_logs.find_one(
        {"reader_card": card_no, "book_isbn": isbn, "status": "借出"},
        sort=[("borrow_date", -1)],
    )
    if not log:
        print("归还失败：没有找到该读者对该图书的“借出”记录")
        return 0

    now = datetime.now(timezone.utc)
    deleted = db.borrow_logs.delete_one({"_id": log["_id"]})
    if deleted.deleted_count == 0:
        print("归还失败：流水已被其他操作修改，请刷新后重试")
        return 0

    new_log = {key: value for key, value in log.items() if key != "_id"}
    new_log["status"] = "已归还"
    new_log["return_date"] = now
    try:
        result = db.borrow_logs.insert_one(new_log)
    except Exception:
        # 插入失败则恢复原流水，避免借阅记录丢失
        db.borrow_logs.insert_one(log)
        print("归还失败：写入归还记录时出错，已恢复原流水")
        return 0

    db.books.update_one({"isbn": isbn}, {"$inc": {"stock": 1}})
    print(f"归还成功：新流水 {result.inserted_id} 状态为“已归还”，库存 +1")
    return 1


def overdue_borrows(db: Database, days: int = 30) -> list[dict[str, Any]]:
    """查询超过指定天数仍未归还的借阅记录。"""
    deadline = datetime.now(timezone.utc) - timedelta(days=days)
    pipeline = [
        {"$match": {"status": "借出", "borrow_date": {"$lt": deadline}}},
        {"$sort": {"borrow_date": 1}},
        {"$lookup": {"from": "readers", "localField": "reader_card",
                     "foreignField": "card_no", "as": "reader"}},
        {"$unwind": {"path": "$reader", "preserveNullAndEmptyArrays": True}},
        {"$lookup": {"from": "books", "localField": "book_isbn",
                     "foreignField": "isbn", "as": "book"}},
        {"$unwind": {"path": "$book", "preserveNullAndEmptyArrays": True}},
        {"$project": {
            "_id": 1,
            "reader_card": 1,
            "name": "$reader.name",
            "book_isbn": 1,
            "title": "$book.title",
            "borrow_date": 1,
            "days": {"$dateDiff": {"startDate": "$borrow_date", "endDate": "$$NOW", "unit": "day"}},
        }},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def mark_overdue(db: Database, days: int = 30) -> int:
    """把超期未还的记录批量标记为“逾期”，返回修改条数。

    同样受时间序列集合的更新限制，采用逐条“删除 + 插入”的方式。
    """
    deadline = datetime.now(timezone.utc) - timedelta(days=days)
    query = {"status": "借出", "borrow_date": {"$lt": deadline}}
    changed = 0
    for log in list(db.borrow_logs.find(query)):
        deleted = db.borrow_logs.delete_one({"_id": log["_id"]})
        if deleted.deleted_count == 0:
            continue
        new_log = {key: value for key, value in log.items() if key != "_id"}
        new_log["status"] = "逾期"
        db.borrow_logs.insert_one(new_log)
        changed += 1
    return changed


def show_overdue(records: list[dict[str, Any]]) -> None:
    rows = [
        (
            str(r.get("_id", "")),
            r.get("reader_card", ""),
            r.get("name") or "（读者已删除）",
            r.get("title") or "（图书已删除）",
            str(r.get("borrow_date", ""))[:10],
            r.get("days", ""),
        )
        for r in records
    ]
    print_table(["流水ID", "借阅证号", "姓名", "书名", "借阅日期", "已借天数"], rows)


def borrow_history(db: Database, card_no: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """查询借阅历史，可按借阅证号过滤。"""
    query = {"reader_card": card_no} if card_no else {}
    cursor = db.borrow_logs.find(
        query,
        {"_id": 1, "reader_card": 1, "book_isbn": 1, "borrow_date": 1,
         "return_date": 1, "status": 1},
    ).sort("borrow_date", -1).limit(limit)
    return list(cursor)
