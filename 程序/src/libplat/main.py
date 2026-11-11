"""主程序：菜单式交互界面。

覆盖任务三要求的 11 项检索与统计能力，另含图书/读者/借阅管理、
电子书存储与操作日志，共 13 个功能项。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import books as books_api
from . import borrows as borrow_api
from . import db as db_api
from . import gridfs_store
from . import readers as readers_api
from . import stats
from .audit import recent

WIDTH_MAP = {}


def _width(text: str) -> int:
    """粗略计算中文显示宽度，保证表格对齐。"""
    total = 0
    for ch in str(text):
        total += 2 if ord(ch) > 127 else 1
    return total


def row(cells: list[str], widths: list[int], sep: str = " | ") -> str:
    out = []
    for text, width in zip(cells, widths):
        s = str(text)
        out.append(s + " " * max(width - _width(s), 0))
    return sep.join(out).rstrip()


def table(headers: list[str], rows: list[list[str]], limit: int | None = 20) -> None:
    widths = [_width(h) for h in headers]
    for r in rows:
        widths = [max(w, _width(c)) for w, c in zip(widths, r)]
    print(row(headers, widths))
    print("-+-".join("-" * w for w in widths))
    for r in rows[:limit] if limit else rows:
        print(row(r, widths))
    if limit and len(rows) > limit:
        print(f"... 共 {len(rows)} 条，仅显示前 {limit} 条")


def show(data) -> None:
    """通用的结果打印：列表按字典展平。"""
    if isinstance(data, list) and data and isinstance(data[0], dict):
        keys = list(data[0].keys())
        table(keys, [[_fmt(item.get(k)) for k in keys] for item in data])
    else:
        print(data)


def _fmt(value) -> str:
    from datetime import datetime, timedelta, timezone
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.strftime("%Y-%m-%d %H:%M")
        return value.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    if isinstance(value, dict):
        return ",".join(f"{k}={v}" for k, v in value.items())
    if isinstance(value, list):
        return "/".join(str(v) for v in value)
    return str(value)


def pause() -> None:
    input("\n按回车返回主菜单...")


def ask(prompt: str, default: str = "") -> str:
    value = input(prompt).strip()
    return value or default


# ---------------- 菜单项 ----------------
def menu_overview() -> None:
    print(db_api.ping())
    print()
    counts = stats.overview()
    table(["集合", "文档数"], [[k, v] for k, v in counts.items()], limit=None)


def menu_category_price() -> None:
    category = ask("类别（计算机/文学/历史/经济管理/自然科学/艺术）: ", "计算机")
    lo = float(ask("最低价格: ", "50"))
    hi = float(ask("最高价格: ", "120"))
    result = books_api.by_category_price(category, lo, hi)
    print(f"\n[结果] {len(result)} 条")
    show(result)


def menu_tags() -> None:
    raw = ask("标签（多个用英文逗号分隔，如 编程,入门）: ", "编程,入门")
    tags = [t.strip() for t in raw.split(",") if t.strip()]
    result = books_api.by_tags_all(tags)
    print(f"\n[结果] 同时含 {tags} 的图书 {len(result)} 条")
    show(result)


def menu_title() -> None:
    keyword = ask("书名关键词: ", "Python")
    result = books_api.by_title(keyword)
    print(f"\n[结果] {len(result)} 条")
    show(result)


def menu_year() -> None:
    start = int(ask("起始年份: ", "2020"))
    end = int(ask("结束年份: ", "2024"))
    result = books_api.by_publish_year_range(start, end)
    print(f"\n[结果] {start}-{end} 年出版 {len(result)} 条")
    show(result)


def menu_quality() -> None:
    no_tags = books_api.missing_tags()
    print(f"\n[数据质量] 缺少 tags 字段的图书 {len(no_tags)} 条")
    show(no_tags)
    no_mail = readers_api.missing_email()
    print(f"\n[数据质量] 缺少 email 的读者 {len(no_mail)} 条")
    show(no_mail)


def menu_top_rating() -> None:
    result = books_api.top_rated(10)
    print("\n[评分 Top10]")
    show(result)


def menu_paging() -> None:
    page = int(ask("页码: ", "1"))
    data = books_api.list_books(page=page)
    print(f"\n第 {data['page']}/{data['pages']} 页，共 {data['total']} 条")
    show(data["items"])


def menu_book_crud() -> None:
    print("1 新增图书  2 修改库存  3 删除图书")
    op = ask("选择: ", "1")
    if op == "1":
        book = {
            "isbn": ask("ISBN: ", "9780000000001"),
            "title": ask("书名: ", "测试图书"),
            "author": ask("作者: ", "测试作者"),
            "publisher": ask("出版社: ", "测试出版社"),
            "category": ask("类别: ", "计算机"),
            "price": float(ask("价格: ", "59.9")),
            "stock": int(ask("库存: ", "3")),
            "rating": float(ask("评分: ", "4.2")),
            "publish_date": ask("出版日期(YYYY-MM-DD): ", "2024-09-01"),
            "location": {"floor": "四楼新书区", "shelf": "D-01", "copies": 3},
        }
        print("已新增，ISBN =", books_api.add_book(book))
    elif op == "2":
        isbn = ask("ISBN: ", "9787115428028")
        print("修改条数:", books_api.update_book(isbn, {"stock": int(ask("新库存: ", "20"))}))
    else:
        isbn = ask("ISBN: ", "9780000000001")
        print("删除条数:", books_api.delete_book(isbn))


def menu_readers() -> None:
    print("1 按学院  2 按等级  3 新增读者  4 偏好类别")
    op = ask("选择: ", "1")
    if op == "1":
        show(readers_api.by_college(ask("学院: ", "计算机学院")))
    elif op == "2":
        show(readers_api.by_level(ask("等级(普通/高级/教师): ", "高级")))
    elif op == "3":
        reader = {
            "card_no": ask("借阅证号: ", "R20260001"),
            "name": ask("姓名: ", "测试读者"),
            "college": ask("学院: ", "计算机学院"),
            "email": ask("邮箱: ", "test@example.edu"),
            "phone": ask("电话: ", "13000000000"),
            "level": ask("等级: ", "普通"),
            "register_date": ask("注册日期(YYYY-MM-DD): ", "2026-09-01"),
            "fav_categories": ["计算机"],
        }
        print("已新增，证号 =", readers_api.add_reader(reader))
    else:
        show(readers_api.like_category(ask("类别: ", "计算机")))


def menu_borrow() -> None:
    print("1 借书  2 还书  3 逾期清单  4 读者借阅历史")
    op = ask("选择: ", "1")
    card = ask("借阅证号: ", "R20240001")
    if op == "1":
        print(borrow_api.borrow(card, ask("ISBN: ", "9787115428028")))
    elif op == "2":
        print(borrow_api.give_back(card, ask("ISBN: ", "9787115428028")))
    elif op == "3":
        show(borrow_api.overdue())
    else:
        show(borrow_api.history_by_reader(card, 15))


def menu_stats() -> None:
    print("1 分类统计  2 学院借阅 Top5  3 月度趋势  4 借阅 Top10  5 联合分析  6 统计落库")
    op = ask("选择: ", "1")
    if op == "1":
        show(stats.category_summary())
    elif op == "2":
        show(stats.college_top(5))
    elif op == "3":
        show(stats.monthly_trend())
    elif op == "4":
        show(stats.top_borrowed_books(10))
    elif op == "5":
        for r in stats.college_category_matrix():
            print(r["college"], r["top_categories"])
    else:
        print(stats.save_category_stats())


def menu_gridfs() -> None:
    print("1 上传样例文件  2 文件清单  3 按书名下载  4 全量校验")
    op = ask("选择: ", "2")
    if op == "1":
        show(gridfs_store.upload_all())
    elif op == "2":
        show(gridfs_store.list_files())
    elif op == "3":
        keyword = ask("书名关键词: ", "Python编程")
        info = gridfs_store.download_by_title(keyword)
        print(f"已下载《{info['book']['title']}》-> {info['path']} ({info['bytes']} 字节)")
    else:
        show(gridfs_store.verify())


def menu_audit() -> None:
    rows = recent(100)
    print(f"\n[操作日志] 最近 {len(rows)} 条")
    if not rows:
        print("暂无操作日志")
        return
    table(["时间", "操作", "集合", "目标", "账号", "结果"],
          [[_fmt(r["ts"]), r["action"], r["collection"], r["target"],
            r["operator"], r["result"]] for r in rows], limit=30)


MENU = [
    ("1", "平台概览：连通性 + 各集合文档数", menu_overview),
    ("2", "图书检索：类别 + 价格区间", menu_category_price),
    ("3", "图书检索：标签多选（同时命中）", menu_tags),
    ("4", "图书检索：书名模糊", menu_title),
    ("5", "图书检索：出版年份区间", menu_year),
    ("6", "数据质量核查：缺 tags / 缺 email", menu_quality),
    ("7", "图书检索：评分 Top10", menu_top_rating),
    ("8", "图书分页浏览", menu_paging),
    ("9", "图书增删改", menu_book_crud),
    ("10", "读者查询与新增", menu_readers),
    ("11", "借阅 / 归还 / 逾期 / 历史", menu_borrow),
    ("12", "统计分析：分类 / 学院 / 趋势 / Top10 / 联合 / 落库", menu_stats),
    ("13", "电子书：GridFS 上传 / 清单 / 下载 / 校验", menu_gridfs),
    ("14", "操作日志：最近 100 条", menu_audit),
]


def banner() -> None:
    print("=" * 78)
    print("  智慧图书馆数字资源平台  ·  MongoDB 版  ·  课程期末项目")
    print("=" * 78)
    print(db_api.ping())
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="智慧图书馆数字资源平台")
    parser.add_argument("--profile", help="standalone / replset / shard")
    parser.add_argument("--no-auth", action="store_true", help="使用未启用认证的连接串")
    parser.add_argument("--demo", action="store_true", help="非交互执行检索统计演示（用于过程记录）")
    args = parser.parse_args(argv)
    if args.profile:
        import os
        os.environ["LIB_PROFILE"] = args.profile

    if args.demo:
        return demo()

    banner()
    while True:
        print("功能菜单")
        for key, label, _ in MENU:
            print(f"  {key:>2}. {label}")
        print("   0. 退出")
        choice = ask("\n请输入功能编号: ")
        if choice in ("0", "q", "quit"):
            print("已退出。")
            return 0
        for key, _, handler in MENU:
            if key == choice:
                print()
                try:
                    handler()
                except Exception as exc:  # 菜单层兜底，避免因单条数据异常退出
                    print(f"[错误] {type(exc).__name__}: {exc}")
                pause()
                break
        else:
            print("无效编号，请重新输入。")


def demo() -> int:
    """固定顺序跑一遍核心能力，输出可直接截图的记录。"""
    banner()
    print(">> 1. 图书检索：类别=计算机 且 价格 50~120")
    result = books_api.by_category_price("计算机", 50, 120)
    print(f"[结果] {len(result)} 条")
    show(result)

    print("\n>> 2. 图书检索：同时含标签 [编程, 入门]")
    result = books_api.by_tags_all(["编程", "入门"])
    print(f"[结果] {len(result)} 条")
    show(result)

    print("\n>> 3. 图书检索：书名包含「计算机」")
    result = books_api.by_title("计算机")
    print(f"[结果] {len(result)} 条")
    show(result)

    print("\n>> 4. 图书检索：出版年份 2021—2024")
    result = books_api.by_publish_year_range(2021, 2024)
    print(f"[结果] {len(result)} 条")
    show(result)

    print("\n>> 5. 数据质量：缺少 tags 字段的图书")
    result = books_api.missing_tags()
    print(f"[结果] {len(result)} 条")
    show(result)

    print("\n>> 6. 图书检索：评分 Top10（仅书名/作者/评分）")
    show(books_api.top_rated(10))

    print("\n>> 7. 统计：按类别统计藏书量/均价/均分")
    show(stats.category_summary())

    print("\n>> 8. 统计：各学院借阅总量 Top5")
    show(stats.college_top(5))

    print("\n>> 9. 统计：按年月借阅趋势（前后各 6 个月）")
    trend = stats.monthly_trend()
    show(trend[:6] + trend[-6:])

    print("\n>> 10. 统计：借阅次数 Top10 并关联馆藏位置")
    show(stats.top_borrowed_books(10))

    print("\n>> 11. 统计结果落库 -> category_stats")
    print(stats.save_category_stats())

    print("\n>> 12. 电子书文件清单（GridFS）")
    show(gridfs_store.list_files())
    return 0


if __name__ == "__main__":
    sys.exit(main())
