# -*- coding: utf-8 -*-
"""读者管理模块：读者信息管理、学院统计、等级分布。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo.database import Database

from mongodb_connect import print_table


def find_readers(db: Database, keyword: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """按借阅证号、姓名或学院模糊查询读者。"""
    query: dict[str, Any] = {}
    if keyword:
        query["$or"] = [
            {"card_no": {"$regex": keyword, "$options": "i"}},
            {"name": {"$regex": keyword, "$options": "i"}},
            {"college": {"$regex": keyword, "$options": "i"}},
        ]
    cursor = db.readers.find(
        query,
        {"_id": 0, "card_no": 1, "name": 1, "college": 1, "email": 1,
         "phone": 1, "level": 1, "register_date": 1},
    ).limit(limit)
    return list(cursor)


def show_readers(readers: list[dict[str, Any]]) -> None:
    rows = [
        (
            r.get("card_no", ""),
            r.get("name", ""),
            r.get("college", ""),
            r.get("email") or "（空）",
            r.get("phone", ""),
            r.get("level", ""),
        )
        for r in readers
    ]
    print_table(["借阅证号", "姓名", "学院", "邮箱", "电话", "等级"], rows)


def add_reader(db: Database, reader: dict[str, Any]) -> str:
    """新增读者，返回插入的 _id。"""
    doc = dict(reader)
    doc.setdefault("register_date", datetime.now(timezone.utc))
    doc.setdefault("fav_categories", [])
    result = db.readers.insert_one(doc)
    return str(result.inserted_id)


def delete_reader(db: Database, card_no: str) -> int:
    """按借阅证号删除读者，返回删除条数。"""
    result = db.readers.delete_one({"card_no": card_no})
    return result.deleted_count


def college_stats(db: Database) -> list[dict[str, Any]]:
    """按学院统计读者人数，按人数降序。"""
    pipeline = [
        {"$group": {"_id": "$college", "reader_count": {"$sum": 1}}},
        {"$project": {"_id": 0, "college": "$_id", "reader_count": 1}},
        {"$sort": {"reader_count": -1, "college": 1}},
    ]
    return list(db.readers.aggregate(pipeline))


def level_distribution(db: Database) -> list[dict[str, Any]]:
    """按借阅等级统计人数。"""
    pipeline = [
        {"$group": {"_id": "$level", "reader_count": {"$sum": 1}}},
        {"$project": {"_id": 0, "level": "$_id", "reader_count": 1}},
        {"$sort": {"reader_count": -1, "level": 1}},
    ]
    return list(db.readers.aggregate(pipeline))


def show_college_stats(stats: list[dict[str, Any]]) -> None:
    print_table(["学院", "读者人数"], [(s["college"], s["reader_count"]) for s in stats])


def show_level_distribution(stats: list[dict[str, Any]]) -> None:
    print_table(["借阅等级", "人数"], [(s["level"], s["reader_count"]) for s in stats])
