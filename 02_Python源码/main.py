# -*- coding: utf-8 -*-
"""图书情报检索与统计平台 —— 菜单式主程序。

运行前请确保：
1. MongoDB 已在 127.0.0.1:27017 启动；
2. 已执行任务二的建库与数据导入；
3. 已安装 pymongo（pip install pymongo）。

启动方式：python main.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone

from pymongo.errors import PyMongoError

import book_manager
import borrow_manager
import reader_manager
import stat_manager
from mongodb_connect import MONGO_DB, MONGO_HOST, MONGO_PORT, close_client, get_database


# ---------------------------------------------------------------------------
# 输入辅助
# ---------------------------------------------------------------------------
def input_optional(prompt: str) -> str | None:
    value = input(prompt).strip()
    return value or None


def input_float(prompt: str) -> float | None:
    value = input(prompt).strip()
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        print("输入的不是数字，已忽略该条件。")
        return None


def input_int(prompt: str, default: int | None = None) -> int | None:
    value = input(prompt).strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        print("输入的不是整数，已使用默认值。")
        return default


def pause() -> None:
    input("\n按回车键返回主菜单 ...")


# ---------------------------------------------------------------------------
# 菜单各项功能
# ---------------------------------------------------------------------------
def menu_search_books(db) -> None:
    print("\n--- 1. 图书条件检索 ---")
    keyword = input_optional("关键词（书名/作者/ISBN，回车跳过）: ")
    category = input_optional("类别（如 计算机/文学，回车跳过）: ")
    min_price = input_float("最低价格（回车跳过）: ")
    max_price = input_float("最高价格（回车跳过）: ")
    books = book_manager.search_books(db, keyword, category, min_price, max_price)
    book_manager.show_books(books)


def menu_add_book(db) -> None:
    print("\n--- 2. 新增图书 ---")
    tags_text = input("标签（多个用英文逗号分隔，可回车跳过）: ").strip()
    book = {
        "isbn": input("ISBN: ").strip(),
        "title": input("书名: ").strip(),
        "author": input("作者: ").strip(),
        "publisher": input("出版社: ").strip(),
        "category": input("类别: ").strip(),
        "price": input_float("价格: ") or 0.0,
        "stock": input_int("库存: ", 0) or 0,
        "rating": input_float("评分（0-5）: ") or 0.0,
        "tags": [t.strip() for t in tags_text.replace("，", ",").split(",") if t.strip()],
        "publish_date": datetime.now(timezone.utc),
        "borrow_count": 0,
    }
    inserted_id = book_manager.add_book(db, book)
    print(f"新增成功，_id = {inserted_id}")


def menu_adjust_stock(db) -> None:
    print("\n--- 3. 调整库存 ---")
    isbn = input("ISBN: ").strip()
    delta = input_int("库存变化量（正数增加，负数减少）: ", 0) or 0
    changed = book_manager.adjust_stock(db, isbn, delta)
    if changed:
        print(f"库存调整成功，受影响文档数 = {changed}")
    else:
        print("未找到该 ISBN，或库存没有发生变化。")


def menu_delete_book(db) -> None:
    print("\n--- 4. 删除图书 ---")
    isbn = input("ISBN: ").strip()
    confirm = input(f"确认删除 ISBN={isbn} 的图书？(y/N): ").strip().lower()
    if confirm != "y":
        print("已取消删除。")
        return
    deleted = book_manager.delete_book(db, isbn)
    print(f"删除完成，受影响文档数 = {deleted}")


def menu_readers(db) -> None:
    print("\n--- 5. 读者查询与统计 ---")
    keyword = input_optional("按借阅证号/姓名/学院查询（回车显示全部）: ")
    readers = reader_manager.find_readers(db, keyword)
    reader_manager.show_readers(readers)
    print("\n各学院读者人数：")
    reader_manager.show_college_stats(reader_manager.college_stats(db))
    print("\n借阅等级分布：")
    reader_manager.show_level_distribution(reader_manager.level_distribution(db))


def menu_borrow(db) -> None:
    print("\n--- 6. 借阅登记 ---")
    card_no = input("借阅证号: ").strip()
    isbn = input("ISBN: ").strip()
    borrow_manager.borrow_book(db, card_no, isbn)


def menu_return(db) -> None:
    print("\n--- 7. 归还处理 ---")
    card_no = input("借阅证号: ").strip()
    isbn = input("ISBN: ").strip()
    changed = borrow_manager.return_book(db, card_no, isbn)
    print(f"受影响文档数 = {changed}")


def menu_overdue(db) -> None:
    print("\n--- 8. 逾期查询 ---")
    days = input_int("超过多少天视为逾期（默认 30）: ", 30) or 30
    records = borrow_manager.overdue_borrows(db, days)
    borrow_manager.show_overdue(records)
    if records:
        mark = input("是否把这些记录批量标记为“逾期”？(y/N): ").strip().lower()
        if mark == "y":
            changed = borrow_manager.mark_overdue(db, days)
            print(f"已标记 {changed} 条记录为逾期。")


def menu_category_stats(db) -> None:
    print("\n--- 9. 分类统计 ---")
    stat_manager.show_category_stats(stat_manager.category_stats(db))


def menu_trend(db) -> None:
    print("\n--- 10. 借阅趋势 ---")
    stat_manager.show_borrow_trend(stat_manager.borrow_trend(db))


def menu_bestsellers(db) -> None:
    print("\n--- 11. 畅销榜 ---")
    n = input_int("显示前几名（默认 5）: ", 5) or 5
    stat_manager.show_bestsellers(stat_manager.bestsellers(db, n))


def menu_publishers(db) -> None:
    print("\n--- 12. 出版社排行 ---")
    n = input_int("显示前几家（默认 5）: ", 5) or 5
    stat_manager.show_publisher_stats(stat_manager.publisher_stats(db, n))


# ---------------------------------------------------------------------------
# 主程序
# ---------------------------------------------------------------------------
def print_banner(db) -> None:
    print("=" * 64)
    print("          图书情报检索与统计平台（MongoDB + PyMongo）")
    print("=" * 64)
    print(f"连接地址：mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}")
    print("连接状态：成功")
    print(f"图书总数：{db.books.count_documents({})} 本")
    print(f"读者总数：{db.readers.count_documents({})} 人")
    print(f"借阅流水：{db.borrow_logs.count_documents({})} 条")
    print(f"统计结果：{db.category_stats.count_documents({})} 条")
    print("=" * 64)


def main() -> int:
    client = None
    try:
        client, db = get_database()
        print_banner(db)
    except (PyMongoError, OSError) as exc:
        print("数据库连接失败：", exc)
        print("请检查 MongoDB 是否启动、账号密码是否正确。")
        close_client(client)
        return 1

    menu = """
请选择功能：
  1. 图书条件检索          2. 新增图书
  3. 调整库存              4. 删除图书
  5. 读者查询与统计        6. 借阅登记
  7. 归还处理              8. 逾期查询
  9. 分类统计             10. 借阅趋势
 11. 畅销榜               12. 出版社排行
  0. 退出系统
"""
    actions = {
        "1": menu_search_books,
        "2": menu_add_book,
        "3": menu_adjust_stock,
        "4": menu_delete_book,
        "5": menu_readers,
        "6": menu_borrow,
        "7": menu_return,
        "8": menu_overdue,
        "9": menu_category_stats,
        "10": menu_trend,
        "11": menu_bestsellers,
        "12": menu_publishers,
    }

    try:
        while True:
            print(menu)
            choice = input("请输入功能编号: ").strip()
            if choice == "0":
                print("感谢使用，正在退出 ...")
                break
            action = actions.get(choice)
            if action is None:
                print("无效的编号，请重新输入。")
                continue
            try:
                action(db)
            except (PyMongoError, ValueError) as exc:
                print("操作失败：", exc)
            pause()
    except (KeyboardInterrupt, EOFError):
        print("\n检测到退出信号，程序结束。")
    finally:
        close_client(client)
        print("数据库连接已关闭。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
