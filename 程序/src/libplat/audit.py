"""操作日志模块。

audit_logs 结构（自行设计）:
    ts        Date      操作发生时间，倒序查询的排序键
    action    String    INSERT / UPDATE / DELETE / EXPORT / UPLOAD / DOWNLOAD / LOGIN
    collection String   目标集合名
    target    String    业务主键（ISBN、借阅证号或文件名）
    operator  String    操作账号（取自认证用户名）
    detail    Object    变更摘要 {before, after, count}
    result    String    成功 / 失败
    cost_ms   Int       耗时
"""
from __future__ import annotations

import functools
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from pymongo.database import Database

from .db import audit_logs, get_db

CN_TZ = timezone(timedelta(hours=8))


def _operator(db: Database) -> str:
    """取当前连接使用的账号名，未启用认证时返回 anonymous。"""
    try:
        status = db.client.admin.command("connectionStatus")
        users = status.get("authInfo", {}).get("authenticatedUsers", [])
        return users[0]["user"] if users else "anonymous"
    except Exception:
        return "anonymous"


def write_log(action: str, collection: str, target: str = "",
              detail: dict[str, Any] | None = None, result: str = "成功",
              cost_ms: int | None = None, db: Database | None = None) -> None:
    """写入一条操作日志。"""
    db = get_db() if db is None else db
    audit_logs(db).insert_one({
        "ts": datetime.now(CN_TZ),
        "action": action,
        "collection": collection,
        "target": target,
        "operator": _operator(db),
        "detail": detail or {},
        "result": result,
        "cost_ms": cost_ms,
    })


def audit(action: str, collection: str, target_key: str = "target"):
    """装饰器：自动记录操作日志与耗时，失败也留痕。"""

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            target = str(kwargs.get(target_key, args[0] if args else ""))
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                write_log(action, collection, target,
                          {"error": str(exc)}, result="失败",
                          cost_ms=int((time.perf_counter() - started) * 1000))
                raise
            write_log(action, collection, target,
                      {"return": str(result)[:120]}, result="成功",
                      cost_ms=int((time.perf_counter() - started) * 1000))
            return result

        return wrapper

    return decorator


def recent(limit: int = 100, db: Database | None = None) -> list[dict]:
    """按时间倒序查询最近 N 条操作，支撑「最近 100 条」需求。"""
    cursor = audit_logs(db).find({}, {"_id": 0}).sort("ts", -1).limit(limit)
    return list(cursor)


def ensure_indexes(db: Database | None = None) -> list[str]:
    """建立日志索引：倒序时间 + 操作类型。"""
    db = get_db() if db is None else db
    created = []
    created.append(audit_logs(db).create_index([("ts", -1)], name="idx_ts_desc"))
    created.append(audit_logs(db).create_index([("action", 1), ("ts", -1)], name="idx_action_ts"))
    return created
