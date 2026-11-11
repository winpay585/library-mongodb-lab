"""图书管理模块：增删改查、条件检索、分页排序。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from bson.decimal128 import Decimal128  # noqa: F401  (留作价格高精度扩展)

from .audit import write_log

CN_TZ = timezone(timedelta(hours=8))

PROJECTION_BRIEF = {"_id": 0, "isbn": 1, "title": 1, "author": 1, "rating": 1}


def year_bounds(start_year: int, end_year: int) -> dict[str, datetime]:
    """按年份区间构造 UTC 时间边界（以东八区自然年为准）。"""
    return {
        "$gte": datetime(start_year, 1, 1, tzinfo=CN_TZ),
        "$lt": datetime(end_year + 1, 1, 1, tzinfo=CN_TZ),
    }


def get_book(isbn: str, db=None) -> dict | None:
    db = _db() if db is None else db
    return db.books.find_one({"isbn": isbn}, {"_id": 0})


def add_book(book: dict, db=None) -> str:
    """新增图书，price/rating 统一为 float，publish_date 统一为 Date。"""
    db = _db() if db is None else db
    book.setdefault("borrow_count", 0)
    book["price"] = float(book["price"])
    book["rating"] = float(book["rating"])
    book["stock"] = int(book["stock"])
    if isinstance(book.get("publish_date"), str):
        book["publish_date"] = datetime.fromisoformat(book["publish_date"])
    db.books.insert_one(dict(book))
    write_log("INSERT", "books", book["isbn"], {"title": book.get("title")}, db=db)
    return book["isbn"]


def update_book(isbn: str, patch: dict, db=None) -> int:
    db = _db() if db is None else db
    before = db.books.find_one({"isbn": isbn}, {"_id": 0, "title": 1, "stock": 1, "price": 1})
    res = db.books.update_one({"isbn": isbn}, {"$set": patch})
    write_log("UPDATE", "books", isbn, {"before": before, "after": patch}, db=db)
    return res.modified_count


def delete_book(isbn: str, db=None) -> int:
    db = _db() if db is None else db
    res = db.books.delete_one({"isbn": isbn})
    write_log("DELETE", "books", isbn, {"deleted": res.deleted_count}, db=db)
    return res.deleted_count


# ---------------- 条件检索 ----------------
def by_category_price(category: str, min_price: float, max_price: float, db=None) -> list[dict]:
    """1. 类别 + 价格区间组合筛选。"""
    db = _db() if db is None else db
    return list(db.books.find(
        {"category": category, "price": {"$gte": min_price, "$lte": max_price}},
        {"_id": 0, "isbn": 1, "title": 1, "category": 1, "price": 1},
    ).sort("price", 1))


def by_tags_all(tags: list[str], db=None) -> list[dict]:
    """2. 标签多选匹配：$all 要求同时命中全部指定标签。"""
    db = _db() if db is None else db
    return list(db.books.find(
        {"tags": {"$all": tags}}, {"_id": 0, "isbn": 1, "title": 1, "tags": 1}
    ).sort("rating", -1))


def by_title(keyword: str, db=None) -> list[dict]:
    """3. 书名模糊检索（正则，大小写不敏感）。"""
    db = _db() if db is None else db
    return list(db.books.find(
        {"title": {"$regex": re.escape(keyword), "$options": "i"}},
        {"_id": 0, "isbn": 1, "title": 1, "author": 1},
    ))


def by_publish_year_range(start_year: int, end_year: int, db=None) -> list[dict]:
    """4. 出版年份区间检索。"""
    db = _db() if db is None else db
    return list(db.books.find(
        {"publish_date": year_bounds(start_year, end_year)},
        {"_id": 0, "isbn": 1, "title": 1, "publish_date": 1},
    ).sort("publish_date", -1))


def missing_tags(db=None) -> list[dict]:
    """5. 查询缺少 tags 字段的图书（数据质量核查）。"""
    db = _db() if db is None else db
    return list(db.books.find(
        {"tags": {"$exists": False}},
        {"_id": 0, "isbn": 1, "title": 1, "category": 1},
    ))


def top_rated(limit: int = 10, db=None) -> list[dict]:
    """6. 按评分排序取前 N，仅返回书名、作者、评分。"""
    db = _db() if db is None else db
    return list(db.books.find({}, PROJECTION_BRIEF).sort("rating", -1).limit(limit))


# ---------------- 分页与排序 ----------------
def list_books(page: int = 1, page_size: int = 10, sort_field: str = "title",
               ascending: bool = True, db=None) -> dict[str, Any]:
    """分页查询：返回当前页数据与总页数。"""
    db = _db() if db is None else db
    total = db.books.count_documents({})
    cursor = (db.books.find({}, {"_id": 0})
              .sort(sort_field, 1 if ascending else -1)
              .skip((page - 1) * page_size)
              .limit(page_size))
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
        "items": list(cursor),
    }


def _db():
    from .db import get_db
    return get_db()
