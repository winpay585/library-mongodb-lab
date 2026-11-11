"""统一数据库连接模块。

所有业务模块只通过本模块获取客户端/集合，避免各处重复构造连接串。

认证策略（LIB_AUTH 环境变量控制）:
    LIB_AUTH=1  强制使用账号连接（验证权限时使用）
    LIB_AUTH=0  强制使用无账号连接（建库、建账号的引导阶段使用）
    未设置      自动探测：先用账号连接，认证失败则回退到无账号连接并给出提示
"""
from __future__ import annotations

import os
from typing import Any

from gridfs import GridFSBucket
from pymongo import MongoClient, ReadPreference
from pymongo.database import Database
from pymongo.errors import OperationFailure

from .config import settings

_CLIENTS: dict[str, MongoClient] = {}

READ_PREF_MAP = {
    "primary": ReadPreference.PRIMARY,
    "primaryPreferred": ReadPreference.PRIMARY_PREFERRED,
    "secondary": ReadPreference.SECONDARY,
    "secondaryPreferred": ReadPreference.SECONDARY_PREFERRED,
    "nearest": ReadPreference.NEAREST,
}


def _build(uri: str, read_preference: str | None) -> MongoClient:
    kwargs: dict[str, Any] = {
        "serverSelectionTimeoutMS": 8000,
        "appname": "smart-library-platform",
        "tz_aware": True,
    }
    if read_preference:
        kwargs["read_preference"] = READ_PREF_MAP[read_preference]
    return MongoClient(uri, **kwargs)


def get_client(*, profile: str | None = None, auth: bool = True,
               readonly: bool = False, read_preference: str | None = None) -> MongoClient:
    """获取（并缓存）MongoClient。

    参数
    ----
    profile : standalone / replset / shard，默认取配置中的 default_profile
    auth    : 是否使用带账号的连接串
    readonly: 使用只读账号（用于权限验证）
    read_preference: 副本集读取偏好，未指定时取配置项
    """
    profile = profile or settings.profile
    pref_name = read_preference or (settings.read_preference if profile == "replset" else None)
    mode = os.environ.get("LIB_AUTH")  # None / "1" / "0"

    if readonly:
        candidates = [(settings.readonly_uri, "只读账号")]
    elif not auth or mode == "0":
        candidates = [(settings.uri(profile, auth=False), "无账号")]
    elif mode == "1":
        candidates = [(settings.uri(profile, auth=True), "账号")]
    else:
        candidates = [(settings.uri(profile, auth=True), "账号"),
                      (settings.uri(profile, auth=False), "无账号(回退)")]

    last_error: Exception | None = None
    for uri, label in candidates:
        key = f"{uri}|{pref_name}"
        if key in _CLIENTS:
            return _CLIENTS[key]
        client = _build(uri, pref_name)
        try:
            # connectionStatus 会真正触发认证，能在引导阶段暴露账号不存在的问题
            client.admin.command("connectionStatus")
        except OperationFailure as exc:
            last_error = exc
            client.close()
            if readonly:
                raise
            continue
        _CLIENTS[key] = client
        if label.endswith("回退)"):
            print(f"[提示] 数据库尚未创建账号（未启用访问控制），已使用无认证连接: {uri}")
        return client
    raise last_error if last_error else RuntimeError("无法建立数据库连接")


def get_db(*, profile: str | None = None, auth: bool = True,
           readonly: bool = False, read_preference: str | None = None) -> Database:
    """返回平台数据库对象。"""
    return get_client(
        profile=profile, auth=auth, readonly=readonly, read_preference=read_preference
    )[settings.db_name]


def books(db: Database | None = None):
    return (get_db() if db is None else db).books


def readers(db: Database | None = None):
    return (get_db() if db is None else db).readers


def borrow_logs(db: Database | None = None):
    return (get_db() if db is None else db).borrow_logs


def audit_logs(db: Database | None = None):
    return (get_db() if db is None else db).audit_logs


def category_stats(db: Database | None = None):
    return (get_db() if db is None else db).category_stats


def get_fs(db: Database | None = None) -> GridFSBucket:
    """GridFS 存储桶，桶名固定为 fs。"""
    return GridFSBucket(get_db() if db is None else db, bucket_name="fs")


def ping(profile: str | None = None, auth: bool = True) -> str:
    """连通性自检，返回服务端版本、拓扑类型与当前账号。"""
    client = get_client(profile=profile, auth=auth)
    info = client.admin.command("hello")
    version = client.server_info().get("version", "unknown")
    topo = "sharded" if info.get("msg") == "isdbgrid" else ("replicaSet" if info.get("setName") else "standalone")
    try:
        username = client.admin.command("connectionStatus")["authInfo"]["authenticatedUsers"][0]["user"]
    except Exception:
        username = "anonymous"
    return (f"连接成功 | MongoDB {version} | 拓扑: {topo} | 账号: {username}"
            f" | 主节点: {info.get('primary', 'N/A')}")
