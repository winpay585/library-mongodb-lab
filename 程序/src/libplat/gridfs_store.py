"""GridFS 文件存储模块：电子书 PDF 与封面图的上传、下载与校验。"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from gridfs import GridFSBucket
from pymongo.errors import PyMongoError

from .audit import write_log
from .config import settings
CN_TZ = timezone(timedelta(hours=8))


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest(gridfs_dir: Path | None = None) -> dict[str, Any]:
    gridfs_dir = gridfs_dir or settings.path("gridfs_dir")
    manifest = gridfs_dir / "files_manifest.txt"
    return json.loads(manifest.read_text(encoding="utf-8"))


def upload_all(db=None, gridfs_dir: Path | None = None) -> list[dict[str, Any]]:
    """把 3 个 PDF 与 3 张封面写入 GridFS，并写入元数据。

    元数据：isbn（关联图书）、file_type（ebook/cover）、original_name（原始文件名）
    """
    db = _db() if db is None else db
    gridfs_dir = gridfs_dir or settings.path("gridfs_dir")
    manifest = load_manifest(gridfs_dir)
    bucket = GridFSBucket(db, bucket_name="fs")
    uploaded: list[dict[str, Any]] = []

    for group, file_type in (("ebooks", "ebook"), ("covers", "cover")):
        for item in manifest[group]:
            path = gridfs_dir / item["filename"]
            if not path.exists():
                raise FileNotFoundError(f"文件缺失: {path}")
            # 幂等：同名文件先删除，避免重复上传
            for old in db["fs.files"].find({"filename": item["filename"]}, {"_id": 1}):
                bucket.delete(old["_id"])
            with open(path, "rb") as fh:
                file_id = bucket.upload_from_stream(
                    item["filename"],
                    fh,
                    metadata={
                        "isbn": item["related_isbn"],
                        "file_type": file_type,
                        "original_name": item["filename"],
                        "size_bytes": item["bytes"],
                    },
                )
            write_log("UPLOAD", "fs.files", item["filename"],
                      {"isbn": item["related_isbn"], "bytes": item["bytes"], "file_type": file_type},
                      db=db)
            uploaded.append({"filename": item["filename"], "file_id": str(file_id),
                             "bytes": item["bytes"], "file_type": file_type,
                             "isbn": item["related_isbn"]})
    return uploaded


def list_files(db=None) -> list[dict[str, Any]]:
    """列出 GridFS 中全部文件及大小、上传时间。"""
    db = _db() if db is None else db
    rows = []
    for f in db["fs.files"].find({}, {"filename": 1, "length": 1, "uploadDate": 1, "metadata": 1}):
        meta = f.get("metadata") or {}
        rows.append({
            "filename": f["filename"],
            "bytes": f.get("length", 0),
            "upload_date": f.get("uploadDate").astimezone(CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
            "isbn": meta.get("isbn", ""),
            "file_type": meta.get("file_type", ""),
        })
    return sorted(rows, key=lambda r: (r["file_type"], r["filename"]))


def find_book_by_title(keyword: str, db=None) -> dict | None:
    """按书名模糊检索图书，返回含 ebook_name 的文档。"""
    db = _db() if db is None else db
    return db.books.find_one(
        {"title": {"$regex": re.escape(keyword), "$options": "i"}},
        {"_id": 0, "isbn": 1, "title": 1, "ebook_name": 1},
    )


def download(filename: str, out_dir: Path | None = None, db=None) -> Path:
    """按文件名从 GridFS 下载到本地目录。"""
    db = _db() if db is None else db
    out_dir = out_dir or settings.path("download_dir")
    out_dir.mkdir(parents=True, exist_ok=True)
    bucket = GridFSBucket(db, bucket_name="fs")
    target = out_dir / filename

    # 先确认存在，避免空读取
    if not db["fs.files"].find_one({"filename": filename}, {"_id": 1}):
        raise FileNotFoundError(f"GridFS 中不存在文件: {filename}")

    with open(target, "wb") as fh:
        bucket.download_to_stream_by_name(filename, fh)
    write_log("DOWNLOAD", "fs.files", filename, {"path": str(target)}, db=db)
    return target


def download_by_title(keyword: str, out_dir: Path | None = None, db=None) -> dict[str, Any]:
    """按书名查询电子书并下载，返回校验信息。"""
    book = find_book_by_title(keyword, db)
    if not book:
        raise LookupError(f"没有找到书名包含「{keyword}」的图书")
    if not book.get("ebook_name"):
        raise LookupError(f"《{book['title']}》没有关联电子书")
    path = download(book["ebook_name"], out_dir, db)
    return {"book": book, "path": path, "bytes": path.stat().st_size}


def verify(db=None, gridfs_dir: Path | None = None,
           download_dir: Path | None = None) -> list[dict[str, Any]]:
    """全量校验：下载全部文件，比对字节数与 MD5 是否与源文件一致。"""
    db = _db() if db is None else db
    gridfs_dir = gridfs_dir or settings.path("gridfs_dir")
    download_dir = download_dir or settings.path("download_dir")
    rows = []
    for item in list_files(db):
        local = download(item["filename"], download_dir, db)
        src = gridfs_dir / item["filename"]
        rows.append({
            "filename": item["filename"],
            "gridfs_bytes": item["bytes"],
            "download_bytes": local.stat().st_size,
            "source_bytes": src.stat().st_size if src.exists() else -1,
            "size_match": local.stat().st_size == item["bytes"] == (src.stat().st_size if src.exists() else -1),
            "md5_match": md5_of(local) == md5_of(src) if src.exists() else False,
        })
    return rows


def _db():
    from .db import get_db
    return get_db()
