# -*- coding: utf-8 -*-
"""统计分析模块：分类统计、借阅趋势、畅销榜、出版社统计。"""

from __future__ import annotations

from typing import Any

from pymongo.database import Database

from mongodb_connect import print_table


def category_stats(db: Database) -> list[dict[str, Any]]:
    """按类别统计库存总量、平均价格、图书数量，按库存总量降序。"""
    pipeline = [
        {"$group": {
            "_id": "$category",
            "total_stock": {"$sum": "$stock"},
            "avg_price": {"$avg": "$price"},
            "book_count": {"$sum": 1},
        }},
        {"$project": {
            "_id": 0,
            "category": "$_id",
            "total_stock": 1,
            "avg_price": {"$round": ["$avg_price", 2]},
            "book_count": 1,
        }},
        {"$sort": {"total_stock": -1, "category": 1}},
    ]
    return list(db.books.aggregate(pipeline))


def show_category_stats(stats: list[dict[str, Any]]) -> None:
    print_table(
        ["类别", "库存总量", "平均价格", "图书数量"],
        [(s["category"], s["total_stock"], f"{s['avg_price']:.2f}", s["book_count"]) for s in stats],
    )


def borrow_trend(db: Database) -> list[dict[str, Any]]:
    """按年份统计借阅量，输出“2024年”格式。"""
    pipeline = [
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y年", "date": "$borrow_date",
                                       "timezone": "Asia/Shanghai"}},
            "borrow_count": {"$sum": 1},
        }},
        {"$project": {"_id": 0, "year": "$_id", "borrow_count": 1}},
        {"$sort": {"year": 1}},
    ]
    return list(db.borrow_logs.aggregate(pipeline))


def show_borrow_trend(trend: list[dict[str, Any]]) -> None:
    print_table(["年份", "借阅量"], [(t["year"], t["borrow_count"]) for t in trend])


def bestsellers(db: Database, n: int = 5) -> list[dict[str, Any]]:
    """畅销榜：按累计借阅次数降序。"""
    cursor = (
        db.books.find({}, {"_id": 0, "isbn": 1, "title": 1, "borrow_count": 1,
                           "rating": 1, "category": 1})
        .sort("borrow_count", -1)
        .limit(n)
    )
    return list(cursor)


def show_bestsellers(books: list[dict[str, Any]]) -> None:
    rows = [
        (i, b.get("title", ""), b.get("borrow_count", 0), b.get("rating", 0), b.get("category", ""))
        for i, b in enumerate(books, start=1)
    ]
    print_table(["名次", "书名", "累计借阅", "评分", "类别"], rows)


def publisher_stats(db: Database, n: int = 5) -> list[dict[str, Any]]:
    """各出版社图书数量 Top N，使用 $topN 累加器。"""
    pipeline = [
        {"$group": {"_id": "$publisher", "count": {"$sum": 1}}},
        {"$group": {"_id": None, "top": {"$topN": {
            "n": n, "sortBy": {"count": -1},
            "output": {"publisher": "$_id", "count": "$count"},
        }}}},
        {"$unwind": "$top"},
        {"$replaceRoot": {"newRoot": "$top"}},
    ]
    return list(db.books.aggregate(pipeline))


def show_publisher_stats(stats: list[dict[str, Any]]) -> None:
    print_table(["出版社", "图书数量"], [(s["publisher"], s["count"]) for s in stats])
