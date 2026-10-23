# -*- coding: utf-8 -*-
"""MongoDB 连接模块（图书情报检索与统计平台）

功能：
1. 统一封装 MongoClient 的连接参数；
2. 提供 get_database() / close_client() 给其余 5 个程序文件调用；
3. 提供终端表格输出辅助函数 print_table()，避免中文列宽错位。

运行环境：Python 3.9+，pymongo 4.x
默认连接：mongodb://libWriter:Writer%4012345@127.0.0.1:27017/library?authSource=library
如本机账号或端口不同，修改下方 MONGO_URI，或设置环境变量 MONGO_URI。
"""

from __future__ import annotations

import os
import unicodedata
from typing import Iterable, Sequence

from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import PyMongoError

# ---------------------------------------------------------------------------
# 连接参数统一在此定义
# ---------------------------------------------------------------------------
MONGO_HOST = os.getenv("MONGO_HOST", "127.0.0.1")
MONGO_PORT = int(os.getenv("MONGO_PORT", "27017"))
MONGO_DB = os.getenv("MONGO_DB", "library")
MONGO_USER = os.getenv("MONGO_USER", "libWriter")
MONGO_PASSWORD = os.getenv("MONGO_PASSWORD", "Writer@12345")
MONGO_AUTH_SOURCE = os.getenv("MONGO_AUTH_SOURCE", "library")

# 密码中的 @ 必须转义为 %40，否则 URI 解析会失败
_uri_password = MONGO_PASSWORD.replace("@", "%40")
MONGO_URI = os.getenv(
    "MONGO_URI",
    f"mongodb://{MONGO_USER}:{_uri_password}@{MONGO_HOST}:{MONGO_PORT}/"
    f"{MONGO_DB}?authSource={MONGO_AUTH_SOURCE}",
)


def get_database() -> tuple[MongoClient, Database]:
    """建立连接并返回 (client, database)。

    使用 serverSelectionTimeoutMS 避免服务器未启动时长时间卡住；
    连接后执行 ping，确保返回的是一个真正可用的连接。
    """
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except PyMongoError:
        client.close()
        raise
    return client, client[MONGO_DB]


def close_client(client: MongoClient | None) -> None:
    """安全关闭连接。"""
    if client is not None:
        client.close()


# ---------------------------------------------------------------------------
# 终端表格输出辅助
# ---------------------------------------------------------------------------
def _display_width(text: object) -> int:
    """计算字符串在终端中的显示宽度（中文按 2 列计）。"""
    width = 0
    for ch in str(text):
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad(text: object, width: int, align: str = "left") -> str:
    text = str(text)
    space = max(0, width - _display_width(text))
    if align == "right":
        return " " * space + text
    return text + " " * space


def print_table(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> None:
    """打印带分隔线的终端表格；没有数据时给出明确提示。"""
    rows = [list(row) for row in rows]
    if not rows:
        print("（没有查询到符合条件的数据）")
        return

    widths = [_display_width(h) for h in headers]
    for row in rows:
        for i, value in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], _display_width(value))

    line = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    print(line)
    print("| " + " | ".join(_pad(h, widths[i]) for i, h in enumerate(headers)) + " |")
    print(line)
    for row in rows:
        cells = [_pad(row[i] if i < len(row) else "", widths[i]) for i in range(len(headers))]
        print("| " + " | ".join(cells) + " |")
    print(line)
    print(f"共 {len(rows)} 条记录")


if __name__ == "__main__":
    # 直接运行本文件可单独检查数据库连接是否正常
    print("正在连接 MongoDB ...")
    _client, _db = get_database()
    print(f"连接成功：mongodb://{MONGO_HOST}:{MONGO_PORT}/{MONGO_DB}")
    print("数据库：", _db.name)
    print("集合：", ", ".join(sorted(_db.list_collection_names())))
    close_client(_client)
