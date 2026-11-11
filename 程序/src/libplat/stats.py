"""统计分析模块：分类统计、排行榜、趋势与多集合联合分析。"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from .audit import write_log

CN_TZ = timezone(timedelta(hours=8))


def category_summary(db=None) -> list[dict]:
    """按类别统计藏书量、平均价格、平均评分。"""
    db = _db() if db is None else db
    pipeline = [
        {"$group": {
            "_id": "$category",
            "book_kinds": {"$sum": 1},               # 品种数
            "copies": {"$sum": "$stock"},            # 在架册数
            "avg_price": {"$avg": "$price"},
            "avg_rating": {"$avg": "$rating"},
            "total_borrow": {"$sum": "$borrow_count"},
        }},
        {"$project": {
            "_id": 0,
            "category": "$_id",
            "book_kinds": 1,
            "copies": 1,
            "avg_price": {"$round": ["$avg_price", 2]},
            "avg_rating": {"$round": ["$avg_rating", 2]},
            "total_borrow": 1,
        }},
        {"$sort": {"copies": -1}},
    ]
    return list(db.books.aggregate(pipeline))


def college_top(college_n: int = 5, db=None) -> list[dict]:
    """统计各学院借阅总量，取前 N 名（borrow_logs ⋈ readers）。"""
    db = _db() if db is None else db
    pipeline = [
        {"$group": {"_id": "$reader_card", "borrow_times": {"$sum": 1}}},
        {"$lookup": {
            "from": "readers",
            "localField": "_id",
            "foreignField": "card_no",
            "as": "reader",
        }},
        {"$unwind": {"path": "$reader", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"$ifNull": ["$reader.college", "未知学院"]},
            "readers": {"$sum": 1},
            "borrow_times": {"$sum": "$borrow_times"},
        }},
        {"$project": {"_id": 0, "college": "$_id", "readers": 1, "borrow_times": 1},
        },
        {"$sort": {"borrow_times": -1}},
        {"$limit": college_n},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def _date_expr(field: str = "$borrow_date") -> dict:
    """兼容两种入库方式：数据文件里的日期是 ISO 字符串，手工插入的可能是 Date。"""
    return {
        "$cond": [
            {"$eq": [{"$type": field}, "string"]},
            {"$toDate": field},
            field,
        ]
    }


def monthly_trend(db=None) -> list[dict]:
    """按年月统计借阅趋势，输出 2023-01 这类可读标签。"""
    db = _db() if db is None else db
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m", "date": _date_expr(), "timezone": "+08:00"}},
            "count": {"$sum": 1},
            "avg_duration": {"$avg": "$duration_days"},
        }},
        {"$project": {"_id": 0, "month": "$_id", "count": 1,
                      "avg_duration": {"$round": ["$avg_duration", 1]}}},
        {"$sort": {"month": 1}},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def yearly_trend(db=None) -> list[dict]:
    db = _db() if db is None else db
    pipeline = [
        {"$group": {"_id": {"$year": {"date": _date_expr(), "timezone": "+08:00"}},
                    "count": {"$sum": 1}}},
        {"$project": {"_id": 0, "year": "$_id", "count": 1}},
        {"$sort": {"year": 1}},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def top_borrowed_books(limit: int = 10, db=None) -> list[dict]:
    """借阅次数最多的图书，并关联出馆藏位置。"""
    db = _db() if db is None else db
    pipeline = [
        {"$sort": {"borrow_count": -1}},
        {"$limit": limit},
        {"$project": {
            "_id": 0, "isbn": 1, "title": 1, "author": 1, "category": 1,
            "borrow_count": 1, "location": 1,
        }},
    ]
    return list(db.books.aggregate(pipeline))


def college_category_matrix(db=None) -> list[dict]:
    """多集合联合分析：学院 × 图书类别 的借阅矩阵（取每学院前 3 类）。"""
    db = _db() if db is None else db
    pipeline = [
        {"$lookup": {"from": "books", "localField": "book_isbn",
                     "foreignField": "isbn", "as": "book"}},
        {"$unwind": "$book"},
        {"$lookup": {"from": "readers", "localField": "reader_card",
                     "foreignField": "card_no", "as": "reader"}},
        {"$unwind": {"path": "$reader", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"college": {"$ifNull": ["$reader.college", "未知学院"]},
                    "category": "$book.category"},
            "times": {"$sum": 1},
        }},
        {"$sort": {"times": -1}},
        {"$group": {
            "_id": "$_id.college",
            "top_categories": {"$push": {"category": "$_id.category", "times": "$times"}},
        }},
        {"$project": {
            "_id": 0,
            "college": "$_id",
            "top_categories": {"$slice": ["$top_categories", 3]},
        }},
        {"$sort": {"college": 1}},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def save_category_stats(db=None) -> dict[str, Any]:
    """把分类统计结果落库到 category_stats，供后续直接查询。"""
    db = _db() if db is None else db
    rows = category_summary(db)
    generated = datetime.now(CN_TZ)
    for row in rows:
        row["generated_at"] = generated
    db.category_stats.delete_many({})
    if rows:
        db.category_stats.insert_many([dict(r) for r in rows])
    write_log("EXPORT", "category_stats", "category_summary",
              {"rows": len(rows)}, db=db)
    return {"rows": len(rows), "generated_at": generated.isoformat()}


def overview(db=None) -> dict[str, Any]:
    """平台数据总览，用于程序首页与验收核对。"""
    db = _db() if db is None else db
    return {
        "books": db.books.count_documents({}),
        "readers": db.readers.count_documents({}),
        "borrow_logs": db.borrow_logs.count_documents({}),
        "audit_logs": db.audit_logs.count_documents({}),
        "category_stats": db.category_stats.count_documents({}),
        "gridfs_files": db["fs.files"].count_documents({}),
    }


def _db():
    from .db import get_db
    return get_db()
