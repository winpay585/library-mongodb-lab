"""索引清单：任务二的索引设计与任务三的实际创建共用同一份定义。"""
from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, TEXT

INDEX_PLAN: dict[str, list[dict]] = {
    "books": [
        {"keys": [("isbn", ASCENDING)], "name": "uk_isbn", "unique": True,
         "purpose": "ISBN 唯一标识，点查与去重"},
        {"keys": [("category", ASCENDING), ("price", ASCENDING)], "name": "idx_category_price",
         "purpose": "类别 + 价格区间组合检索（最常用筛选）"},
        {"keys": [("tags", ASCENDING)], "name": "idx_tags",
         "purpose": "标签多选匹配（multikey 索引）"},
        {"keys": [("publish_date", DESCENDING)], "name": "idx_publish_date",
         "purpose": "出版年份区间检索与时间排序"},
        {"keys": [("rating", DESCENDING)], "name": "idx_rating_desc",
         "purpose": "评分 Top10 排序取数"},
        {"keys": [("title", TEXT), ("author", TEXT)], "name": "idx_text_title_author",
         "purpose": "书名/作者全文检索（替代低效正则）"},
    ],
    "readers": [
        {"keys": [("card_no", ASCENDING)], "name": "uk_card_no", "unique": True,
         "purpose": "借阅证号唯一，借阅流水关联"},
        {"keys": [("college", ASCENDING), ("level", ASCENDING)], "name": "idx_college_level",
         "purpose": "按学院/等级筛选与学院统计"},
        {"keys": [("fav_categories", ASCENDING)], "name": "idx_fav_categories",
         "purpose": "偏好类别匹配"},
    ],
    "borrow_logs": [
        {"keys": [("reader_card", ASCENDING), ("borrow_date", DESCENDING)], "name": "idx_reader_date",
         "purpose": "读者借阅历史（等值 + 时间倒序），同时是分片键前缀"},
        {"keys": [("book_isbn", ASCENDING), ("borrow_date", DESCENDING)], "name": "idx_book_date",
         "purpose": "图书借阅历史与热门书统计"},
        {"keys": [("borrow_date", DESCENDING)], "name": "idx_borrow_date",
         "purpose": "按年月趋势统计与时间范围查询"},
        {"keys": [("status", ASCENDING)], "name": "idx_status",
         "purpose": "在借/逾期状态筛选"},
    ],
    "audit_logs": [
        {"keys": [("ts", DESCENDING)], "name": "idx_ts_desc",
         "purpose": "按时间倒序取最近 100 条操作"},
        {"keys": [("action", ASCENDING), ("ts", DESCENDING)], "name": "idx_action_ts",
         "purpose": "按操作类型筛选"},
    ],
    "category_stats": [
        {"keys": [("category", ASCENDING)], "name": "uk_stat_category", "unique": True,
         "purpose": "统计结果按类别点查"},
    ],
}


def planned_list() -> list[list[str]]:
    """展开成「集合 / 索引名 / 字段 / 类型 / 用途」的表格行。"""
    rows = []
    for coll, items in INDEX_PLAN.items():
        for item in items:
            fields = ", ".join(f"{k}:{'1' if v == ASCENDING else '-1' if v == DESCENDING else 'text'}"
                               for k, v in item["keys"])
            kind = "唯一" if item.get("unique") else ("全文" if any(v == TEXT for _, v in item["keys"]) else "普通")
            rows.append([coll, item["name"], fields, kind, item["purpose"]])
    return rows


def ensure_indexes(db) -> list[tuple[str, str]]:
    """按清单创建索引，返回 (集合, 索引名) 列表。"""
    created = []
    for coll, items in INDEX_PLAN.items():
        if coll not in db.list_collection_names():
            continue
        for item in items:
            kwargs = {"name": item["name"]}
            if item.get("unique"):
                kwargs["unique"] = True
            db[coll].create_index(item["keys"], **kwargs)
            created.append((coll, item["name"]))
    return created
