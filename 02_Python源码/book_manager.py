# -*- coding: utf-8 -*-
"""图书管理模块：图书增删改查、条件检索、评分排行。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from mongodb_connect import print_table


def build_query(
    keyword: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
) -> dict[str, Any]:
    """把用户输入组合成 MongoDB 查询条件。

    - keyword：书名/作者/ISBN 模糊匹配（不区分大小写）
    - category：类别精确匹配
    - min_price / max_price：价格范围
    """
    query: dict[str, Any] = {}
    if keyword:
        query["$or"] = [
            {"title": {"$regex": keyword, "$options": "i"}},
            {"author": {"$regex": keyword, "$options": "i"}},
            {"isbn": {"$regex": keyword, "$options": "i"}},
        ]
    if category:
        query["category"] = category
    if min_price is not None or max_price is not None:
        price: dict[str, float] = {}
        if min_price is not None:
            price["$gte"] = min_price
        if max_price is not None:
            price["$lte"] = max_price
        query["price"] = price
    return query


def search_books(
    db: Database,
    keyword: str | None = None,
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """条件检索，按评分降序返回。"""
    query = build_query(keyword, category, min_price, max_price)
    cursor = (
        db.books.find(query, {"_id": 1, "isbn": 1, "title": 1, "author": 1,
                              "category": 1, "price": 1, "stock": 1, "rating": 1})
        .sort("rating", -1)
        .limit(limit)
    )
    return list(cursor)


def show_books(books: list[dict[str, Any]]) -> None:
    rows = [
        (
            b.get("isbn", ""),
            b.get("title", ""),
            b.get("author", ""),
            b.get("category", ""),
            f"{b.get('price', 0):.2f}",
            b.get("stock", 0),
            b.get("rating", 0),
        )
        for b in books
    ]
    print_table(["ISBN", "书名", "作者", "类别", "价格", "库存", "评分"], rows)


def add_book(db: Database, book: dict[str, Any]) -> str:
    """新增一本图书，返回插入的 _id。"""
    doc = dict(book)
    doc.setdefault("publish_date", datetime.now(timezone.utc))
    doc.setdefault("borrow_count", 0)
    doc.setdefault("tags", [])
    result = db.books.insert_one(doc)
    return str(result.inserted_id)


def adjust_stock(db: Database, isbn: str, delta: int) -> int:
    """库存增减；返回实际修改的文档数。"""
    if delta == 0:
        return 0
    result = db.books.update_one({"isbn": isbn}, {"$inc": {"stock": delta}})
    return result.modified_count


def delete_book(db: Database, isbn: str) -> int:
    """按 ISBN 删除图书；返回删除条数。"""
    result = db.books.delete_one({"isbn": isbn})
    return result.deleted_count


def top_rated(db: Database, n: int = 5) -> list[dict[str, Any]]:
    """评分排行：评分降序，同分按借阅次数降序。"""
    cursor = (
        db.books.find({}, {"_id": 0, "title": 1, "rating": 1, "borrow_count": 1, "category": 1})
        .sort([("rating", -1), ("borrow_count", -1)])
        .limit(n)
    )
    return list(cursor)


def show_rating_rank(books: list[dict[str, Any]]) -> None:
    rows = [
        (i, b.get("title", ""), b.get("rating", 0), b.get("borrow_count", 0), b.get("category", ""))
        for i, b in enumerate(books, start=1)
    ]
    print_table(["名次", "书名", "评分", "借阅次数", "类别"], rows)
